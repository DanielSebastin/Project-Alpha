"""app/pipeline/skill_verifier.py

Matches resume skills against GitHub extracted skills and produces
a verification result with confidence scores.

Evidence source weights:
    language   = 1
    readme     = 2
    topic      = 3
    dependency = 4

Score formula:
    score = (total_weight * 10) + (unique_repos * 5) + (unique_sources * 10)
    Clamped to [0, 100]
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

_ALIASES: dict[str, str] = {
    "js": "JavaScript", "javascript": "JavaScript",
    "ts": "TypeScript", "typescript": "TypeScript",
    "node": "Node.js", "nodejs": "Node.js", "node.js": "Node.js", "node js": "Node.js",
    "python": "Python", "python3": "Python",
    "fastapi": "FastAPI", "fast-api": "FastAPI", "fast api": "FastAPI",
    "flask": "Flask", "django": "Django",
    "react": "React", "reactjs": "React", "react.js": "React", "react js": "React",
    "vue": "Vue.js", "vuejs": "Vue.js", "vue.js": "Vue.js",
    "next": "Next.js", "nextjs": "Next.js", "next.js": "Next.js",
    "postgres": "PostgreSQL", "postgresql": "PostgreSQL", "pg": "PostgreSQL",
    "mongodb": "MongoDB", "mongo": "MongoDB",
    "mysql": "MySQL", "sqlite": "SQLite", "redis": "Redis",
    "docker": "Docker", "kubernetes": "Kubernetes", "k8s": "Kubernetes",
    "aws": "AWS", "amazon web services": "AWS",
    "graphql": "GraphQL",
    "tailwind": "Tailwind CSS", "tailwindcss": "Tailwind CSS", "tailwind css": "Tailwind CSS",
    "mui": "Material UI", "material ui": "Material UI",
    "langchain": "LangChain", "openai": "OpenAI",
    "pandas": "Pandas", "numpy": "NumPy",
    "sklearn": "scikit-learn", "scikit-learn": "scikit-learn", "scikit learn": "scikit-learn",
    "pytorch": "PyTorch", "torch": "PyTorch",
    "tensorflow": "TensorFlow", "tf": "TensorFlow",
    "streamlit": "Streamlit", "pydantic": "Pydantic",
    "sqlalchemy": "SQLAlchemy", "uvicorn": "Uvicorn",
    "socket.io": "Socket.IO", "socketio": "Socket.IO",
    "groq": "Groq", "qdrant": "Qdrant",
    "html": "HTML", "css": "CSS",
    "java": "Java", "rust": "Rust", "go": "Go", "golang": "Go",
    "c": "C", "c++": "C++", "cpp": "C++",
    "dart": "Dart", "flutter": "Flutter",
    "swift": "Swift", "kotlin": "Kotlin",
    "git": "Git", "github actions": "GitHub Actions",
    "linux": "Linux", "bash": "Shell", "shell": "Shell",
}

_SOURCE_WEIGHTS: dict[str, int] = {
    "language":   1,
    "readme":     2,
    "topic":      3,
    "dependency": 4,
}

_CONFIDENCE_LEVELS = [
    (80, "VERY_HIGH"),
    (60, "HIGH"),
    (30, "MEDIUM"),
    (0,  "LOW"),
]


def normalize(skill: str) -> str:
    """Normalize a skill name for comparison."""
    cleaned = re.sub(r'\s+', ' ', skill.strip()).lower()
    return _ALIASES.get(cleaned, skill.strip())


def collect_resume_skills(resume_profile: dict) -> list[str]:
    """Collect deduplicated skills from technical_skills + project technologies."""
    seen: set[str] = set()
    skills: list[str] = []

    def _add(raw: str) -> None:
        norm = normalize(raw).lower()
        if norm not in seen:
            seen.add(norm)
            skills.append(raw.strip())

    for s in resume_profile.get("technical_skills") or []:
        if isinstance(s, str) and s.strip():
            _add(s)

    for project in resume_profile.get("projects") or []:
        for tech in (project.get("technologies") or []):
            if isinstance(tech, str) and tech.strip():
                _add(tech)

    return skills


def _confidence_level(score: int) -> str:
    for threshold, label in _CONFIDENCE_LEVELS:
        if score >= threshold:
            return label
    return "LOW"


def _calculate_confidence(evidence: list[dict]) -> dict:
    total_weight = 0
    unique_repos: set[str] = set()
    unique_sources: set[str] = set()

    for entry in evidence:
        if not isinstance(entry, dict):
            continue
        source = entry.get("source", "")
        repo = entry.get("repo", "")
        total_weight += _SOURCE_WEIGHTS.get(source, 0)
        if repo:
            unique_repos.add(repo)
        if source:
            unique_sources.add(source)

    raw = total_weight * 10 + len(unique_repos) * 5 + len(unique_sources) * 10
    score = max(0, min(100, raw))
    return {"score": score, "level": _confidence_level(score)}


def verify_skills(resume_profile: dict, github_data: dict) -> dict:
    """Match resume skills against GitHub extracted skills.

    Args:
        resume_profile: ResumeProfile dict (output of resume parser).
        github_data: Dict from github_pipeline.run_github_pipeline().

    Returns:
        verification_result dict.
    """
    username = github_data.get("username", "unknown")
    github_skills: dict = github_data.get("skills", {})

    # Build GitHub lookup: normalized → (original, evidence)
    gh_lookup: dict[str, tuple[str, list[dict]]] = {}
    for gh_name, gh_data in github_skills.items():
        norm = normalize(gh_name).lower()
        evidence = gh_data.get("evidence", []) if isinstance(gh_data, dict) else []
        gh_lookup[norm] = (gh_name, evidence)

    resume_skills = collect_resume_skills(resume_profile)

    matched = []
    unmatched = []

    for raw_skill in resume_skills:
        norm = normalize(raw_skill).lower()
        if norm in gh_lookup:
            gh_name, evidence = gh_lookup[norm]
            matched.append({
                "resume_skill": raw_skill,
                "github_skill": gh_name,
                "confidence": _calculate_confidence(evidence),
                "evidence": evidence,
            })
        else:
            unmatched.append({"resume_skill": raw_skill})

    total = len(resume_skills)
    matched_count = len(matched)
    pct = round(matched_count / total * 100, 1) if total else 0.0

    return {
        "username": username,
        "matched_skills": matched,
        "unmatched_skills": unmatched,
        "statistics": {
            "resume_skills_count": total,
            "matched_count": matched_count,
            "unmatched_count": len(unmatched),
            "verification_percentage": pct,
        },
    }
