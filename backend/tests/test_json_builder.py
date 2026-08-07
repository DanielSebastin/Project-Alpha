"""Unit tests for app/pipeline/json_builder.py — tasks 4.2"""

import pytest

from app.models.errors import ErrorCode, PipelineError
from app.models.schemas import ResumeProfile
from app.pipeline.json_builder import build, deserialize, serialize


# ---------------------------------------------------------------------------
# 1. Malformed JSON raises MALFORMED_LLM_RESPONSE
# ---------------------------------------------------------------------------

def test_malformed_llm_response():
    with pytest.raises(PipelineError) as exc_info:
        deserialize("not json")
    assert exc_info.value.error_code == ErrorCode.MALFORMED_LLM_RESPONSE


# ---------------------------------------------------------------------------
# 2. Valid dict returns a fully-populated ResumeProfile
# ---------------------------------------------------------------------------

def test_valid_dict_returns_resume_profile():
    raw = {
        "projects": [
            {"name": "MyProject", "description": "A cool project", "technologies": ["Python"]}
        ],
        "technical_skills": ["Python"],
        "soft_skills": ["Leadership"],
        "certifications": ["AWS Certified"],
        "achievements": ["Won hackathon"],
        "hackathons": [{"name": "HackX", "role": "Backend Dev"}],
        "experience": [
            {
                "company": "Acme",
                "role": "Engineer",
                "duration": "1 year",
                "description": "Built stuff",
            }
        ],
    }
    profile = build(raw)

    assert isinstance(profile, ResumeProfile)
    assert profile.projects[0].name == "MyProject"
    assert profile.projects[0].description == "A cool project"
    assert profile.certifications == ["AWS Certified"]
    assert profile.achievements == ["Won hackathon"]
    assert profile.hackathons[0].name == "HackX"
    assert profile.hackathons[0].role == "Backend Dev"
    assert profile.experience[0].company == "Acme"
    assert profile.experience[0].role == "Engineer"
    assert profile.experience[0].duration == "1 year"
    assert profile.experience[0].description == "Built stuff"
    assert "Leadership" in profile.soft_skills


# ---------------------------------------------------------------------------
# 3. Schema validation error includes field-level details
# ---------------------------------------------------------------------------

def test_schema_validation_error_with_field_details():
    with pytest.raises(PipelineError) as exc_info:
        build({"projects": "not-a-list"})
    err = exc_info.value
    assert err.error_code == ErrorCode.SCHEMA_VALIDATION_ERROR
    assert isinstance(err.details, dict)
    # At least one key should reference the "projects" field
    assert any("projects" in key for key in err.details)


# ---------------------------------------------------------------------------
# 4. Technology normalization and promotion to skills
# ---------------------------------------------------------------------------

def test_technology_normalization_and_promotion():
    raw = {
        "projects": [
            {"name": "X", "description": "Y", "technologies": ["fastapi", "postgresql"]}
        ],
        "technical_skills": [],
        "soft_skills": [],
    }
    profile = build(raw)

    # Normalized in project
    assert "FastAPI" in profile.projects[0].technologies
    assert "PostgreSQL" in profile.projects[0].technologies
    assert "fastapi" not in profile.projects[0].technologies
    assert "postgresql" not in profile.projects[0].technologies

    # Promoted to technical_skills
    assert "FastAPI" in profile.technical_skills
    assert "PostgreSQL" in profile.technical_skills


# ---------------------------------------------------------------------------
# 5. Deduplication — case-insensitive, first occurrence wins
# ---------------------------------------------------------------------------

def test_deduplication():
    raw = {
        "projects": [
            {"name": "X", "description": "Y", "technologies": ["React", "react"]}
        ],
        "technical_skills": ["React", "react", "Python"],
        "soft_skills": ["Teamwork", "teamwork"],
    }
    profile = build(raw)

    # Project technologies deduplicated: only one "React"
    assert profile.projects[0].technologies.count("React") == 1
    assert len(profile.projects[0].technologies) == 1

    # technical_skills deduplicated: "React" once, "Python" once
    react_count = sum(1 for s in profile.technical_skills if s.lower() == "react")
    python_count = sum(1 for s in profile.technical_skills if s.lower() == "python")
    assert react_count == 1
    assert python_count == 1

    # soft_skills deduplicated: "Teamwork" once
    teamwork_count = sum(1 for s in profile.soft_skills if s.lower() == "teamwork")
    assert teamwork_count == 1


# ---------------------------------------------------------------------------
# 6. Null / missing fields coerce to defaults
# ---------------------------------------------------------------------------

def test_null_coercion_empty_dict():
    profile = build({})

    assert profile.projects == []
    assert profile.technical_skills == []
    assert profile.soft_skills == []
    assert profile.certifications == []
    assert profile.achievements == []
    assert profile.hackathons == []
    assert profile.experience == []


def test_null_coercion_project_fields():
    profile = build({"projects": [{"name": None}]})

    assert profile.projects[0].name is None
    assert profile.projects[0].description is None
    assert profile.projects[0].technologies == []


# ---------------------------------------------------------------------------
# 7. Round-trip: serialize / deserialize
# ---------------------------------------------------------------------------

def test_serialize_deserialize_roundtrip():
    raw = {
        "projects": [{"name": "P", "description": "D", "technologies": ["Python"]}],
        "technical_skills": ["Python"],
        "soft_skills": ["Leadership"],
        "certifications": [],
        "achievements": [],
        "hackathons": [],
        "experience": [],
    }
    original = build(raw)
    json_str = serialize(original)
    restored = deserialize(json_str)

    assert restored.projects[0].name == "P"
    assert "Python" in restored.technical_skills
    assert "Leadership" in restored.soft_skills
