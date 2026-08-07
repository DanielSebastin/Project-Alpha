"""app/api/routes.py

POST /parse — accept a PDF upload and return a structured ResumeProfile.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.models.errors import ErrorCode, ErrorResponse, PipelineError
from app.pipeline.orchestrator import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()

# Mapping from ErrorCode string values to HTTP status codes
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


@router.post("/parse")
async def parse_resume(file: UploadFile = File(...)) -> JSONResponse:
    """Accept a PDF resume and return a structured ResumeProfile JSON.

    Pre-pipeline validation:
        1. Content-type or filename must indicate a PDF.
        2. File size must not exceed the configured limit.

    Returns:
        200 with ResumeProfile JSON on success.
        4xx/5xx with ErrorResponse JSON on failure.
    """
    settings = get_settings()

    # ------------------------------------------------------------------ #
    # 1. Format validation                                                 #
    # ------------------------------------------------------------------ #
    is_pdf_content_type = file.content_type == "application/pdf"
    is_pdf_filename = (file.filename or "").lower().endswith(".pdf")

    if not (is_pdf_content_type or is_pdf_filename):
        body = ErrorResponse(
            error_code="INVALID_FILE_FORMAT",
            message="File must be a PDF",
            stage="pre_validation",
        )
        return JSONResponse(status_code=422, content=body.model_dump())

    # ------------------------------------------------------------------ #
    # 2. Size validation                                                   #
    # ------------------------------------------------------------------ #
    pdf_bytes = await file.read()

    if len(pdf_bytes) > settings.max_pdf_size_bytes:
        body = ErrorResponse(
            error_code="FILE_TOO_LARGE",
            message="File exceeds 10 MB limit",
            stage="pre_validation",
        )
        return JSONResponse(status_code=413, content=body.model_dump())

    # ------------------------------------------------------------------ #
    # 3. Pipeline execution                                                #
    # ------------------------------------------------------------------ #
    try:
        profile = await run_pipeline(pdf_bytes)
        return JSONResponse(content=profile.model_dump(), status_code=200)
    except PipelineError as exc:
        error_code_str = (
            exc.error_code.value
            if hasattr(exc.error_code, "value")
            else str(exc.error_code)
        )
        status_code = _ERROR_CODE_TO_STATUS.get(error_code_str, 500)
        stage_str = (
            exc.stage.value if hasattr(exc.stage, "value") else str(exc.stage)
        )
        body = ErrorResponse(
            error_code=error_code_str,
            message=exc.message,
            stage=stage_str,
            details=exc.details,
        )
        return JSONResponse(status_code=status_code, content=body.model_dump())
