from __future__ import annotations

import json

import pydantic

from app.models.errors import ErrorCode, PipelineError, PipelineStage
from app.models.schemas import ResumeProfile

# Canonical technology name mapping (keys are lowercase for case-insensitive lookup)
_TECH_MAP: dict[str, str] = {
    "fastapi": "FastAPI",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "aws": "AWS",
    "gcp": "GCP",
    "azure": "Azure",
    "react": "React",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "python": "Python",
    "html": "HTML",
    "css": "CSS",
    "sql": "SQL",
    "graphql": "GraphQL",
    "flask": "Flask",
    "django": "Django",
}


def _normalize_tech(tech: str) -> str:
    """Return canonical casing for a technology name, or the original if not in the map."""
    return _TECH_MAP.get(tech.lower(), tech)


def _dedupe_case_insensitive(items: list[str]) -> list[str]:
    """Deduplicate a list of strings using case-insensitive comparison, preserving first occurrence."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def build(raw: dict) -> ResumeProfile:
    """Validate raw dict into a ResumeProfile, normalize technologies, and promote them to skills."""
    try:
        profile = ResumeProfile.model_validate(raw)
    except pydantic.ValidationError as exc:
        details: dict[str, dict] = {}
        for error in exc.errors():
            # loc is a tuple like ('projects',) or ('projects', 0, 'technologies')
            field_name = ".".join(str(part) for part in error["loc"]) if error["loc"] else "unknown"
            details[field_name] = {
                "expected_type": error.get("type", "unknown"),
                "actual_value": error.get("input"),
                "message": error.get("msg", ""),
            }
        raise PipelineError(
            error_code=ErrorCode.SCHEMA_VALIDATION_ERROR,
            message=f"Schema validation failed: {exc.error_count()} error(s)",
            stage=PipelineStage.JSON_BUILDING,
            details=details,
        ) from exc

    # Normalize and deduplicate technologies in each project
    for project in profile.projects:
        normalized = [_normalize_tech(t) for t in project.technologies]
        project.technologies = _dedupe_case_insensitive(normalized)

    # Collect all project technologies to promote into top-level technical_skills
    project_techs: list[str] = []
    for project in profile.projects:
        project_techs.extend(project.technologies)

    # Merge project technologies into technical_skills, then deduplicate
    combined_technical = list(profile.technical_skills) + project_techs
    profile.technical_skills = _dedupe_case_insensitive(combined_technical)

    # Deduplicate soft_skills independently
    profile.soft_skills = _dedupe_case_insensitive(profile.soft_skills)

    return profile


def serialize(profile: ResumeProfile) -> str:
    """Serialize a ResumeProfile to a JSON string."""
    return profile.model_dump_json()


def deserialize(json_str: str) -> ResumeProfile:
    """Deserialize a JSON string into a ResumeProfile."""
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise PipelineError(
            error_code=ErrorCode.MALFORMED_LLM_RESPONSE,
            message=f"Invalid JSON: {exc}",
            stage=PipelineStage.JSON_BUILDING,
        ) from exc

    return build(parsed)
