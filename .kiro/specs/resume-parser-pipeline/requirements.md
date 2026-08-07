# Requirements Document

## Introduction

The Resume Intelligence Engine is a backend module of the Hackathon Team Formation Platform. Its sole responsibility is to accept a participant's resume in PDF format, extract raw text using PyMuPDF, send the text to a Large Language Model (LLM), validate the LLM response against a predefined schema, and return a structured JSON object containing the participant's technical profile.

The engine operates as a self-contained pipeline with the following stages:

```
PDF Resume
    ↓
PDF Text Extraction
    ↓
LLM Processing
    ↓
JSON Validation
    ↓
Structured Resume JSON
```

The following concerns are explicitly out of scope for this module: GitHub verification, repository analysis, skill confidence scoring, technology verification, team recommendation logic, availability analysis, and personality assessment. Personal profile information (name, email, college, degree, year of study, GitHub profile, LinkedIn profile, LeetCode profile, availability) is collected separately during onboarding and is not extracted by this engine.

## Glossary

- **Pipeline**: The end-to-end processing flow: PDF input → text extraction → LLM processing → JSON validation → structured JSON output
- **PDF_Extractor**: The component responsible for extracting plain text from PDF files using PyMuPDF
- **LLM_Client**: The component responsible for sending extracted text to the LLM API and receiving a structured response
- **JSON_Builder**: The component responsible for validating and serializing the LLM response into a well-defined JSON schema
- **Resume**: A PDF document containing a participant's projects, skills, experience, certifications, achievements, and hackathon history
- **Extracted_Text**: The raw plain text content obtained from a Resume PDF by the PDF_Extractor
- **Resume_Profile**: The structured JSON object produced at the end of the Pipeline
- **Schema**: The JSON schema that defines the expected structure of the Resume_Profile output

---

## Requirements

### Requirement 1: PDF Text Extraction

**User Story:** As a backend service, I want to extract plain text from an uploaded resume PDF, so that the text can be passed to the LLM for structured parsing.

#### Acceptance Criteria

1. WHEN a valid PDF file is provided, THE PDF_Extractor SHALL extract all machine-readable text from every page of the PDF and return it as a single Extracted_Text string.
2. WHEN a multi-page PDF is provided, THE PDF_Extractor SHALL concatenate text from all pages in page-order into the Extracted_Text string, separated by a newline character (`\n`) between pages.
3. IF a PDF file is empty, contains no machine-readable text, or consists solely of scanned images with no embedded text layer, THEN THE PDF_Extractor SHALL return an error response indicating the file contains no readable content.
4. IF a provided file is not a valid PDF, THEN THE PDF_Extractor SHALL return an error response indicating the file format is invalid.
5. IF the PDF file exceeds 10 MB in size, THEN THE PDF_Extractor SHALL reject the file and return an error response indicating the file size limit has been exceeded.
6. IF a PDF file is password-protected or encrypted, THEN THE PDF_Extractor SHALL return an error response indicating the file is protected and cannot be processed.

---

### Requirement 2: LLM-Based Resume Parsing

**User Story:** As a backend service, I want to send extracted resume text to an LLM, so that the LLM can identify and structure technical profile fields into a consistent format.

#### Acceptance Criteria

1. WHEN text extraction completes successfully, THE LLM_Client SHALL send the Extracted_Text to the configured LLM API endpoint using a predefined system prompt that instructs the LLM to return a structured JSON object containing the participant's projects, technical skills, certifications, achievements, hackathon participation, and work experience.
2. WHEN the LLM API returns an HTTP 2xx response with a parseable JSON body, THE LLM_Client SHALL extract the JSON payload from the response and pass it to the JSON_Builder.
3. IF the LLM API returns an HTTP 2xx response but the response body is not parseable as JSON, THEN THE LLM_Client SHALL return an error response to the Pipeline indicating an invalid LLM response format.
4. IF the LLM API returns an error response (HTTP 4xx or 5xx), THEN THE LLM_Client SHALL retry the request up to 3 times with exponential backoff (1 s, 2 s, 4 s) before returning an error response to the Pipeline.
5. IF the LLM API does not respond within 30 seconds, THEN THE LLM_Client SHALL cancel the request and return a timeout error response to the Pipeline.
6. THE LLM_Client SHALL read the LLM API key from an environment variable.
7. THE LLM_Client SHALL NOT hard-code credentials or API keys in source code.
8. THE LLM_Client SHALL transmit the complete Extracted_Text to the LLM without truncation whenever the text fits within the context length supported by the configured LLM.
9. IF the Extracted_Text exceeds the context length supported by the configured LLM, THEN THE LLM_Client SHALL apply a chunking strategy that splits the text at semantic boundaries (e.g., section breaks or paragraph boundaries) to preserve continuity, process each chunk independently, and merge the resulting structured outputs into a single Resume_Profile before passing it to the JSON_Builder.
10. THE LLM_Client SHALL request schema-constrained JSON output using the structured output mechanism provided by the configured LLM provider, where such a mechanism is supported.
11. THE LLM response SHALL contain only the expected JSON payload, with no explanatory text, markdown formatting, or code fences.
12. IF the configured LLM provider does not support schema-constrained output, THEN THE LLM_Client SHALL sanitize the raw response by stripping any surrounding markdown fences or non-JSON content before forwarding it to the JSON_Builder.

---

### Requirement 3: JSON Output Validation and Schema Compliance

**User Story:** As a consumer of the pipeline, I want the parsed resume profile to conform to a defined JSON schema, so that downstream systems can reliably process the structured data for team formation.

#### Acceptance Criteria

1. THE JSON_Builder SHALL validate the LLM response against the Resume_Profile Schema before returning the output.
2. WHEN the LLM response conforms to the Schema, THE JSON_Builder SHALL return a validated Resume_Profile JSON object.
3. IF the LLM response is not valid JSON (i.e., cannot be parsed), THEN THE JSON_Builder SHALL return an error response indicating a malformed LLM response before performing schema validation.
4. IF the LLM response is valid JSON but does not conform to the Schema, THEN THE JSON_Builder SHALL return an error response that lists each field that failed validation along with the expected type and the actual value received.
5. THE Resume_Profile Schema SHALL include the following top-level fields: `projects` (array of objects), `skills` (array of strings), `certifications` (array of strings), `achievements` (array of strings), `hackathons` (array of objects), `experience` (array of objects).
6. WHEN the `projects` field is populated, each project object SHALL contain: `name` (string), `description` (string), `technologies` (array of strings).
7. WHEN the `hackathons` field is populated, each hackathon object SHALL contain: `name` (string), `role` (string).
8. WHEN the `experience` field is populated, each experience object SHALL contain: `company` (string), `role` (string), `duration` (string), `description` (string).
9. WHERE a Schema string field is not present in the resume, THE JSON_Builder SHALL populate the field with `null` rather than an empty string or omitting the field entirely.
10. WHERE a Schema array field is not present in the resume, THE JSON_Builder SHALL populate the field with an empty array rather than omitting the field entirely.
11. Technologies appearing within `project` objects SHALL be normalized to a canonical casing format before being stored (e.g., `fastapi` → `FastAPI`, `postgresql` → `PostgreSQL`, `aws` → `AWS`).
12. WHEN technologies are identified within a `project` object, THE JSON_Builder SHALL also include those technologies in the top-level `skills` array where the technology represents a distinct technical skill, avoiding duplication with skills already present in that array.
13. THE JSON_Builder SHALL deduplicate entries in the `skills` array and in each `project.technologies` array, using case-insensitive comparison, so that no skill or technology name appears more than once in its respective array.

---

### Requirement 4: End-to-End Pipeline Orchestration

**User Story:** As an API consumer, I want a single pipeline endpoint that accepts a PDF and returns structured JSON, so that I do not need to coordinate individual pipeline stages manually.

#### Acceptance Criteria

1. THE Pipeline SHALL expose a single entry point that accepts a PDF file (valid, ≤ 10 MB) and returns a Resume_Profile JSON object.
2. WHEN all pipeline stages succeed, THE Pipeline SHALL return the Resume_Profile JSON object with an HTTP 200 status.
3. IF any pipeline stage fails, THEN THE Pipeline SHALL return a structured error response that includes an error code, a human-readable message, and the name of the stage at which the failure occurred, without modifying any previously stored intermediate results.
4. THE Pipeline SHALL process a single valid resume PDF of 10 MB or less, with the LLM API responding within its 30-second timeout, end-to-end within 60 seconds.
5. WHEN a pipeline run completes (success or failure), THE Pipeline SHALL log for each stage: the stage name, its status (success or failure), and its duration in milliseconds; plus the total end-to-end duration in milliseconds.
6. IF the provided file is invalid (not a PDF or exceeds 10 MB), THEN THE Pipeline SHALL reject the request before invoking any pipeline stage and return a structured error response with the appropriate error code.

---

### Requirement 5: Round-Trip Serialization Integrity

**User Story:** As a developer, I want assurance that the Resume_Profile JSON output can be serialized and deserialized without data loss, so that downstream consumers can safely store and reload Resume_Profile objects.

#### Acceptance Criteria

1. THE JSON_Builder SHALL serialize Resume_Profile objects into valid JSON strings.
2. FOR ALL valid Resume_Profile objects, serializing then deserializing SHALL produce an object equivalent to the original (round-trip property).
3. WHEN a Resume_Profile is deserialized from a JSON string, THE JSON_Builder SHALL validate the result against the Schema before returning it.
4. IF deserialization produces a JSON parse error, THEN THE JSON_Builder SHALL return an error response indicating a malformed input string.
5. IF deserialization succeeds but the resulting object does not conform to the Resume_Profile Schema, THEN THE JSON_Builder SHALL return an error response listing each failing field with the expected type and the actual value received.
