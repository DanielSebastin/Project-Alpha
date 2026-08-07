"""app/pipeline/llm_client.py

LLM_Client — sends extracted resume text to a configured LLM API and returns
a raw Python dict ready for JSON_Builder validation.
"""
from __future__ import annotations

import asyncio
import json
import re
import logging
from typing import Any

import httpx

from app.config import get_settings
from app.models.errors import ErrorCode, PipelineError, PipelineStage
from app.models.schemas import ResumeProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a resume parser. You will receive the plain text of a resume.

Your task is to extract the following fields and return a single, valid JSON object.

The JSON object MUST conform exactly to this schema:

{
  "github_username": <string or null>,
  "projects": [
    {
      "name": <string or null>,
      "description": <string or null>,
      "technologies": [<string>, ...]
    }
  ],
  "technical_skills": [<string>, ...],
  "soft_skills": [<string>, ...],
  "certifications": [<string>, ...],
  "achievements": [<string>, ...],
  "hackathons": [
    {
      "name": <string or null>,
      "role": <string or null>
    }
  ],
  "experience": [
    {
      "company": <string or null>,
      "role": <string or null>,
      "duration": <string or null>,
      "description": <string or null>
    }
  ]
}

Rules:
- "github_username": Extract ONLY the GitHub username from the resume. If the resume contains a GitHub URL like "https://github.com/HemachandranT" or "github.com/HemachandranT/someproject", extract just the username part (e.g. "HemachandranT"). If the resume lists a GitHub username directly (e.g. "GitHub: HemachandranT"), extract that. If no GitHub information is present, use null.
- "technical_skills" means programming languages, frameworks, tools, platforms, databases, and technologies (e.g. Python, React, Docker, PostgreSQL, AWS).
- "soft_skills" means interpersonal and professional traits (e.g. Leadership, Communication, Teamwork, Problem Solving).
- If a skill could be either, prefer "technical_skills".
- "experience" means ONLY paid work experience, internships, part-time jobs, and freelance work at companies or organisations. Do NOT put colleges, universities, schools, or any educational institutions in "experience" — education is out of scope and must be completely ignored.
- Use null (not empty string "") for any string field not present in the resume.
- Use [] for any array field not present in the resume.
- Do NOT invent or infer information not explicitly present in the resume.
- Return ONLY the raw JSON object — no markdown, no code fences, no explanations.
"""

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Approximate token budget for a single LLM request.  We use a conservative
# character-based heuristic (1 token ≈ 4 characters) to decide when to chunk.
# The default of 6 000 tokens → 24 000 chars leaves headroom for the system
# prompt and response even with a 8 k-token model.
_DEFAULT_CONTEXT_CHARS: int = 24_000

# Section-header patterns used for semantic splitting.
_SECTION_BOUNDARY_RE = re.compile(
    r"(?=\n(?:EXPERIENCE|EDUCATION|SKILLS|PROJECTS|CERTIFICATIONS|"
    r"ACHIEVEMENTS|HACKATHONS|WORK EXPERIENCE|PROFESSIONAL EXPERIENCE|"
    r"SUMMARY|OBJECTIVE|AWARDS|VOLUNTEERING)[^\n]*\n)",
    re.IGNORECASE,
)

# Regex to strip markdown code fences that some LLMs wrap their JSON in.
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _strip_markdown_fences(text: str) -> str:
    """Remove leading/trailing markdown code fences from *text*."""
    return _FENCE_RE.sub("", text).strip()


def _split_text(text: str, max_chars: int) -> list[str]:
    """Split *text* into chunks ≤ *max_chars* at semantic section boundaries.

    If no section header is found, falls back to splitting on blank lines, and
    finally on raw character boundaries as a last resort.
    """
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    remaining = text

    while len(remaining) > max_chars:
        # Try splitting at a section boundary within the allowed window.
        window = remaining[:max_chars]
        match = None
        for m in _SECTION_BOUNDARY_RE.finditer(window):
            if m.start() > 0:
                match = m

        if match:
            split_at = match.start()
        else:
            # Fallback: split at the last blank line within the window.
            last_blank = window.rfind("\n\n")
            if last_blank > 0:
                split_at = last_blank
            else:
                # Hard split at max_chars as absolute last resort.
                split_at = max_chars

        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]

    if remaining:
        chunks.append(remaining)

    return chunks


def _merge_profiles(profiles: list[dict]) -> dict:
    """Merge multiple partial profile dicts into one by combining all lists."""
    merged: dict[str, Any] = {
        "github_username": None,
        "projects": [],
        "technical_skills": [],
        "soft_skills": [],
        "certifications": [],
        "achievements": [],
        "hackathons": [],
        "experience": [],
    }

    seen_technical: set[str] = set()
    seen_soft: set[str] = set()

    for profile in profiles:
        # Take first non-null github_username found
        if merged["github_username"] is None and profile.get("github_username"):
            merged["github_username"] = profile["github_username"]

        for key in ("projects", "certifications", "achievements", "hackathons", "experience"):
            items = profile.get(key)
            if isinstance(items, list):
                merged[key].extend(items)

        for skill in profile.get("technical_skills") or []:
            if isinstance(skill, str) and skill.lower() not in seen_technical:
                seen_technical.add(skill.lower())
                merged["technical_skills"].append(skill)

        for skill in profile.get("soft_skills") or []:
            if isinstance(skill, str) and skill.lower() not in seen_soft:
                seen_soft.add(skill.lower())
                merged["soft_skills"].append(skill)

    return merged


# ---------------------------------------------------------------------------
# LLMClient
# ---------------------------------------------------------------------------


class LLMClient:
    """Async client that calls an OpenAI-compatible LLM API."""

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key: str = api_key or settings.llm_api_key
        self._endpoint: str = endpoint or settings.llm_endpoint
        self._model: str = model or settings.llm_model
        self._timeout: float = timeout if timeout is not None else settings.llm_timeout
        self._max_retries: int = settings.max_retries
        # Derive the JSON schema for structured output from the Pydantic model.
        self._response_schema: dict = ResumeProfile.model_json_schema()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def parse(self, extracted_text: str) -> dict:
        """Send *extracted_text* to the LLM and return a parsed dict.

        Handles chunking for long texts, exponential backoff on errors, and
        markdown fence stripping.

        Raises:
            PipelineError(LLM_TIMEOUT)                 — on timeout
            PipelineError(LLM_API_ERROR)                — after exhausted retries
            PipelineError(LLM_INVALID_RESPONSE_FORMAT)  — on JSON parse failure
        """
        chunks = _split_text(extracted_text, _DEFAULT_CONTEXT_CHARS)

        if len(chunks) == 1:
            return await self._parse_chunk(chunks[0])

        # Process each chunk independently then merge.
        partial_profiles: list[dict] = []
        for chunk in chunks:
            partial = await self._parse_chunk(chunk)
            partial_profiles.append(partial)

        return _merge_profiles(partial_profiles)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_payload(self, text: str) -> dict:
        """Build the JSON request payload for the LLM API."""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Resume text:\n{text}"},
        ]
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
        }

        # Request schema-constrained JSON output only for providers that support
        # it (OpenAI). Groq and similar providers don't support "json_schema"
        # structured output — for those, the system prompt's "raw JSON only"
        # instruction + markdown fence stripping is the fallback.
        if "groq.com" not in self._endpoint:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "ResumeProfile",
                    "strict": True,
                    "schema": self._response_schema,
                },
            }

        return payload

    async def _call_llm(self, payload: dict) -> str:
        """Make the HTTP POST to the LLM endpoint with exponential backoff.

        Returns the raw response text on success.

        Raises:
            PipelineError(LLM_TIMEOUT)    — on httpx.TimeoutException
            PipelineError(LLM_API_ERROR)  — after max retries on 4xx/5xx
        """
        last_status: int = 0
        last_body: str = ""

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for attempt in range(self._max_retries):
                try:
                    response = await client.post(
                        self._endpoint,
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                    )
                except httpx.TimeoutException as exc:
                    raise PipelineError(
                        error_code=ErrorCode.LLM_TIMEOUT,
                        message="LLM API request timed out.",
                        stage=PipelineStage.LLM_PARSING,
                    ) from exc

                if response.is_success:
                    return response.text

                # 4xx / 5xx — back off and retry.
                last_status = response.status_code
                last_body = response.text
                logger.warning(
                    "LLM API error on attempt %d/%d: HTTP %d",
                    attempt + 1,
                    self._max_retries,
                    last_status,
                )

                if attempt < self._max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        raise PipelineError(
            error_code=ErrorCode.LLM_API_ERROR,
            message=(
                f"LLM API returned HTTP {last_status} after "
                f"{self._max_retries} retries."
            ),
            stage=PipelineStage.LLM_PARSING,
            details={"last_status": last_status, "last_body": last_body[:500]},
        )

    async def _extract_content(self, raw_response: str) -> str:
        """Extract the LLM message content string from a raw API response.

        Tries to parse the response as an OpenAI chat completion envelope first.
        If that fails, treats the whole response body as the content directly.
        """
        try:
            envelope = json.loads(raw_response)
            content: str = envelope["choices"][0]["message"]["content"]
            return content
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            # Provider may return the JSON payload directly (non-OpenAI format).
            return raw_response

    async def _parse_chunk(self, text: str) -> dict:
        """Send a single chunk to the LLM and return a parsed dict."""
        payload = self._build_payload(text)
        raw_response = await self._call_llm(payload)

        content = await self._extract_content(raw_response)

        # Strip markdown fences in case the provider doesn't honour the prompt.
        cleaned = _strip_markdown_fences(content)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise PipelineError(
                error_code=ErrorCode.LLM_INVALID_RESPONSE_FORMAT,
                message="LLM response could not be parsed as JSON.",
                stage=PipelineStage.LLM_PARSING,
                details={"raw_content": content[:500]},
            ) from exc
