"""Unit tests for app/pipeline/pdf_extractor.py"""
from __future__ import annotations

from unittest.mock import patch

import fitz
import pytest

from app.models.errors import ErrorCode, PipelineError
from app.pipeline.pdf_extractor import extract_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_pdf(pages: list[str]) -> bytes:
    """Build a minimal PDF in-memory with one text insertion per page."""
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    buf = doc.tobytes()
    doc.close()
    return buf


def make_encrypted_pdf() -> bytes:
    """Build a password-protected PDF."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "secret")
    buf = doc.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw="pw",
        owner_pw="pw",
    )
    doc.close()
    return buf


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_single_page_extraction():
    """A single-page PDF returns the inserted text."""
    text = "Hello, resume!"
    pdf_bytes = make_pdf([text])
    result = extract_text(pdf_bytes)
    assert text in result


def test_multi_page_concatenation():
    """Two-page PDF: text from both pages is included, separated by a newline."""
    page1 = "First page content"
    page2 = "Second page content"
    pdf_bytes = make_pdf([page1, page2])
    result = extract_text(pdf_bytes)
    assert page1 in result
    assert page2 in result
    # page1 must appear before page2 in the joined output
    assert result.index(page1) < result.index(page2)


def test_empty_pdf_raises():
    """A PDF with one blank page raises NO_READABLE_TEXT."""
    pdf_bytes = make_pdf([""])  # blank page
    with pytest.raises(PipelineError) as exc_info:
        extract_text(pdf_bytes)
    assert exc_info.value.error_code == ErrorCode.NO_READABLE_TEXT


def test_non_pdf_bytes_raises():
    """Random bytes that are not a PDF raise INVALID_FILE_FORMAT."""
    with pytest.raises(PipelineError) as exc_info:
        extract_text(b"not a pdf")
    assert exc_info.value.error_code == ErrorCode.INVALID_FILE_FORMAT


def test_exact_size_boundary_passes():
    """A PDF whose byte-length exactly equals max_pdf_size_bytes is accepted."""
    small_pdf = make_pdf(["boundary test"])
    # Patch the settings object used inside the module so max == len(pdf)
    with patch("app.pipeline.pdf_extractor.settings") as mock_settings:
        mock_settings.max_pdf_size_bytes = len(small_pdf)
        # Should not raise
        result = extract_text(small_pdf)
    assert "boundary test" in result


def test_one_byte_over_size_raises():
    """A PDF one byte larger than the limit raises FILE_TOO_LARGE."""
    small_pdf = make_pdf(["boundary test"])
    with patch("app.pipeline.pdf_extractor.settings") as mock_settings:
        mock_settings.max_pdf_size_bytes = len(small_pdf) - 1
        with pytest.raises(PipelineError) as exc_info:
            extract_text(small_pdf)
    assert exc_info.value.error_code == ErrorCode.FILE_TOO_LARGE


def test_encrypted_pdf_raises():
    """An encrypted PDF raises FILE_ENCRYPTED."""
    enc_pdf = make_encrypted_pdf()
    with pytest.raises(PipelineError) as exc_info:
        extract_text(enc_pdf)
    assert exc_info.value.error_code == ErrorCode.FILE_ENCRYPTED
