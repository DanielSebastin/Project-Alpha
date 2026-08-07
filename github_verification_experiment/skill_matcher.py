"""skill_matcher.py — Integration layer between Resume Parser and GitHub Verification Engine.

Connects ResumeProfile JSON output with extracted_skills.json to produce a
verification_result.json with confidence scores for each matched skill.

Does NOT modify any existing pipeline stages.

Usage:
    python skill_matcher.py --resume resume_profile.json --github extracted_skills.json

Output:
    output/verification_result.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

# Canonical form map — key is the normalised (lowercased, stripped) alias
_NORM_MAP: dict[str, str] = {
    # JavaScript variants
    "js":                   "JavaScript",
    "javascript":           "JavaScript",
    "es6":                  "JavaScript",
    # TypeScript variants
    "ts":                   "TypeScript",
    "typescript":           "TypeScript",
    # Node.js variants
    "node":                 "Node.js",
    "nodejs":               "Node.js",
    "node.js":              "Node.js",
    "node js":              "Node.js",
    # Python
    "python":               "Python",
    "python3":              "Python",
    # FastAPI variants
    "fastapi":              "FastAPI",
    "fast-api":             "FastAPI",
    "fast api":             "FastAPI",
    # Flask
    "flask":                "Flask",
    # Django
    "django":               "Django",
    # React variants
    "react":                "React",
    "reactjs":              "React",
    "react.js":             "React",
    "react js":             "React",
    # Vue variants
    "vue":                  "Vue.js",
    "vuejs":                "Vue.js",
    "vue.js":               "Vue.js",
    "vue js":               "Vue.js",
    # Next.js variants
    "next":                 "Next.js",
    "nextjs":               "Next.js",
    "next.js":              "Next.js",
    "next js":              "Next.js",
    # PostgreSQL variants
    "postgres":             "PostgreSQL",
    "postgresql":           "PostgreSQL",
    "pg":                   "PostgreSQL",
    # MongoDB
    "mongodb":              "MongoDB",
    "mongo":                "MongoDB",
    # MySQL
    "mysql":                "MySQL",
    # SQLite
    "sqlite":               "SQLite",
    # Redis
    "redis":                "Redis",
    # Docker
    "docker":               "Docker",
    # Kubernetes
    "kubernetes":           "Kubernetes",
    "k8s":                  "Kubernetes",
    # AWS
    "aws":                  "AWS",
    "amazon web services":  "AWS",
    # GraphQL
    "graphql":              "GraphQL",
    # Express
    "express":              "Express",
    "expressjs":            "Express",
    "express.js":           "Express",
    # Tailwind
    "tailwind":             "Tailwind CSS",
    "tailwindcss":          "Tailwind CSS",
    "tailwind css":         "Tailwind CSS",
    # Material UI
    "mui":                  "Material UI",
    "material ui":          "Material UI",
    # LangChain
    "langchain":            "LangChain",
    # OpenAI
    "openai":               "OpenAI",
    # Pandas
    "pandas":               "Pandas",
    # NumPy
    "numpy":                "NumPy",
    # scikit-learn
    "sklearn":              "scikit-learn",
    "scikit-learn":         "scikit-learn",
    "scikit learn":         "scikit-learn",
    # PyTorch
    "pytorch":              "PyTorch",
    "torch":                "PyTorch",
    # TensorFlow
    "tensorflow":           "TensorFlow",
    "tf":                   "TensorFlow",
    # Streamlit
    "streamlit":            "Streamlit",
    # Pydantic
    "pydantic":             "Pydantic",
    # SQLAlchemy
    "sqlalchemy":           "SQLAlchemy",
    # Uvicorn
    "uvicorn":              "Uvicorn",
    # Socket.IO
    "socket.io":            "Socket.IO",
    "socketio":             "Socket.IO",
    # Groq
    "groq":                 "Groq",
    # Qdrant
    "qdrant":               "Qdrant",
    # HTML / CSS
    "html":                 "HTML",
    "css":                  "CSS",
    # Java
    "java":                 "Java",
    # Rust
    "rust":                 "Rust",
    # Go
    "go":                   "Go",
    "golang":               "Go",
    # C / C++
    "c":                    "C",
    "c++":                  "C++",
    "cpp":                  "C++",
    # Dart / Flutter
    "dart":                 "Dart",
    "flutter":              "Flutter",
    # Swift / Kotlin
    "swift":                "Swift",
    "kotlin":               "Kotlin",
    # Git
    "git":                  "Git",
    # GitHub Actions
    "github actions":       "GitHub Actions",
    # Linux / Shell
    "linux":                "Linux",
    "bash":                 "Shell",
    "shell":                "Shell",
}

# Evidence source weights for confidence scoring
_SOURCE_WEIGHTS: dict[str, int] = {
    "language":   1,
    "readme":     2,
    "topic":      3,
    "dependency": 4,
}

# Confidence thresholds
_CONFIDENCE_LEVELS = [
    (80, "VERY_HIGH"),
    (60, "HIGH"),
    (30, "MEDIUM"),
    (0,  "LOW"),
]


def normalize(skill: str) -> str:
    """Normalize a skill name to its canonical form.

    Steps:
        1. Strip whitespace
        2. Collapse multiple spaces
        3. Lowercase
        4. Apply alias map (returns canonical casing)
        5. If not in map, return title-cased original

    Args:
        skill: Raw skill string.

    Returns:
        Canonical skill name.
    """
    cleaned = re.sub(r'\s+', ' ', skill.strip()).lower()
    return _NORM_MAP.get(cleaned, skill.strip())


# ---------------------------------------------------------------------------
# Resume skill collection
# ---------------------------------------------------------------------------

def collect_resume_skills(resume_profile: dict) -> list[str]:
    """Collect and deduplicate skills from a ResumeProfile dict.

    Collects from:
        - technical_skills (top-level list)
        - projects[*].technologies (nested list)

    Args:
        resume_profile: Parsed ResumeProfile JSON dict.

    Returns:
        Deduplicated list of raw skill strings.
    """
    seen_norm: set[str] = set()
    skills: list[str] = []

    def _add(raw: str) -> None:
        norm = normalize(raw)
        if norm.lower() not in seen_norm:
            seen_norm.add(norm.lower())
            skills.append(raw)

    # A. technical_skills
    for skill in resume_profile.get("technical_skills") or []:
        if isinstance(skill, str) and skill.strip():
            _add(skill.strip())

    # B. project technologies
    for project in resume_profile.get("projects") or []:
        for tech in (project.get("technologies") or []):
            if isinstance(tech, str) and tech.strip():
                _add(tech.strip())

    return skills


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def _confidence_level(score: int) -> str:
    """Map a clamped score to a confidence label."""
    for threshold, label in _CONFIDENCE_LEVELS:
        if score >= threshold:
            return label
    return "LOW"


def calculate_confidence(evidence: list[dict]) -> dict:
    """Calculate confidence score for a matched skill.

    Formula:
        score = (total_weight * 10) + (unique_repos * 5) + (unique_sources * 10)
        Clamped to [0, 100].

    Args:
        evidence: List of evidence entry dicts from extracted_skills.json.

    Returns:
        Dict with keys: score (int), level (str).
    """
    total_weight = 0
    unique_repos: set[str] = set()
    unique_sources: set[str] = set()

    for entry in evidence:
        if not isinstance(entry, dict):
            continue
        source = entry.get("source", "")
        repo = entry.get("repo", "")

        weight = _SOURCE_WEIGHTS.get(source, 0)
        total_weight += weight

        if repo:
            unique_repos.add(repo)
        if source:
            unique_sources.add(source)

    raw_score = (
        total_weight * 10
        + len(unique_repos) * 5
        + len(unique_sources) * 10
    )
    score = max(0, min(100, raw_score))

    return {
        "score": score,
        "level": _confidence_level(score),
    }


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def match_skills(
    resume_skills: list[str],
    github_skills: dict[str, dict],
) -> dict:
    """Match resume skills against GitHub extracted skills.

    Args:
        resume_skills: Raw skill strings from the resume.
        github_skills: Dict mapping skill name → skill data from extracted_skills.json.

    Returns:
        Dict with matched_skills, unmatched_skills, statistics.
    """
    # Build GitHub lookup: normalized_name → (original_name, evidence)
    github_lookup: dict[str, tuple[str, list[dict]]] = {}
    for gh_name, gh_data in github_skills.items():
        norm = normalize(gh_name).lower()
        evidence = gh_data.get("evidence") or [] if isinstance(gh_data, dict) else []
        github_lookup[norm] = (gh_name, evidence)

    matched: list[dict] = []
    unmatched: list[dict] = []

    for raw_skill in resume_skills:
        norm_resume = normalize(raw_skill).lower()

        if norm_resume in github_lookup:
            gh_name, evidence = github_lookup[norm_resume]
            confidence = calculate_confidence(evidence)
            matched.append({
                "resume_skill": raw_skill,
                "github_skill": gh_name,
                "confidence": confidence,
                "evidence": evidence,
            })
        else:
            unmatched.append({"resume_skill": raw_skill})

    resume_count = len(resume_skills)
    matched_count = len(matched)
    unmatched_count = len(unmatched)
    verification_pct = round((matched_count / resume_count * 100), 1) if resume_count else 0.0

    return {
        "matched_skills": matched,
        "unmatched_skills": unmatched,
        "statistics": {
            "resume_skills_count": resume_count,
            "matched_count": matched_count,
            "unmatched_count": unmatched_count,
            "verification_percentage": verification_pct,
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Match resume skills against GitHub extracted skills."
    )
    parser.add_argument(
        "--resume",
        required=True,
        help="Path to ResumeProfile JSON file (output of resume parser)",
    )
    parser.add_argument(
        "--github",
        default="output/extracted_skills.json",
        help="Path to extracted_skills.json (default: output/extracted_skills.json)",
    )
    args = parser.parse_args()

    resume_path = Path(args.resume)
    github_path = Path(args.github)

    for p in (resume_path, github_path):
        if not p.exists():
            print(f"Error: '{p}' not found.", file=sys.stderr)
            sys.exit(1)

    # Load inputs
    try:
        resume_profile = json.loads(resume_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Error: '{resume_path}' contains invalid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        github_data = json.loads(github_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Error: '{github_path}' contains invalid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    username: str = github_data.get("username", "unknown")
    github_skills: dict = github_data.get("skills", {})

    # Collect resume skills from technical_skills + project technologies
    resume_skills = collect_resume_skills(resume_profile)

    print(f"Resume skills found    : {len(resume_skills)}")
    print(f"GitHub skills loaded   : {len(github_skills)}")

    # Match
    result = match_skills(resume_skills, github_skills)
    stats = result["statistics"]

    print(f"Matched skills         : {stats['matched_count']}")
    print(f"Unmatched skills       : {stats['unmatched_count']}")
    print(f"Verification percentage: {stats['verification_percentage']}%")

    # Build output
    output = {"username": username, **result}
    formatted = json.dumps(output, indent=2, ensure_ascii=False)

    # Save
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "verification_result.json"
    output_file.write_text(formatted, encoding="utf-8")

    print(f"\nOutput saved to        : {output_file}")
    print()
    print(formatted)


if __name__ == "__main__":
    main()
