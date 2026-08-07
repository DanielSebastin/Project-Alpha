"""tests/test_api.py

Integration tests for the POST /parse API endpoint.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.main import app
from app.models.schemas import (
    ExperienceObject,
    HackathonObject,
    ProjectObject,
    ResumeProfile,
)

# Maximum PDF size in bytes (10 MB)
MAX_PDF_SIZE_BYTES = 10 * 1024 * 1024

# Minimal valid-looking PDF header bytes (not a real PDF, but enough for content-type routing)
_SMALL_PDF_BYTES = b"%PDF-1.4 small fake pdf content"


@pytest.fixture()
def sample_profile() -> ResumeProfile:
    """Return a sample ResumeProfile used across tests."""
    return ResumeProfile(
        projects=[ProjectObject(name="Project A", description="Desc", technologies=["Python"])],
        technical_skills=["Python", "FastAPI"],
        soft_skills=["Leadership"],
        certifications=["AWS Certified"],
        achievements=["Dean's List"],
        hackathons=[HackathonObject(name="HackX", role="Backend Dev")],
        experience=[
            ExperienceObject(
                company="Acme Corp",
                role="Engineer",
                duration="2 years",
                description="Built things",
            )
        ],
    )


# --------------------------------------------------------------------------- #
# Test 1: valid PDF → 200 with all expected keys                              #
# --------------------------------------------------------------------------- #

async def test_valid_pdf_returns_200(sample_profile: ResumeProfile) -> None:
    """Uploading a valid PDF (by content-type) returns HTTP 200 with all profile keys."""
    transport = httpx.ASGITransport(app=app)
    with patch("app.api.routes.run_pipeline", new=AsyncMock(return_value=sample_profile)):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/parse",
                files={"file": ("resume.pdf", _SMALL_PDF_BYTES, "application/pdf")},
            )

    assert response.status_code == 200
    body = response.json()
    for key in ("projects", "technical_skills", "soft_skills", "certifications", "achievements", "hackathons", "experience"):
        assert key in body, f"Expected key '{key}' missing from response"


# --------------------------------------------------------------------------- #
# Test 2: oversized file → 413                                                #
# --------------------------------------------------------------------------- #

async def test_oversized_file_returns_413() -> None:
    """Sending a file larger than MAX_PDF_SIZE_BYTES returns HTTP 413."""
    oversized_bytes = b"x" * (MAX_PDF_SIZE_BYTES + 1)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/parse",
            files={"file": ("resume.pdf", oversized_bytes, "application/pdf")},
        )

    assert response.status_code == 413
    assert response.json()["error_code"] == "FILE_TOO_LARGE"


# --------------------------------------------------------------------------- #
# Test 3: non-PDF file → 422                                                  #
# --------------------------------------------------------------------------- #

async def test_non_pdf_returns_422() -> None:
    """Sending a plaintext file (wrong content-type and non-.pdf filename) returns HTTP 422."""
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/parse",
            files={"file": ("document.txt", b"hello world", "text/plain")},
        )

    assert response.status_code == 422
    assert response.json()["error_code"] == "INVALID_FILE_FORMAT"
