"""app/pipeline/orchestrator.py

Top-level pipeline orchestrator: wires pdf_extractor → llm_client → json_builder
and emits structured timing/status logs for each stage.
"""
from __future__ import annotations

import logging
import time

from app.config import get_settings
from app.models.errors import PipelineError
from app.models.schemas import ResumeProfile
from app.pipeline import json_builder, pdf_extractor
from app.pipeline.llm_client import LLMClient

logger = logging.getLogger(__name__)


async def run_pipeline(pdf_bytes: bytes) -> ResumeProfile:
    """Execute the full resume-parsing pipeline.

    Stages (in order):
        1. pdf_extraction  — extract_text(pdf_bytes) -> str
        2. llm_parsing     — LLMClient.parse(text)   -> dict
        3. json_building   — json_builder.build(raw)  -> ResumeProfile

    Each stage is timed and a structured log entry is emitted on completion
    (success or failure).  A final ``pipeline_complete`` entry is always emitted
    with the total wall-clock duration.

    Raises:
        PipelineError: Any error raised by a stage is re-raised unchanged.
    """
    settings = get_settings()
    pipeline_start = time.perf_counter()
    final_status = "success"
    error_code = None

    try:
        # ------------------------------------------------------------------ #
        # Stage 1 — PDF extraction                                            #
        # ------------------------------------------------------------------ #
        t0 = time.perf_counter()
        try:
            extracted_text = pdf_extractor.extract_text(pdf_bytes)
            duration_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "stage_complete",
                extra={"extra": {"stage": "pdf_extraction", "status": "success", "duration_ms": duration_ms}},
            )
        except PipelineError as exc:
            duration_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "stage_complete",
                extra={"extra": {"stage": "pdf_extraction", "status": "failure", "duration_ms": duration_ms}},
            )
            raise

        # ------------------------------------------------------------------ #
        # Stage 2 — LLM parsing                                               #
        # ------------------------------------------------------------------ #
        client = LLMClient(
            api_key=settings.llm_api_key,
            endpoint=settings.llm_endpoint,
            model=settings.llm_model,
            timeout=settings.llm_timeout,
        )

        t0 = time.perf_counter()
        try:
            raw_dict = await client.parse(extracted_text)
            duration_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "stage_complete",
                extra={"extra": {"stage": "llm_parsing", "status": "success", "duration_ms": duration_ms}},
            )
        except PipelineError as exc:
            duration_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "stage_complete",
                extra={"extra": {"stage": "llm_parsing", "status": "failure", "duration_ms": duration_ms}},
            )
            raise

        # ------------------------------------------------------------------ #
        # Stage 3 — JSON building / schema validation                         #
        # ------------------------------------------------------------------ #
        t0 = time.perf_counter()
        try:
            profile = json_builder.build(raw_dict)
            duration_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "stage_complete",
                extra={"extra": {"stage": "json_building", "status": "success", "duration_ms": duration_ms}},
            )
        except PipelineError as exc:
            duration_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "stage_complete",
                extra={"extra": {"stage": "json_building", "status": "failure", "duration_ms": duration_ms}},
            )
            raise

    except PipelineError as exc:
        final_status = "failure"
        error_code = exc.error_code.value
        raise
    finally:
        total_duration_ms = (time.perf_counter() - pipeline_start) * 1000
        logger.info(
            "pipeline_complete",
            extra={"extra": {"status": final_status, "total_duration_ms": total_duration_ms, "error_code": error_code}},
        )

    return profile
