"""tests/test_llm_client.py

Unit tests for LLMClient class.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.models.errors import ErrorCode, PipelineError
from app.pipeline.llm_client import LLMClient


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------


def make_mock_settings():
    """Create a mock Settings object for testing."""
    s = MagicMock()
    s.llm_api_key = "test-key"
    s.llm_endpoint = "https://api.example.com/v1/chat/completions"
    s.llm_model = "gpt-4o-mini"
    s.llm_timeout = 30.0
    s.max_retries = 3
    return s


def openai_response(content: str, status_code: int = 200) -> httpx.Response:
    """Build an OpenAI-style chat completion response."""
    body = json.dumps({
        "choices": [{"message": {"content": content}}]
    })
    return httpx.Response(status_code=status_code, text=body, request=MagicMock())


def make_mock_client(responses):
    """Create a mock httpx.AsyncClient that returns responses in order.
    
    Args:
        responses: list of httpx.Response objects or exceptions to raise
    """
    mock_client = AsyncMock()
    
    # Handle both responses and exceptions
    if isinstance(responses, list):
        mock_client.post = AsyncMock(side_effect=responses)
    else:
        mock_client.post = AsyncMock(side_effect=[responses])
    
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


@patch("app.pipeline.llm_client.get_settings", return_value=make_mock_settings())
@patch("app.pipeline.llm_client.httpx.AsyncClient")
async def test_2xx_json_response_returns_correct_dict(mock_async_client_class, mock_get_settings):
    """Test that a 200 response with valid JSON returns the correct dict."""
    # Prepare a valid JSON response with all six required keys
    valid_json = {
        "projects": [{"name": "Test Project", "description": "A test", "technologies": ["Python"]}],
        "skills": ["Python", "JavaScript"],
        "certifications": ["AWS Certified"],
        "achievements": ["Won hackathon"],
        "hackathons": [{"name": "HackComp 2024", "role": "Participant"}],
        "experience": [{"company": "Tech Corp", "role": "Engineer", "duration": "2 years", "description": "Built APIs"}]
    }
    
    response = openai_response(json.dumps(valid_json), status_code=200)
    mock_client = make_mock_client([response])
    mock_async_client_class.return_value = mock_client
    
    client = LLMClient()
    result = await client.parse("Sample resume text")
    
    # Assert all six keys are present
    assert "projects" in result
    assert "skills" in result
    assert "certifications" in result
    assert "achievements" in result
    assert "hackathons" in result
    assert "experience" in result
    
    # Verify values match what we sent
    assert result["projects"] == valid_json["projects"]
    assert result["skills"] == valid_json["skills"]
    assert result["certifications"] == valid_json["certifications"]
    assert result["achievements"] == valid_json["achievements"]
    assert result["hackathons"] == valid_json["hackathons"]
    assert result["experience"] == valid_json["experience"]


@patch("app.pipeline.llm_client.get_settings", return_value=make_mock_settings())
@patch("app.pipeline.llm_client.httpx.AsyncClient")
async def test_2xx_non_json_response_raises_invalid_format(mock_async_client_class, mock_get_settings):
    """Test that a 200 response with non-JSON content raises LLM_INVALID_RESPONSE_FORMAT."""
    # Return a 200 response with invalid JSON
    response = openai_response("This is not valid JSON at all!", status_code=200)
    mock_client = make_mock_client([response])
    mock_async_client_class.return_value = mock_client
    
    client = LLMClient()
    
    with pytest.raises(PipelineError) as exc_info:
        await client.parse("Sample resume text")
    
    assert exc_info.value.error_code == ErrorCode.LLM_INVALID_RESPONSE_FORMAT


@patch("app.pipeline.llm_client.get_settings", return_value=make_mock_settings())
@patch("app.pipeline.llm_client.httpx.AsyncClient")
async def test_timeout_raises_llm_timeout(mock_async_client_class, mock_get_settings):
    """Test that httpx.TimeoutException raises LLM_TIMEOUT."""
    # Configure mock to raise TimeoutException
    mock_client = make_mock_client([httpx.TimeoutException("Request timed out")])
    mock_async_client_class.return_value = mock_client
    
    client = LLMClient()
    
    with pytest.raises(PipelineError) as exc_info:
        await client.parse("Sample resume text")
    
    assert exc_info.value.error_code == ErrorCode.LLM_TIMEOUT


@patch("app.pipeline.llm_client.get_settings", return_value=make_mock_settings())
@patch("app.pipeline.llm_client.httpx.AsyncClient")
@patch("app.pipeline.llm_client.asyncio.sleep")
async def test_5xx_retries_three_times_with_correct_sleep_intervals(
    mock_sleep, mock_async_client_class, mock_get_settings
):
    """Test that 5xx errors trigger exactly 3 retries with exponential backoff."""
    # Return 500 error three times
    error_response = httpx.Response(
        status_code=500,
        text="Internal Server Error",
        request=MagicMock()
    )
    mock_client = make_mock_client([error_response, error_response, error_response])
    mock_async_client_class.return_value = mock_client
    
    client = LLMClient()
    
    with pytest.raises(PipelineError) as exc_info:
        await client.parse("Sample resume text")
    
    # Verify error code
    assert exc_info.value.error_code == ErrorCode.LLM_API_ERROR
    
    # Verify post was called exactly 3 times
    assert mock_client.post.call_count == 3
    
    # Verify sleep was called exactly 2 times with correct intervals
    # With max_retries=3 and attempts 0,1,2:
    # - After attempt 0 (first failure): sleep(2^0) = sleep(1)
    # - After attempt 1 (second failure): sleep(2^1) = sleep(2)
    # - After attempt 2 (third failure): no sleep (exhausted retries)
    assert mock_sleep.call_count == 2
    sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
    assert sleep_calls == [1, 2]


@patch("app.pipeline.llm_client.get_settings", return_value=make_mock_settings())
@patch("app.pipeline.llm_client.httpx.AsyncClient")
async def test_markdown_fenced_response_is_stripped_and_parsed(mock_async_client_class, mock_get_settings):
    """Test that markdown code fences are stripped before JSON parsing."""
    # Prepare JSON wrapped in markdown code fences
    json_content = {
        "projects": [],
        "skills": ["Python"],
        "certifications": [],
        "achievements": [],
        "hackathons": [],
        "experience": []
    }
    
    fenced_content = f"""```json
{json.dumps(json_content)}
```"""
    
    response = openai_response(fenced_content, status_code=200)
    mock_client = make_mock_client([response])
    mock_async_client_class.return_value = mock_client
    
    client = LLMClient()
    result = await client.parse("Sample resume text")
    
    # Assert the fences were stripped and JSON was parsed correctly
    assert result == json_content
    assert result["skills"] == ["Python"]
    assert result["projects"] == []
