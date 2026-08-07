"""tests/test_orchestrator.py

Unit tests for app.pipeline.orchestrator.run_pipeline.

Covers:
  - All stages succeed → ResumeProfile returned
  - PipelineError from pdf_extraction propagates unchanged
  - PipelineError from llm_parsing propagates unchanged
  - PipelineError from json_building propagates unchanged
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.errors import ErrorCode, PipelineError, PipelineStage
from app.models.schemas import ResumeProfile
from app.pipeline.orchestrator import run_pipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_PDF_BYTES = b"%PDF-1.4 fake bytes"
_SAMPLE_TEXT = "John Doe — Software Engineer\nSkills: Python, FastAPI"
_SAMPLE_RAW_DICT = {
    "projects": [],
    "technical_skills": ["Python", "FastAPI"],
    "soft_skills": [],
    "certifications": [],
    "achievements": [],
    "hackathons": [],
    "experience": [],
}
_SAMPLE_PROFILE = ResumeProfile(technical_skills=["Python", "FastAPI"])


# ---------------------------------------------------------------------------
# Test: all stages succeed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_pipeline_success():
    """run_pipeline returns a ResumeProfile when every stage succeeds."""
    with (
        patch("app.pipeline.orchestrator.pdf_extractor.extract_text", return_value=_SAMPLE_TEXT) as mock_extract,
        patch("app.pipeline.orchestrator.LLMClient") as MockLLMClient,
        patch("app.pipeline.orchestrator.json_builder.build", return_value=_SAMPLE_PROFILE) as mock_build,
    ):
        mock_client_instance = AsyncMock()
        mock_client_instance.parse = AsyncMock(return_value=_SAMPLE_RAW_DICT)
        MockLLMClient.return_value = mock_client_instance

        result = await run_pipeline(_SAMPLE_PDF_BYTES)

    assert isinstance(result, ResumeProfile)
    assert result.technical_skills == ["Python", "FastAPI"]
    mock_extract.assert_called_once_with(_SAMPLE_PDF_BYTES)
    mock_client_instance.parse.assert_called_once_with(_SAMPLE_TEXT)
    mock_build.assert_called_once_with(_SAMPLE_RAW_DICT)


# ---------------------------------------------------------------------------
# Test: PipelineError from pdf_extraction propagates unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_pipeline_pdf_extraction_error_propagates():
    """PipelineError raised by extract_text is re-raised without wrapping."""
    original_error = PipelineError(
        error_code=ErrorCode.NO_READABLE_TEXT,
        message="PDF contains no readable text",
        stage=PipelineStage.PDF_EXTRACTION,
    )

    with (
        patch("app.pipeline.orchestrator.pdf_extractor.extract_text", side_effect=original_error),
        patch("app.pipeline.orchestrator.LLMClient"),
        patch("app.pipeline.orchestrator.json_builder.build"),
    ):
        with pytest.raises(PipelineError) as exc_info:
            await run_pipeline(_SAMPLE_PDF_BYTES)

    raised = exc_info.value
    # Must be the exact same object (not a re-wrapped copy)
    assert raised is original_error
    assert raised.error_code is ErrorCode.NO_READABLE_TEXT
    assert raised.stage is PipelineStage.PDF_EXTRACTION


# ---------------------------------------------------------------------------
# Test: PipelineError from llm_parsing propagates unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_pipeline_llm_parsing_error_propagates():
    """PipelineError raised by LLMClient.parse is re-raised without wrapping."""
    original_error = PipelineError(
        error_code=ErrorCode.LLM_TIMEOUT,
        message="LLM API request timed out.",
        stage=PipelineStage.LLM_PARSING,
    )

    with (
        patch("app.pipeline.orchestrator.pdf_extractor.extract_text", return_value=_SAMPLE_TEXT),
        patch("app.pipeline.orchestrator.LLMClient") as MockLLMClient,
        patch("app.pipeline.orchestrator.json_builder.build"),
    ):
        mock_client_instance = AsyncMock()
        mock_client_instance.parse = AsyncMock(side_effect=original_error)
        MockLLMClient.return_value = mock_client_instance

        with pytest.raises(PipelineError) as exc_info:
            await run_pipeline(_SAMPLE_PDF_BYTES)

    raised = exc_info.value
    assert raised is original_error
    assert raised.error_code is ErrorCode.LLM_TIMEOUT
    assert raised.stage is PipelineStage.LLM_PARSING


# ---------------------------------------------------------------------------
# Test: PipelineError from json_building propagates unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_pipeline_json_building_error_propagates():
    """PipelineError raised by json_builder.build is re-raised without wrapping."""
    original_error = PipelineError(
        error_code=ErrorCode.SCHEMA_VALIDATION_ERROR,
        message="Schema validation failed: 1 error(s)",
        stage=PipelineStage.JSON_BUILDING,
    )

    with (
        patch("app.pipeline.orchestrator.pdf_extractor.extract_text", return_value=_SAMPLE_TEXT),
        patch("app.pipeline.orchestrator.LLMClient") as MockLLMClient,
        patch("app.pipeline.orchestrator.json_builder.build", side_effect=original_error),
    ):
        mock_client_instance = AsyncMock()
        mock_client_instance.parse = AsyncMock(return_value=_SAMPLE_RAW_DICT)
        MockLLMClient.return_value = mock_client_instance

        with pytest.raises(PipelineError) as exc_info:
            await run_pipeline(_SAMPLE_PDF_BYTES)

    raised = exc_info.value
    assert raised is original_error
    assert raised.error_code is ErrorCode.SCHEMA_VALIDATION_ERROR
    assert raised.stage is PipelineStage.JSON_BUILDING
