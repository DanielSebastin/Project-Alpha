"""app/pipeline/github_pipeline.py

Runs the GitHub verification pipeline for a given username and returns
extracted skill evidence. Wraps the github_verification_experiment scripts
as pure Python functions — no subprocess calls, no file I/O side effects
visible to callers.

Stages:
    1. Collect repositories (GraphQL)
    2. Filter (remove forks/archived, keep top N)
    3. Fetch READMEs (REST)
    4. Fetch dependency files (REST)
    5. Extract skills from all evidence sources
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_GITHUB_GRAPHQL = "https://api.github.com/graphql"
_GITHUB_REST_BASE = "https://api.github.com"
_MAX_REPOS = 10
_REQUEST_TIMEOUT = 30.0
_RATE_LIMIT_BACKOFF = 60
_MAX_RETRIES = 3

# Ecosystem detection
_LANGUAGE_TO_ECOSYSTEM: dict[str, str] = {
    "python": "python",
    "javascript": "node",
    "typescript": "node",
    "dart": "flutter",
    "java": "java",
    "kotlin": "java",
    "rust": "rust",
}

_ECOSYSTEM_FILES: dict[str, list[str]] = {
    "python":  ["requirements.txt", "pyproject.toml"],
    "node":    ["package.json"],
    "flutter": ["pubspec.yaml"],
    "java":    ["pom.xml"],
    "rust":    ["Cargo.toml"],
}

# Technology canonical map
_TECH_MAP: dict[str, str] = {
    "fastapi": "FastAPI", "flask": "Flask", "django": "Django",
    "sqlalchemy": "SQLAlchemy", "pydantic": "Pydantic", "uvicorn": "Uvicorn",
    "httpx": "httpx", "requests": "requests", "pytest": "pytest",
    "celery": "Celery", "psycopg2": "psycopg2", "psycopg2-binary": "psycopg2",
    "redis": "Redis", "pymongo": "PyMongo", "pymupdf": "PyMuPDF",
    "numpy": "NumPy", "pandas": "Pandas", "scikit-learn": "scikit-learn",
    "torch": "PyTorch", "tensorflow": "TensorFlow", "langchain": "LangChain",
    "openai": "OpenAI", "groq": "Groq", "qdrant-client": "Qdrant",
    "qdrant": "Qdrant", "chromadb": "ChromaDB", "anthropic": "Anthropic",
    "react": "React", "react-dom": "React", "vue": "Vue.js",
    "next": "Next.js", "express": "Express", "vite": "Vite",
    "tailwindcss": "Tailwind CSS", "@mui/material": "Material UI",
    "axios": "Axios", "typescript": "TypeScript", "eslint": "ESLint",
    "docker": "Docker", "kubernetes": "Kubernetes", "aws": "AWS",
    "postgresql": "PostgreSQL", "postgres": "PostgreSQL",
    "mongodb": "MongoDB", "sqlite": "SQLite", "mysql": "MySQL",
    "sentence-transformers": "sentence-transformers",
    "faiss-cpu": "faiss-cpu", "streamlit": "Streamlit",
    "python-dotenv": "python-dotenv", "motor": "motor",
    "python-jose": "python-jose", "bcrypt": "bcrypt",
    "playwright": "playwright", "apscheduler": "apscheduler",
}

# README patterns → canonical skill
_README_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bfastapi\b', re.I), "FastAPI"),
    (re.compile(r'\bflask\b', re.I), "Flask"),
    (re.compile(r'\bdjango\b', re.I), "Django"),
    (re.compile(r'\bpython\b', re.I), "Python"),
    (re.compile(r'\bsqlalchemy\b', re.I), "SQLAlchemy"),
    (re.compile(r'\bpydantic\b', re.I), "Pydantic"),
    (re.compile(r'\breact\b', re.I), "React"),
    (re.compile(r'\btypescript\b', re.I), "TypeScript"),
    (re.compile(r'\bjavascript\b', re.I), "JavaScript"),
    (re.compile(r'\bvite\b', re.I), "Vite"),
    (re.compile(r'\btailwind\b', re.I), "Tailwind CSS"),
    (re.compile(r'\bdocker\b', re.I), "Docker"),
    (re.compile(r'\bkubernetes\b', re.I), "Kubernetes"),
    (re.compile(r'\bpostgres(?:ql)?\b', re.I), "PostgreSQL"),
    (re.compile(r'\bmongodb\b', re.I), "MongoDB"),
    (re.compile(r'\bredis\b', re.I), "Redis"),
    (re.compile(r'\bgroq\b', re.I), "Groq"),
    (re.compile(r'\bopenai\b', re.I), "OpenAI"),
    (re.compile(r'\blangchain\b', re.I), "LangChain"),
    (re.compile(r'\bqdrant\b', re.I), "Qdrant"),
    (re.compile(r'\bchromadb\b', re.I), "ChromaDB"),
    (re.compile(r'\bgithub\s+actions\b', re.I), "GitHub Actions"),
    (re.compile(r'\baws\b'), "AWS"),
    (re.compile(r'\bgraphql\b', re.I), "GraphQL"),
    (re.compile(r'\bstreamlit\b', re.I), "Streamlit"),
    (re.compile(r'\bfaiss\b', re.I), "faiss-cpu"),
    (re.compile(r'\bollama\b', re.I), "Ollama"),
]

_GRAPHQL_REPOS_QUERY = """
query FetchRepositories($username: String!, $first: Int!) {
  user(login: $username) {
    repositories(
      first: $first
      orderBy: { field: UPDATED_AT, direction: DESC }
      ownerAffiliations: OWNER
    ) {
      nodes {
        name
        description
        isFork
        isArchived
        updatedAt
        repositoryTopics(first: 20) {
          nodes { topic { name } }
        }
        languages(first: 20, orderBy: { field: SIZE, direction: DESC }) {
          nodes { name color }
        }
      }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gh_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _fetch_file(client: httpx.Client, token: str, owner: str, repo: str, filepath: str) -> str | None:
    url = f"{_GITHUB_REST_BASE}/repos/{owner}/{repo}/contents/{filepath}"
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            r = client.get(url, headers=_gh_headers(token), timeout=_REQUEST_TIMEOUT)
        except httpx.RequestError:
            if attempt < _MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            return None
        if r.status_code == 404:
            return None
        if r.status_code in (403, 429):
            time.sleep(int(r.headers.get("Retry-After", _RATE_LIMIT_BACKOFF)))
            continue
        if not r.is_success:
            if attempt < _MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            return None
        data = r.json()
        encoded = data.get("content", "")
        return base64.b64decode(encoded.replace("\n", "")).decode("utf-8", errors="replace")
    return None


def _extract_pkg_name(raw: str) -> str:
    return re.split(r'[=><!;\[\s@]', raw.strip())[0].strip()


def _add_evidence(
    registry: dict[str, list[dict]],
    skill: str,
    source: str,
    repo: str,
    detail: str,
) -> None:
    canonical = _TECH_MAP.get(skill.lower(), skill)
    if canonical not in registry:
        registry[canonical] = []
    entry = {"source": source, "repo": repo, "detail": detail}
    if entry not in registry[canonical]:
        registry[canonical].append(entry)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_github_pipeline(username: str, github_token: str) -> dict[str, Any]:
    """Run the full GitHub verification pipeline for *username*.

    Args:
        username: GitHub login name.
        github_token: Personal access token with repo read access.

    Returns:
        Dict matching extracted_skills.json format:
        {"username": str, "skills": {skill_name: {"evidence": [...]}}}

    Raises:
        ValueError: If the user is not found or GraphQL returns errors.
        httpx.HTTPStatusError: On non-2xx responses after retries.
    """
    logger.info("Starting GitHub pipeline for username='%s'", username)

    # ------------------------------------------------------------------ #
    # Stage 1: Collect repositories via GraphQL                           #
    # ------------------------------------------------------------------ #
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": _GRAPHQL_REPOS_QUERY,
        "variables": {"username": username, "first": 100},
    }

    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as aclient:
        resp = await aclient.post(_GITHUB_GRAPHQL, json=payload, headers=headers)
    resp.raise_for_status()
    gql_data = resp.json()

    if "errors" in gql_data:
        messages = "; ".join(e.get("message", "unknown") for e in gql_data["errors"])
        raise ValueError(f"GitHub GraphQL error: {messages}")

    user_node = gql_data.get("data", {}).get("user")
    if user_node is None:
        raise ValueError(f"GitHub user '{username}' not found.")

    all_repos = []
    for node in user_node["repositories"]["nodes"]:
        topics = [t["topic"]["name"] for t in node.get("repositoryTopics", {}).get("nodes", [])]
        languages = [{"name": l["name"], "color": l.get("color")} for l in node.get("languages", {}).get("nodes", [])]
        all_repos.append({
            "name": node["name"],
            "is_fork": node["isFork"],
            "is_archived": node["isArchived"],
            "updated_at": node["updatedAt"],
            "topics": topics,
            "languages": languages,
        })

    logger.info("Collected %d repositories for '%s'", len(all_repos), username)

    # ------------------------------------------------------------------ #
    # Stage 2: Filter                                                      #
    # ------------------------------------------------------------------ #
    active = [r for r in all_repos if not r["is_fork"] and not r["is_archived"]]
    active.sort(key=lambda r: r["updated_at"], reverse=True)
    filtered = active[:_MAX_REPOS]
    logger.info("Filtered to %d repositories", len(filtered))

    # ------------------------------------------------------------------ #
    # Stages 3-4: READMEs + dependency files (synchronous HTTP)          #
    # ------------------------------------------------------------------ #
    skill_registry: dict[str, list[dict]] = {}

    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        for repo in filtered:
            repo_name = repo["name"]

            # Languages
            for lang in repo["languages"]:
                lang_name = lang["name"]
                if lang_name.lower() not in ("css", "html"):
                    _add_evidence(skill_registry, lang_name, "language", repo_name, "Detected as repository language")
                else:
                    _add_evidence(skill_registry, lang_name, "language", repo_name, "Detected as repository language")

            # Topics
            for topic in repo["topics"]:
                _add_evidence(skill_registry, topic, "topic", repo_name, f"Repository topic: {topic}")

            # README
            readme = _fetch_file(client, github_token, username, repo_name, "README.md")
            if not readme:
                readme = _fetch_file(client, github_token, username, repo_name, "readme.md")
            if readme:
                for pattern, skill_name in _README_PATTERNS:
                    if pattern.search(readme):
                        _add_evidence(skill_registry, skill_name, "readme", repo_name, "Mentioned in README")

            # Dependency files
            lang_names = {l["name"].lower() for l in repo["languages"]}
            ecosystems = {_LANGUAGE_TO_ECOSYSTEM[l] for l in lang_names if l in _LANGUAGE_TO_ECOSYSTEM}

            for eco in ecosystems:
                for dep_file in _ECOSYSTEM_FILES.get(eco, []):
                    content = _fetch_file(client, github_token, username, repo_name, dep_file)
                    if not content:
                        continue

                    if dep_file == "requirements.txt":
                        for line in content.splitlines():
                            line = line.strip()
                            if line and not line.startswith("#"):
                                pkg = _extract_pkg_name(line)
                                if pkg:
                                    _add_evidence(skill_registry, pkg, "dependency", repo_name, dep_file)

                    elif dep_file == "pyproject.toml":
                        try:
                            import tomllib
                            data = tomllib.loads(content)
                            for dep in data.get("project", {}).get("dependencies", []):
                                pkg = _extract_pkg_name(dep)
                                if pkg:
                                    _add_evidence(skill_registry, pkg, "dependency", repo_name, dep_file)
                            for pkg in data.get("tool", {}).get("poetry", {}).get("dependencies", {}):
                                if pkg.lower() != "python":
                                    _add_evidence(skill_registry, pkg, "dependency", repo_name, dep_file)
                        except Exception:
                            pass

                    elif dep_file == "package.json":
                        try:
                            pkg_data = json.loads(content)
                            all_deps = {}
                            all_deps.update(pkg_data.get("dependencies", {}))
                            all_deps.update(pkg_data.get("devDependencies", {}))
                            for pkg in all_deps:
                                _add_evidence(skill_registry, pkg, "dependency", repo_name, dep_file)
                        except json.JSONDecodeError:
                            pass

                    elif dep_file == "Cargo.toml":
                        try:
                            import tomllib
                            data = tomllib.loads(content)
                            for section in ("dependencies", "dev-dependencies"):
                                for pkg in data.get(section, {}):
                                    _add_evidence(skill_registry, pkg, "dependency", repo_name, dep_file)
                        except Exception:
                            pass

            time.sleep(0.3)  # be a good API citizen

    logger.info("GitHub pipeline complete. Extracted %d unique skills.", len(skill_registry))

    return {
        "username": username,
        "skills": {
            name: {"canonical_name": name, "evidence": ev}
            for name, ev in skill_registry.items()
        },
    }
