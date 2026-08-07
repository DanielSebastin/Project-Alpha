"""app/api/routes.py

POST /parse — accept a PDF resume and return a structured profile with
              GitHub skill confidence scores if a GitHub username is found
              or provided.

Flow:
    1. Validate PDF
    2. Parse resume via LLM → ResumeProfile (includes github_username if found)
    3. If github_username available → run GitHub verification pipeline
    4. Return combined profile + confidence scores
       OR just the ResumeProfile if no GitHub username is available
       (with a flag indicating GitHub verification was skipped)
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.models.errors import ErrorCode, ErrorResponse, PipelineError
from app.pipeline.github_pipeline import run_github_pipeline
from app.pipeline.orchestrator import run_pipeline
from app.pipeline.skill_verifier import verify_skills

logger = logging.getLogger(__name__)

router = APIRouter()

_ERROR_CODE_TO_STATUS: dict[str, int] = {
    ErrorCode.FILE_TOO_LARGE.value: 413,
    ErrorCode.INVALID_FILE_FORMAT.value: 422,
    ErrorCode.FILE_ENCRYPTED.value: 422,
    ErrorCode.NO_READABLE_TEXT.value: 422,
    ErrorCode.LLM_TIMEOUT.value: 504,
    ErrorCode.LLM_API_ERROR.value: 502,
    ErrorCode.LLM_INVALID_RESPONSE_FORMAT.value: 502,
    ErrorCode.MALFORMED_LLM_RESPONSE.value: 502,
    ErrorCode.SCHEMA_VALIDATION_ERROR.value: 502,
    ErrorCode.INTERNAL_ERROR.value: 500,
}

# Regex to extract GitHub username from a URL like https://github.com/Username/repo
_GITHUB_URL_RE = re.compile(
    r'(?:https?://)?github\.com/([A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38})',
    re.IGNORECASE,
)


def _extract_username_from_url(raw: str) -> str | None:
    """Extract GitHub username from a URL or return the raw value if it looks
    like a plain username already."""
    if not raw:
        return None
    m = _GITHUB_URL_RE.search(raw)
    if m:
        return m.group(1)
    # If no URL pattern but looks like a valid GitHub username, use as-is
    if re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}', raw.strip()):
        return raw.strip()
    return None


@router.post("/parse")
async def parse_resume(
    file: UploadFile = File(...),
    github_username: str | None = Form(default=None),
) -> JSONResponse:
    """Accept a PDF resume and return a verified profile with confidence scores.

    The endpoint works in two modes:

    Mode 1 — GitHub username auto-detected from resume:
        Upload the PDF. If the LLM finds a GitHub URL or username in the
        resume, verification runs automatically.

    Mode 2 — GitHub username provided manually:
        Pass `github_username` as an additional form field alongside the PDF.
        This overrides whatever the LLM extracts from the resume.

    Mode 3 — No GitHub info available:
        Returns just the ResumeProfile with a `github_verification` field
        set to `{"status": "skipped", "reason": "no_github_username"}`.

    Returns:
        200 on success — always. The response shape varies by mode:

        With GitHub verification:
        {
          "resume_profile": { ...ResumeProfile fields... },
          "github_verification": {
            "status": "completed",
            "username": "...",
            "matched_skills": [...],
            "unmatched_skills": [...],
            "statistics": {...}
          }
        }

        Without GitHub verification:
        {
          "resume_profile": { ...ResumeProfile fields... },
          "github_verification": {
            "status": "skipped",
            "reason": "no_github_username"
          }
        }
    """
    settings = get_settings()

    # ------------------------------------------------------------------ #
    # 1. Format + size validation                                          #
    # ------------------------------------------------------------------ #
    is_pdf = file.content_type == "application/pdf" or (file.filename or "").lower().endswith(".pdf")
    if not is_pdf:
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error_code="INVALID_FILE_FORMAT",
                message="File must be a PDF",
                stage="pre_validation",
            ).model_dump(),
        )

    pdf_bytes = await file.read()
    if len(pdf_bytes) > settings.max_pdf_size_bytes:
        return JSONResponse(
            status_code=413,
            content=ErrorResponse(
                error_code="FILE_TOO_LARGE",
                message="File exceeds 10 MB limit",
                stage="pre_validation",
            ).model_dump(),
        )

    # ------------------------------------------------------------------ #
    # 2. Parse resume via LLM                                              #
    # ------------------------------------------------------------------ #
    try:
        profile = await run_pipeline(pdf_bytes)
    except PipelineError as exc:
        error_code_str = exc.error_code.value if hasattr(exc.error_code, "value") else str(exc.error_code)
        stage_str = exc.stage.value if hasattr(exc.stage, "value") else str(exc.stage)
        return JSONResponse(
            status_code=_ERROR_CODE_TO_STATUS.get(error_code_str, 500),
            content=ErrorResponse(
                error_code=error_code_str,
                message=exc.message,
                stage=stage_str,
                details=exc.details,
            ).model_dump(),
        )

    profile_dict = profile.model_dump()

    # ------------------------------------------------------------------ #
    # 3. Resolve GitHub username                                           #
    #    Priority: manually provided > extracted from resume by LLM       #
    # ------------------------------------------------------------------ #
    resolved_username: str | None = None

    if github_username and github_username.strip():
        # Manual override — could be a URL or plain username
        resolved_username = _extract_username_from_url(github_username.strip())
        logger.info("GitHub username provided manually: '%s' → '%s'", github_username, resolved_username)
    elif profile.github_username:
        # LLM extracted it from the resume
        resolved_username = _extract_username_from_url(profile.github_username)
        logger.info("GitHub username extracted from resume: '%s' → '%s'", profile.github_username, resolved_username)

    # ------------------------------------------------------------------ #
    # 4. GitHub verification (if username is available)                   #
    # ------------------------------------------------------------------ #
    if not resolved_username:
        logger.info("No GitHub username found — skipping verification")
        return JSONResponse(
            status_code=200,
            content={
                "resume_profile": profile_dict,
                "github_verification": {
                    "status": "skipped",
                    "reason": "no_github_username",
                    "message": (
                        "No GitHub username was found in the resume. "
                        "Re-upload with the 'github_username' form field to enable verification."
                    ),
                },
            },
        )

    github_token = settings.github_token
    if not github_token or github_token == "your_github_token_here":
        logger.warning("GITHUB_TOKEN not configured — skipping verification")
        return JSONResponse(
            status_code=200,
            content={
                "resume_profile": profile_dict,
                "github_verification": {
                    "status": "skipped",
                    "reason": "github_token_not_configured",
                    "message": "GITHUB_TOKEN is not set on the server.",
                },
            },
        )

    try:
        github_data = await run_github_pipeline(resolved_username, github_token)
    except ValueError as exc:
        # User not found on GitHub — return profile without verification
        logger.warning("GitHub user '%s' not found: %s", resolved_username, exc)
        return JSONResponse(
            status_code=200,
            content={
                "resume_profile": profile_dict,
                "github_verification": {
                    "status": "failed",
                    "reason": "github_user_not_found",
                    "username": resolved_username,
                    "message": str(exc),
                },
            },
        )
    except Exception as exc:
        logger.exception("GitHub pipeline failed for username='%s'", resolved_username)
        return JSONResponse(
            status_code=200,
            content={
                "resume_profile": profile_dict,
                "github_verification": {
                    "status": "failed",
                    "reason": "github_pipeline_error",
                    "username": resolved_username,
                    "message": str(exc),
                },
            },
        )

    # ------------------------------------------------------------------ #
    # 5. Match + confidence scoring                                        #
    # ------------------------------------------------------------------ #
    verification = verify_skills(profile_dict, github_data)

    return JSONResponse(
        status_code=200,
        content={
            "resume_profile": profile_dict,
            "github_verification": {
                "status": "completed",
                "username": resolved_username,
                **verification,
            },
        },
    )
