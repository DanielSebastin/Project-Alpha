"""confidence_engine.py — Calculate confidence scores for extracted GitHub skills.

Consumes:  output/extracted_skills.json
Produces:  output/skill_confidence.json

Scoring is based purely on GitHub evidence — no LLMs, no fuzzy matching,
no hardcoded skill names.

Usage:
    python confidence_engine.py [--input <path>]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging setup — structured JSON to stdout
# ---------------------------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(_JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurable scoring weights
# ---------------------------------------------------------------------------

LANGUAGE_WEIGHT: int = 2
DEPENDENCY_WEIGHT: int = 5
TOPIC_WEIGHT: int = 3
README_WEIGHT: int = 1
REPOSITORY_BONUS: int = 1
SOURCE_BONUS: int = 2

# ---------------------------------------------------------------------------
# Confidence thresholds  (inclusive lower bound → label)
# ---------------------------------------------------------------------------

CONFIDENCE_THRESHOLDS: list[tuple[int, str]] = [
    (26, "Very High"),
    (16, "High"),
    (6,  "Medium"),
    (0,  "Low"),
]


# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------

EvidenceEntry = dict       # {"source": str, "repo": str, "detail": str}
SkillData = dict           # {"canonical_name": str, "evidence": list[EvidenceEntry]}


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------

def _confidence_label(score: int) -> str:
    """Return the confidence label for *score* using the configured thresholds.

    Args:
        score: Non-negative integer score.

    Returns:
        One of "Very High", "High", "Medium", "Low".
    """
    for threshold, label in CONFIDENCE_THRESHOLDS:
        if score >= threshold:
            return label
    return "Low"


def score_skill(skill_name: str, skill_data: SkillData) -> dict:
    """Calculate the confidence score for a single skill.

    Args:
        skill_name: The display name of the skill.
        skill_data: Dict containing ``canonical_name`` and ``evidence`` list.

    Returns:
        A dict with keys: skill, score, confidence, breakdown.
    """
    evidence: list[EvidenceEntry] = skill_data.get("evidence") or []

    # Counts by source type
    language_count: int = 0
    dependency_count: int = 0
    topic_count: int = 0
    readme_count: int = 0

    unique_repos: set[str] = set()
    unique_sources: set[str] = set()

    for entry in evidence:
        if not isinstance(entry, dict):
            logger.warning("Skipping malformed evidence entry for skill '%s': %s", skill_name, entry)
            continue

        source = entry.get("source", "")
        repo = entry.get("repo", "")

        if repo:
            unique_repos.add(repo)
        if source:
            unique_sources.add(source)

        if source == "language":
            language_count += 1
        elif source == "dependency":
            dependency_count += 1
        elif source == "topic":
            topic_count += 1
        elif source == "readme":
            readme_count += 1
        else:
            logger.debug("Unknown evidence source '%s' for skill '%s'", source, skill_name)

    unique_repository_count = len(unique_repos)
    unique_source_count = len(unique_sources)

    score: int = (
        language_count   * LANGUAGE_WEIGHT
        + dependency_count * DEPENDENCY_WEIGHT
        + topic_count      * TOPIC_WEIGHT
        + readme_count     * README_WEIGHT
        + unique_repository_count * REPOSITORY_BONUS
        + unique_source_count     * SOURCE_BONUS
    )

    return {
        "skill": skill_name,
        "score": score,
        "confidence": _confidence_label(score),
        "breakdown": {
            "language_count":      language_count,
            "dependency_count":    dependency_count,
            "topic_count":         topic_count,
            "readme_count":        readme_count,
            "unique_repositories": unique_repository_count,
            "unique_sources":      unique_source_count,
        },
    }


def calculate_confidence(extracted: dict) -> dict:
    """Process all skills and return the full confidence output dict.

    Args:
        extracted: Parsed content of extracted_skills.json.

    Returns:
        Dict ready for JSON serialisation with username and sorted skill list.
    """
    username: str = extracted.get("username", "unknown")
    skills_input: dict[str, SkillData] = extracted.get("skills", {})

    if not isinstance(skills_input, dict):
        logger.error("'skills' field is not a dict — got %s", type(skills_input).__name__)
        return {"username": username, "skills": []}

    scored: list[dict] = []
    for skill_name, skill_data in skills_input.items():
        if not isinstance(skill_data, dict):
            logger.warning("Skipping skill '%s': data is not a dict", skill_name)
            continue
        result = score_skill(skill_name, skill_data)
        scored.append(result)
        logger.info("Scored skill '%s': score=%d confidence=%s", skill_name, result["score"], result["confidence"])

    # Sort by score descending, then alphabetically for ties
    scored.sort(key=lambda s: (-s["score"], s["skill"]))

    return {"username": username, "skills": scored}


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

def print_summary(skills: list[dict]) -> None:
    """Print summary statistics to stderr.

    Args:
        skills: Sorted list of scored skill dicts.
    """
    if not skills:
        print("No skills to summarise.", file=sys.stderr)
        return

    total = len(skills)
    scores = [s["score"] for s in skills]
    avg_score = sum(scores) / total
    highest = skills[0]
    lowest = skills[-1]

    distribution: dict[str, int] = {"Very High": 0, "High": 0, "Medium": 0, "Low": 0}
    for s in skills:
        distribution[s["confidence"]] = distribution.get(s["confidence"], 0) + 1

    print("── Confidence Engine Summary ───────────────", file=sys.stderr)
    print(f"  Total skills processed : {total}", file=sys.stderr)
    print(f"  Average score          : {avg_score:.1f}", file=sys.stderr)
    print(f"  Highest scoring skill  : {highest['skill']} (score={highest['score']}, {highest['confidence']})", file=sys.stderr)
    print(f"  Lowest scoring skill   : {lowest['skill']} (score={lowest['score']}, {lowest['confidence']})", file=sys.stderr)
    print("  Confidence distribution:", file=sys.stderr)
    for label in ("Very High", "High", "Medium", "Low"):
        count = distribution.get(label, 0)
        bar = "█" * count
        print(f"    {label:<10} : {count:>3}  {bar}", file=sys.stderr)
    print("────────────────────────────────────────────", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point for the confidence engine CLI."""
    parser = argparse.ArgumentParser(
        description="Calculate confidence scores for extracted GitHub skills."
    )
    parser.add_argument(
        "--input",
        default="output/extracted_skills.json",
        help="Path to extracted_skills.json (default: output/extracted_skills.json)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("Input file not found: %s", input_path)
        print(f"Error: '{input_path}' not found. Run skill_extractor.py first.", file=sys.stderr)
        sys.exit(1)

    # Load — handle malformed JSON safely
    try:
        raw_text = input_path.read_text(encoding="utf-8")
        extracted = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse JSON from '%s': %s", input_path, exc)
        print(f"Error: '{input_path}' contains invalid JSON.", file=sys.stderr)
        sys.exit(1)

    if not isinstance(extracted, dict):
        logger.error("Expected a JSON object at root, got %s", type(extracted).__name__)
        sys.exit(1)

    logger.info("Loaded extracted skills for username='%s'", extracted.get("username"))

    # Score
    result = calculate_confidence(extracted)

    # Summary
    print_summary(result["skills"])

    # Save
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "skill_confidence.json"
    formatted = json.dumps(result, indent=2, ensure_ascii=False)
    output_file.write_text(formatted, encoding="utf-8")

    logger.info("Saved skill_confidence.json with %d skills", len(result["skills"]))
    print(formatted)
    print(f"\nSaved to {output_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
