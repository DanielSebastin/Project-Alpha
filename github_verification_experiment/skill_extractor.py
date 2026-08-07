"""skill_extractor.py — Extract skills from repository data and build evidence.

Input:  output/repositories_with_dependencies.json
Output: output/extracted_skills.json

Evidence sources tracked per skill:
    language    — appeared as a repository language
    topic       — appeared as a repository topic
    dependency  — found in a dependency file (requirements.txt, package.json, etc.)
    readme      — mentioned in README text

Output schema:
{
  "username": "...",
  "skills": {
    "Python": {
      "canonical_name": "Python",
      "evidence": [
        {
          "source": "language",
          "repo": "fastapi_crash",
          "detail": "Detected as primary language"
        },
        {
          "source": "dependency",
          "repo": "fastapi_crash",
          "detail": "requirements.txt"
        }
      ]
    },
    ...
  }
}

Usage:
    python skill_extractor.py [--input <path>]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

# ---------------------------------------------------------------------------
# Canonical name map — normalise skill names to a consistent casing/spelling
# ---------------------------------------------------------------------------

_CANONICAL: dict[str, str] = {
    # Languages
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "rust": "Rust",
    "java": "Java",
    "dart": "Dart",
    "html": "HTML",
    "css": "CSS",
    "shell": "Shell",
    "dockerfile": "Docker",
    "powershell": "PowerShell",
    # Python packages
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "sqlalchemy": "SQLAlchemy",
    "pydantic": "Pydantic",
    "uvicorn": "Uvicorn",
    "httpx": "httpx",
    "requests": "requests",
    "pytest": "pytest",
    "celery": "Celery",
    "alembic": "Alembic",
    "psycopg2": "psycopg2",
    "psycopg2-binary": "psycopg2",
    "redis": "Redis",
    "pymongo": "PyMongo",
    "pymupdf": "PyMuPDF",
    "hypothesis": "Hypothesis",
    "numpy": "NumPy",
    "pandas": "Pandas",
    "scikit-learn": "scikit-learn",
    "torch": "PyTorch",
    "tensorflow": "TensorFlow",
    "langchain": "LangChain",
    "openai": "OpenAI",
    "groq": "Groq",
    "qdrant-client": "Qdrant",
    "qdrant": "Qdrant",
    "chromadb": "ChromaDB",
    "pinecone-client": "Pinecone",
    "anthropic": "Anthropic",
    # Node packages
    "react": "React",
    "react-dom": "React",
    "react-router-dom": "React Router",
    "vue": "Vue.js",
    "next": "Next.js",
    "express": "Express",
    "vite": "Vite",
    "@vitejs/plugin-react": "Vite",
    "tailwindcss": "Tailwind CSS",
    "@tailwindcss/vite": "Tailwind CSS",
    "@mui/material": "Material UI",
    "axios": "Axios",
    "typescript": "TypeScript",
    "eslint": "ESLint",
    "jest": "Jest",
    "vitest": "Vitest",
    "leaflet": "Leaflet",
    "react-leaflet": "Leaflet",
    "socket.io": "Socket.IO",
    "prisma": "Prisma",
    "sequelize": "Sequelize",
    "mongoose": "Mongoose",
    "graphql": "GraphQL",
    "apollo": "Apollo",
    "webpack": "Webpack",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "aws": "AWS",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mongodb": "MongoDB",
    "sqlite": "SQLite",
    "mysql": "MySQL",
    "semgrep": "Semgrep",
}

# README keyword patterns — regex → canonical skill name
# Only match whole words to avoid false positives
_README_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bfastapi\b', re.IGNORECASE), "FastAPI"),
    (re.compile(r'\bflask\b', re.IGNORECASE), "Flask"),
    (re.compile(r'\bdjango\b', re.IGNORECASE), "Django"),
    (re.compile(r'\bpython\b', re.IGNORECASE), "Python"),
    (re.compile(r'\bsqlalchemy\b', re.IGNORECASE), "SQLAlchemy"),
    (re.compile(r'\bpydantic\b', re.IGNORECASE), "Pydantic"),
    (re.compile(r'\breact\b', re.IGNORECASE), "React"),
    (re.compile(r'\btypescript\b', re.IGNORECASE), "TypeScript"),
    (re.compile(r'\bjavascript\b', re.IGNORECASE), "JavaScript"),
    (re.compile(r'\bvite\b', re.IGNORECASE), "Vite"),
    (re.compile(r'\btailwind\b', re.IGNORECASE), "Tailwind CSS"),
    (re.compile(r'\bdocker\b', re.IGNORECASE), "Docker"),
    (re.compile(r'\bkubernetes\b', re.IGNORECASE), "Kubernetes"),
    (re.compile(r'\bpostgres(?:ql)?\b', re.IGNORECASE), "PostgreSQL"),
    (re.compile(r'\bmongodb\b', re.IGNORECASE), "MongoDB"),
    (re.compile(r'\bredis\b', re.IGNORECASE), "Redis"),
    (re.compile(r'\bgroq\b', re.IGNORECASE), "Groq"),
    (re.compile(r'\bopenai\b', re.IGNORECASE), "OpenAI"),
    (re.compile(r'\blangchain\b', re.IGNORECASE), "LangChain"),
    (re.compile(r'\bqdrant\b', re.IGNORECASE), "Qdrant"),
    (re.compile(r'\bchromadb\b', re.IGNORECASE), "ChromaDB"),
    (re.compile(r'\bpinecone\b', re.IGNORECASE), "Pinecone"),
    (re.compile(r'\bsemgrep\b', re.IGNORECASE), "Semgrep"),
    (re.compile(r'\beslint\b', re.IGNORECASE), "ESLint"),
    (re.compile(r'\bflake8\b', re.IGNORECASE), "Flake8"),
    (re.compile(r'\bgithub\s+actions\b', re.IGNORECASE), "GitHub Actions"),
    (re.compile(r'\baws\b'), "AWS"),
    (re.compile(r'\bgraphql\b', re.IGNORECASE), "GraphQL"),
]


def _canonical(raw: str) -> str:
    """Return the canonical skill name for *raw*, or title-case if unknown."""
    return _CANONICAL.get(raw.lower().strip(), raw.strip())


# ---------------------------------------------------------------------------
# Evidence builder
# ---------------------------------------------------------------------------

class SkillEvidence:
    """Accumulates evidence entries for a single skill."""

    def __init__(self, canonical_name: str) -> None:
        self.canonical_name = canonical_name
        self._entries: list[dict] = []
        # Track (source, repo) pairs to avoid exact duplicates
        self._seen: set[tuple[str, str, str]] = set()

    def add(self, source: str, repo: str, detail: str) -> None:
        key = (source, repo, detail)
        if key not in self._seen:
            self._seen.add(key)
            self._entries.append({"source": source, "repo": repo, "detail": detail})

    def to_dict(self) -> dict:
        return {
            "canonical_name": self.canonical_name,
            "evidence": self._entries,
        }


class SkillRegistry:
    """Holds all skills found across all repositories."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillEvidence] = {}

    def add(self, raw_name: str, source: str, repo: str, detail: str) -> None:
        name = _canonical(raw_name)
        if name not in self._skills:
            self._skills[name] = SkillEvidence(name)
        self._skills[name].add(source, repo, detail)

    def to_dict(self) -> dict[str, dict]:
        return {k: v.to_dict() for k, v in sorted(self._skills.items())}


# ---------------------------------------------------------------------------
# Extractors per source
# ---------------------------------------------------------------------------

def extract_from_languages(registry: SkillRegistry, repo_name: str, languages: list[str]) -> None:
    for lang in languages:
        if lang.lower() in ("css", "html"):
            # Too generic to be meaningful as a standalone skill signal
            registry.add(lang, "language", repo_name, "Detected as repository language")
        else:
            registry.add(lang, "language", repo_name, "Detected as repository language")


def extract_from_topics(registry: SkillRegistry, repo_name: str, topics: list[str]) -> None:
    for topic in topics:
        registry.add(topic, "topic", repo_name, f"Repository topic: {topic}")


def extract_from_requirements_txt(registry: SkillRegistry, repo_name: str, content: str) -> None:
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Strip version specifiers: package==1.0, package>=1.0, package[extra]
        pkg = re.split(r'[=><!;\[\s]', line)[0].strip()
        if pkg:
            registry.add(pkg, "dependency", repo_name, "requirements.txt")


def extract_from_pyproject_toml(registry: SkillRegistry, repo_name: str, content: str) -> None:
    try:
        data = tomllib.loads(content)
    except Exception:
        return

    # [project] dependencies
    deps = data.get("project", {}).get("dependencies", [])
    for dep in deps:
        pkg = re.split(r'[=><!;\[\s@]', dep)[0].strip()
        if pkg:
            registry.add(pkg, "dependency", repo_name, "pyproject.toml")

    # [tool.poetry.dependencies]
    poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    for pkg in poetry_deps:
        if pkg.lower() != "python":
            registry.add(pkg, "dependency", repo_name, "pyproject.toml")


def extract_from_package_json(registry: SkillRegistry, repo_name: str, content: str) -> None:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return

    all_deps: dict[str, str] = {}
    all_deps.update(data.get("dependencies", {}))
    all_deps.update(data.get("devDependencies", {}))

    for pkg in all_deps:
        registry.add(pkg, "dependency", repo_name, "package.json")


def extract_from_pubspec_yaml(registry: SkillRegistry, repo_name: str, content: str) -> None:
    # Simple line-based extraction — avoid requiring PyYAML
    in_deps = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped in ("dependencies:", "dev_dependencies:"):
            in_deps = True
            continue
        if in_deps:
            if stripped and not line[0].isspace():
                in_deps = False
                continue
            match = re.match(r'^\s{2}(\w[\w_-]*):', line)
            if match:
                pkg = match.group(1)
                if pkg not in ("flutter", "sdk"):
                    registry.add(pkg, "dependency", repo_name, "pubspec.yaml")
                else:
                    registry.add("Flutter", "dependency", repo_name, "pubspec.yaml")


def extract_from_pom_xml(registry: SkillRegistry, repo_name: str, content: str) -> None:
    # Extract artifactId values from <dependency> blocks
    for match in re.finditer(r'<artifactId>\s*([^<]+)\s*</artifactId>', content):
        pkg = match.group(1).strip()
        if pkg:
            registry.add(pkg, "dependency", repo_name, "pom.xml")


def extract_from_cargo_toml(registry: SkillRegistry, repo_name: str, content: str) -> None:
    try:
        data = tomllib.loads(content)
    except Exception:
        return
    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        for pkg in data.get(section, {}):
            registry.add(pkg, "dependency", repo_name, "Cargo.toml")


_DEP_FILE_EXTRACTORS = {
    "requirements.txt": extract_from_requirements_txt,
    "pyproject.toml":   extract_from_pyproject_toml,
    "package.json":     extract_from_package_json,
    "pubspec.yaml":     extract_from_pubspec_yaml,
    "pom.xml":          extract_from_pom_xml,
    "Cargo.toml":       extract_from_cargo_toml,
}


def extract_from_readme(registry: SkillRegistry, repo_name: str, content: str) -> None:
    for pattern, skill_name in _README_PATTERNS:
        if pattern.search(content):
            registry.add(skill_name, "readme", repo_name, f"Mentioned in README")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def extract_skills(data: dict) -> dict:
    username: str = data["username"]
    registry = SkillRegistry()

    for repo in data["repositories"]:
        repo_name: str = repo["repo_name"]
        languages: list[str] = repo.get("languages", [])
        topics: list[str] = repo.get("topics", [])  # present if merged from filtered
        readme: str | None = repo.get("readme")
        dependencies: dict[str, str] = repo.get("dependencies", {})

        # 1. Languages
        extract_from_languages(registry, repo_name, languages)

        # 2. Topics
        if topics:
            extract_from_topics(registry, repo_name, topics)

        # 3. Dependency files
        for filename, content in dependencies.items():
            if content and filename in _DEP_FILE_EXTRACTORS:
                _DEP_FILE_EXTRACTORS[filename](registry, repo_name, content)

        # 4. README
        if readme:
            extract_from_readme(registry, repo_name, readme)

    return {
        "username": username,
        "skills": registry.to_dict(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Extract skills from repository data.")
    parser.add_argument(
        "--input",
        default="output/repositories_with_dependencies.json",
        help="Path to repositories_with_dependencies.json",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: '{input_path}' not found.", file=sys.stderr)
        sys.exit(1)

    data = json.loads(input_path.read_text(encoding="utf-8"))
    result = extract_skills(data)

    formatted = json.dumps(result, indent=2, ensure_ascii=False)
    print(formatted)

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "extracted_skills.json"
    output_file.write_text(formatted, encoding="utf-8")

    skill_count = len(result["skills"])
    print(f"\nExtracted {skill_count} unique skills → {output_file}", file=sys.stderr)

    # Print summary table to stderr
    print("\n── Skills by evidence source ───────────────", file=sys.stderr)
    source_counts: dict[str, int] = {}
    for skill_data in result["skills"].values():
        for ev in skill_data["evidence"]:
            src = ev["source"]
            source_counts[src] = source_counts.get(src, 0) + 1
    for src, count in sorted(source_counts.items()):
        print(f"  {src:<12} : {count} evidence entries", file=sys.stderr)
    print("────────────────────────────────────────────", file=sys.stderr)


if __name__ == "__main__":
    main()
