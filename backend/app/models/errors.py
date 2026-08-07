from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class PipelineStage(str, Enum):
    PRE_VALIDATION = "pre_validation"
    PDF_EXTRACTION = "pdf_extraction"
    LLM_PARSING = "llm_parsing"
    JSON_BUILDING = "json_building"


class ErrorCode(str, Enum):
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    INVALID_FILE_FORMAT = "INVALID_FILE_FORMAT"
    FILE_ENCRYPTED = "FILE_ENCRYPTED"
    NO_READABLE_TEXT = "NO_READABLE_TEXT"
    LLM_API_ERROR = "LLM_API_ERROR"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_INVALID_RESPONSE_FORMAT = "LLM_INVALID_RESPONSE_FORMAT"
    MALFORMED_LLM_RESPONSE = "MALFORMED_LLM_RESPONSE"
    SCHEMA_VALIDATION_ERROR = "SCHEMA_VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class PipelineError(Exception):
    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        stage: PipelineStage,
        details: dict | None = None,
    ):
        self.error_code = error_code
        self.message = message
        self.stage = stage
        self.details = details or {}
        super().__init__(message)


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    stage: str
    details: dict = {}
