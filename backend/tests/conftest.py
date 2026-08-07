# tests/conftest.py
"""Shared test helpers and fixtures for the resume-parser-pipeline test suite."""
from __future__ import annotations

import json

import fitz
import pytest
from hypothesis import settings

# ---------------------------------------------------------------------------
# Hypothesis CI profile
# ---------------------------------------------------------------------------

settings.register_profile("ci", max_examples=50)
settings.load_profile("ci")


# ---------------------------------------------------------------------------
# Helper functions (not pytest fixtures)
# ---------------------------------------------------------------------------


def synthetic_pdf(pages: list[str]) -> bytes:
    """Build a real PyMuPDF PDF in memory from a list of page text strings.

    One page is created per string; the text is inserted with ``insert_text``.
    Returns the PDF as raw bytes via ``doc.tobytes()``.
    """
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def mock_llm_response(profile_dict: dict) -> bytes:
    """Return a JSON-encoded bytes object mimicking a valid LLM API response.

    Wraps *profile_dict* in the OpenAI-compatible chat completion envelope
    that ``LLMClient._extract_content`` expects:

    .. code-block:: json

        {
            "choices": [
                {
                    "message": {
                        "content": "<json string of profile_dict>"
                    }
                }
            ]
        }
    """
    envelope = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(profile_dict)
                }
            }
        ]
    }
    return json.dumps(envelope).encode("utf-8")


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_resume_profile_dict() -> dict:
    """A realistic hardcoded dict representing a student hackathon participant.

    Contains:
    - 2 projects  (FastAPI web app + React dashboard)
    - 5 skills
    - 1 certification
    - 1 achievement
    - 1 hackathon
    - 1 experience entry
    """
    return {
        "projects": [
            {
                "name": "HackTrack API",
                "description": (
                    "A FastAPI-based REST service for tracking hackathon submissions, "
                    "with JWT authentication and PostgreSQL persistence."
                ),
                "technologies": ["FastAPI", "Python", "PostgreSQL", "Docker"],
            },
            {
                "name": "TeamPulse Dashboard",
                "description": (
                    "A React single-page application that visualises team metrics "
                    "and integrates with GitHub via OAuth."
                ),
                "technologies": ["React", "TypeScript", "GitHub API"],
            },
        ],
        "technical_skills": ["Python", "JavaScript", "Docker", "REST APIs", "Git"],
        "soft_skills": ["Teamwork", "Communication"],
        "certifications": ["AWS Certified Cloud Practitioner"],
        "achievements": ["1st Place — Regional Hackathon 2024"],
        "hackathons": [
            {
                "name": "HackComp 2024",
                "role": "Backend Developer",
            }
        ],
        "experience": [
            {
                "company": "Acme Tech",
                "role": "Software Engineering Intern",
                "duration": "May 2024 – Aug 2024",
                "description": (
                    "Built and maintained internal tooling using Python and FastAPI; "
                    "reduced CI pipeline runtime by 30 %."
                ),
            }
        ],
    }
