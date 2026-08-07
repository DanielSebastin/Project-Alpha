# Implementation Plan: Resume Intelligence Engine

## Overview

Implement a Python/FastAPI backend service that accepts a PDF resume, extracts text via PyMuPDF, sends it to an LLM, and returns a validated structured JSON object — the `ResumeProfile`. The implementation follows the linear pipeline: `PDF_Extractor → LLM_Client → JSON_Builder`, orchestrated by a single endpoint.

This is a 5-day student MVP. Tasks marked `*` are optional and can be skipped to ship the working core faster.

**Pipeline scope:**
```
PDF Resume → PDF Text Extraction → LLM Processing → JSON Validation → Structured ResumeProfile JSON
```

The following are out of scope for this module: GitHub verification, skill confidence scoring, team recommendation, availability analysis.

---

## Tasks

- [x] 1. Set up project structure, dependencies, and configuration
  - Create the `backend/` directory tree: `app/`, `app/api/`, `app/pipeline/`, `app/models/`, `tests/`
  - Add `__init__.py` files to each package
  - Create `pyproject.toml` with pinned dependencies: `fastapi`, `uvicorn`, `pymupdf`, `httpx`, `pydantic`, `pydantic-settings`, `pytest`, `pytest-asyncio`, `hypothesis`
  - Create `.env.example` with `LLM_API_KEY=`, `LLM_ENDPOINT=`, `LLM_MODEL=`
  - Create `app/config.py` with the `Settings` class using `pydantic-settings` reading `LLM_API_KEY`, `LLM_ENDPOINT`, `LLM_MODEL`, `LLM_TIMEOUT`, `MAX_PDF_SIZE_BYTES`, `MAX_RETRIES` from environment variables
  - _Requirements: 2.6, 2.7_

---

- [x] 2. Implement data models and error types
  - [x] 2.1 Create `app/models/schemas.py` with `ProjectObject`, `HackathonObject`, `ExperienceObject`, and `ResumeProfile` Pydantic models
    - `ProjectObject`: `name: Optional[str] = None`, `description: Optional[str] = None`, `technologies: list[str] = []`
    - `HackathonObject`: `name: Optional[str] = None`, `role: Optional[str] = None`
    - `ExperienceObject`: `company: Optional[str] = None`, `role: Optional[str] = None`, `duration: Optional[str] = None`, `description: Optional[str] = None`
    - `ResumeProfile`: `projects: list[ProjectObject] = []`, `skills: list[str] = []`, `certifications: list[str] = []`, `achievements: list[str] = []`, `hackathons: list[HackathonObject] = []`, `experience: list[ExperienceObject] = []`
    - All optional string fields default to `None`; all list fields default to `[]`
    - Set `model_config = {"populate_by_name": True}`
    - _Requirements: 3.5, 3.6, 3.7, 3.8, 3.9, 3.10_

  - [x] 2.2 Create `app/models/errors.py` with `PipelineStage`, `ErrorCode` enums, `PipelineError` exception class, and `ErrorResponse` Pydantic model
    - `PipelineError` stores `error_code`, `message`, `stage`, and optional `details` dict
    - `ErrorResponse` has `error_code`, `message`, `stage`, `details` fields
    - _Requirements: 4.3_

---

- [x] 3. Implement PDF_Extractor
  - [x] 3.1 Create `app/pipeline/pdf_extractor.py` implementing `extract_text(pdf_bytes: bytes) -> str`
    - Check `len(pdf_bytes) <= MAX_PDF_SIZE_BYTES`; raise `PipelineError(FILE_TOO_LARGE)` if exceeded
    - Open PDF with `fitz.open(stream=pdf_bytes, filetype="pdf")`; catch `fitz.FileDataError` and raise `PipelineError(INVALID_FILE_FORMAT)`
    - Check `doc.is_encrypted`; raise `PipelineError(FILE_ENCRYPTED)` if true
    - Iterate pages, collect `page.get_text("text")`; join with `\n`
    - If result is empty/whitespace-only, raise `PipelineError(NO_READABLE_TEXT)`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 3.2 Write unit tests for PDF_Extractor
    - In `tests/test_pdf_extractor.py`: test single-page extraction, multi-page concatenation with `\n` separator, empty PDF error, image-only PDF error, non-PDF bytes error, file at exact 10 MB boundary and one byte over, encrypted PDF error
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 3.3 Write property test for PDF_Extractor — text extraction preserves all page content
    - In `tests/test_pdf_extractor.py`, use `@given(pages=st.lists(st.text(min_size=1), min_size=1, max_size=10))` to generate synthetic multi-page PDFs and assert the extracted text equals `"\n".join(pages)`
    - _Validates: Requirements 1.1, 1.2_

---

- [x] 4. Implement JSON_Builder
  - [x] 4.1 Create `app/pipeline/json_builder.py` implementing `build(raw: dict) -> ResumeProfile`, `serialize(profile: ResumeProfile) -> str`, and `deserialize(json_str: str) -> ResumeProfile`
    - `build`: call `ResumeProfile.model_validate(raw)`; catch `pydantic.ValidationError` and raise `PipelineError(SCHEMA_VALIDATION_ERROR)` with field-level details listing each failing field, its expected type, and actual value received
    - `build`: after validation, apply technology normalization (e.g. `fastapi` → `FastAPI`, `postgresql` → `PostgreSQL`, `aws` → `AWS`) to all `project.technologies` entries; promote normalized project technologies into the top-level `skills` list; deduplicate both lists using case-insensitive comparison
    - `serialize`: return `profile.model_dump_json()`
    - `deserialize`: attempt `json.loads(json_str)`; on `json.JSONDecodeError` raise `PipelineError(MALFORMED_LLM_RESPONSE)`; then call `build`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.9, 3.10, 3.11, 3.12, 3.13, 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 4.2 Write unit tests for JSON_Builder
    - Test `MALFORMED_LLM_RESPONSE` on unparseable JSON string
    - Test validated `ResumeProfile` returned on a valid dict containing projects, skills, certifications, achievements, hackathons, and experience
    - Test `SCHEMA_VALIDATION_ERROR` raised with field-level details on a wrong-typed field
    - Test technology normalization: `"fastapi"` in `project.technologies` is normalized to `"FastAPI"` and promoted to `skills`
    - Test deduplication: duplicate skills and duplicate project technologies are collapsed to a single entry
    - Test null coercion: omitted optional string fields are `None`; omitted array fields are `[]`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.9, 3.10, 3.11, 3.12, 3.13_

  - [ ]* 4.3 Write property test for JSON_Builder — null/empty coercion for missing fields
    - In `tests/test_json_builder.py`, use a `partial_resume_profile_strategy()` that generates valid dicts with random subsets of optional string fields omitted; assert every omitted string field is `None` and every omitted array field is `[]`
    - _Validates: Requirements 3.9, 3.10_

  - [ ]* 4.4 Write property test for JSON_Builder — schema validation failure reports field-level detail
    - In `tests/test_json_builder.py`, use an `invalid_resume_strategy()` generating wrong-typed or structurally broken dicts; assert `PipelineError` is raised with `error_code == SCHEMA_VALIDATION_ERROR` and `details` references each failing field by name
    - _Validates: Requirements 3.4_

  - [ ]* 4.5 Write property test for JSON_Builder — serialization round-trip identity
    - In `tests/test_json_builder.py`, use a `valid_resume_profile_strategy()` generating any combination of null/non-null fields and any-length lists of projects, hackathons, and experience; assert `deserialize(serialize(profile)) == profile`
    - _Validates: Requirements 5.1, 5.2, 5.3_

---

- [x] 5. Checkpoint — Ensure data models, extractor, and builder tests pass
  - Run all tests collected so far; confirm they pass before proceeding. Ask the user if any issues arise.

---

- [x] 6. Implement LLM_Client
  - [x] 6.1 Create `app/pipeline/llm_client.py` with `SYSTEM_PROMPT` constant and `LLMClient` class
    - `SYSTEM_PROMPT` instructs the LLM to extract `projects` (with `name`, `description`, `technologies`), `skills`, `certifications`, `achievements`, `hackathons` (with `name`, `role`), and `experience` (with `company`, `role`, `duration`, `description`) — and explicitly states that personal information (name, email, phone, college, degree, GitHub, LinkedIn, LeetCode) must NOT be extracted
    - `SYSTEM_PROMPT` instructs the LLM to return ONLY a raw JSON object with no markdown, code fences, or explanatory text; use `null` (not `""`) for absent string fields and `[]` for absent array fields
    - Constructor accepts `api_key`, `endpoint`, `model`, `timeout`; reads all values from `settings`
    - `async def parse(self, extracted_text: str) -> dict` builds the messages payload and calls LLM via `httpx.AsyncClient`
    - If the LLM provider supports structured/schema-constrained output, pass the `ResumeProfile` JSON schema in the request; otherwise strip markdown fences from the raw response before `json.loads`
    - IF `len(extracted_text)` would exceed the configured LLM context limit, split at semantic section boundaries, process each chunk, and merge results before returning
    - Implement exponential backoff: retry up to `MAX_RETRIES` times with `asyncio.sleep(2**attempt)` (1 s, 2 s, 4 s) on HTTP 4xx/5xx responses
    - Raise `PipelineError(LLM_TIMEOUT)` on `httpx.TimeoutException`, `PipelineError(LLM_API_ERROR)` after exhausted retries, `PipelineError(LLM_INVALID_RESPONSE_FORMAT)` on `json.JSONDecodeError`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12_

  - [x] 6.2 Write unit tests for LLM_Client
    - Test: 2xx JSON response returns correct dict with `projects`, `skills`, `certifications`, `achievements`, `hackathons`, `experience` keys
    - Test: 2xx non-JSON response raises `LLM_INVALID_RESPONSE_FORMAT`
    - Test: timeout raises `LLM_TIMEOUT`
    - Test: 5xx retries exactly 3 times with sleep intervals of 1 s, 2 s, 4 s (mock `asyncio.sleep`)
    - Test: markdown-fenced response (`\`\`\`json ... \`\`\``) is stripped and parsed correctly
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.12_

  - [ ]* 6.3 Write property test for LLM_Client — request always contains extracted text and system prompt
    - In `tests/test_llm_client.py`, use `@given(text=st.text(min_size=1))` with a mocked `httpx` transport; assert outgoing request body contains both `extracted_text` and `SYSTEM_PROMPT`
    - _Validates: Requirements 2.1_

---

- [x] 7. Implement Pipeline Orchestrator
  - [x] 7.1 Create `app/pipeline/orchestrator.py` implementing `async def run_pipeline(pdf_bytes: bytes) -> ResumeProfile`
    - Sequence: `extract_text` → `llm_client.parse` → `json_builder.build`
    - Wrap each stage call with `time.perf_counter()` timing
    - Emit a structured log entry per stage with keys `stage`, `status` (`"success"` or `"failure"`), `duration_ms`
    - Emit a final log entry with `total_duration_ms` on pipeline completion (success or failure)
    - Re-raise `PipelineError` from any stage without wrapping
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 7.2 Write unit tests for Pipeline Orchestrator
    - Test: all-stage success returns a `ResumeProfile` object
    - Test: `PipelineError` raised in `pdf_extraction` stage is propagated without wrapping
    - Test: `PipelineError` raised in `llm_parsing` stage is propagated without wrapping
    - Test: `PipelineError` raised in `json_building` stage is propagated without wrapping
    - _Requirements: 4.2, 4.3_

  - [ ]* 7.3 Write property test for Pipeline Orchestrator — logging captures stage metrics for every run
    - In `tests/test_orchestrator.py`, use `@given(fail_at=st.one_of(st.none(), st.sampled_from(["pdf_extraction", "llm_parsing", "json_building"])))` with mocked stages; assert log output contains one entry per executed stage with `stage`, `status`, `duration_ms` keys, plus a final entry with `total_duration_ms`
    - _Validates: Requirements 4.5_

---

- [x] 8. Implement FastAPI app and API layer
  - [x] 8.1 Create `app/main.py` with the FastAPI app factory, `JsonFormatter` structured JSON logging setup, a global exception handler that catches any unhandled exception and returns an HTTP 500 `INTERNAL_ERROR` response, and router registration
    - _Requirements: 4.3_

  - [x] 8.2 Create `app/api/routes.py` with `POST /parse` endpoint
    - Pre-pipeline validation: check `content_type == "application/pdf"` or filename ends in `.pdf`; read file bytes; reject with HTTP 413 / `FILE_TOO_LARGE` if bytes exceed `MAX_PDF_SIZE_BYTES`
    - Call `run_pipeline(pdf_bytes)`; return `ResumeProfile` as JSON with HTTP 200 on success
    - Catch `PipelineError` and return `ErrorResponse` with the appropriate HTTP status code per the error table in the design document
    - _Requirements: 4.1, 4.2, 4.3, 4.6_

  - [x] 8.3 Write integration tests for API layer
    - Test: valid PDF upload returns HTTP 200 with a JSON body containing `projects`, `skills`, `certifications`, `achievements`, `hackathons`, `experience` keys
    - Test: oversized file returns HTTP 413
    - Test: non-PDF file returns HTTP 422
    - Use `httpx.AsyncClient` with the FastAPI test app; mock `run_pipeline` for the success case
    - _Requirements: 4.1, 4.2, 4.6_

  - [ ]* 8.4 Write property test for API layer — error responses always contain required fields
    - In `tests/test_api.py`, use `@given(failing_stage=st.sampled_from(PipelineStage))` with a mocked `run_pipeline` that raises a `PipelineError` for the given stage; assert every error response body contains non-null, non-empty `error_code`, `message`, and `stage`
    - _Validates: Requirements 4.3_

---

- [x] 9. Set up shared test fixtures
  - Create `tests/conftest.py` with:
    - `synthetic_pdf(pages: list[str]) -> bytes` — builds a real PyMuPDF PDF in memory from a list of page text strings, for use in extractor tests
    - `mock_llm_response(profile_dict: dict) -> bytes` — returns a JSON-encoded bytes object mimicking a valid LLM API response body, containing `projects`, `skills`, `certifications`, `achievements`, `hackathons`, `experience`
    - `sample_resume_profile_dict` fixture — a realistic hardcoded dict representing a student hackathon participant with 2 projects (e.g. a FastAPI web app and a React dashboard), 5 skills, 1 certification, 1 achievement, 1 hackathon, and 1 experience entry
  - If Hypothesis property tests are included, register the CI profile: `settings.register_profile("ci", max_examples=50); settings.load_profile("ci")`
  - _Requirements: (supports all test tasks)_

---

- [x] 10. Final checkpoint — Ensure all tests pass
  - Run the full test suite; confirm all non-optional tests pass. Ask the user if any issues arise.

---

## Notes

- Tasks marked `*` are **optional** — skip them to hit the MVP deadline faster. Priority order for a 5-day build: Tasks 1 → 2 → 3.1 → 4.1 → 6.1 → 7.1 → 8.1 → 8.2 → 9, then add unit tests (3.2, 4.2, 6.2, 7.2, 8.3) as time allows.
- `ResumeProfile` replaces `ParsedResume` throughout. There is no `EducationObject`; education fields (college, degree) are collected during onboarding and are out of scope.
- The LLM system prompt must never instruct extraction of name, email, phone, college, degree, GitHub, LinkedIn, or LeetCode.
- `LLM_API_KEY` must never appear in source code; always read from environment via `settings`.
- Technology normalization and skill deduplication are part of `json_builder.build`, not a separate component.

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "2.2"] },
    { "id": 2, "tasks": ["3.1", "4.1"] },
    { "id": 3, "tasks": ["3.2", "4.2"] },
    { "id": 4, "tasks": ["3.3", "4.3", "4.4", "4.5", "6.1"] },
    { "id": 5, "tasks": ["6.2", "6.3", "7.1"] },
    { "id": 6, "tasks": ["7.2", "7.3", "8.1", "9"] },
    { "id": 7, "tasks": ["8.2"] },
    { "id": 8, "tasks": ["8.3", "8.4"] }
  ]
}
```
