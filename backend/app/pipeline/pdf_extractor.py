"""PDF text extraction module using PyMuPDF."""
from __future__ import annotations

import fitz  # PyMuPDF

from app.config import get_settings
from app.models.errors import ErrorCode, PipelineError, PipelineStage

settings = get_settings()


def extract_text(pdf_bytes: bytes) -> str:
    """Extract text from a PDF byte stream.

    Args:
        pdf_bytes: Raw PDF file bytes

    Returns:
        Extracted text from all pages, joined with newlines

    Raises:
        PipelineError: If file is too large, invalid format, encrypted, or contains no text
    """
    # 1. Check file size
    if len(pdf_bytes) > settings.max_pdf_size_bytes:
        raise PipelineError(
            error_code=ErrorCode.FILE_TOO_LARGE,
            message=f"PDF exceeds maximum size of {settings.max_pdf_size_bytes} bytes",
            stage=PipelineStage.PDF_EXTRACTION,
        )

    # 2. Try to open as PDF
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except fitz.FileDataError as e:
        raise PipelineError(
            error_code=ErrorCode.INVALID_FILE_FORMAT,
            message=f"Invalid PDF format: {str(e)}",
            stage=PipelineStage.PDF_EXTRACTION,
        ) from e

    # 3. Check if encrypted
    if doc.is_encrypted:
        doc.close()
        raise PipelineError(
            error_code=ErrorCode.FILE_ENCRYPTED,
            message="PDF is encrypted and cannot be processed",
            stage=PipelineStage.PDF_EXTRACTION,
        )

    # 4. Extract text from all pages
    pages_text = [page.get_text("text") for page in doc]
    result = "\n".join(pages_text)
    doc.close()

    # 5. Check for empty result
    if not result.strip():
        raise PipelineError(
            error_code=ErrorCode.NO_READABLE_TEXT,
            message="PDF contains no readable text",
            stage=PipelineStage.PDF_EXTRACTION,
        )

    return result
