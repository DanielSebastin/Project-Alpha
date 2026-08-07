"""dependency_fetcher.py — Fetch dependency files for each repository.

Determines the ecosystem from repository languages and fetches the relevant
dependency files via the GitHub REST API.

Ecosystem → dependency files:
    Python  → requirements.txt, pyproject.toml
    Node    → package.json          (JavaScript, TypeScript)
    Flutter → pubspec.yaml          (Dart)
    Java    → pom.xml
    Rust    → Cargo.toml

Usage:
    python dependency_fetcher.py [--readmes <path>] [--filtered <path>]

Defaults:
    --readmes   output/repositories_with_readmes.json
    --filtered  output/filtered_repositories.json

Output:
    output/repositories_with_dependencies.json
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path

import httpx

from config import GITHUB_TOKEN

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GITHUB_REST_BASE = "https://api.github.com"
_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
_REQUEST_TIMEOUT = 30.0
_RATE_LIMIT_BACKOFF = 60
_MAX_RETRIES = 3

# Ecosystem detection: language name (lowercase) → ecosystem label
_LANGUAGE_TO_ECOSYSTEM: dict[str, str] = {
    "python": "python",
    "javascript": "node",
    "typescript": "node",
    "dart": "flutter",
    "java": "java",
    "kotlin": "java",   # Kotlin projects often use pom.xml or build.gradle
    "rust": "rust",
}

# Ecosystem → ordered list of dependency files to attempt
_ECOSYSTEM_FILES: dict[str, list[str]] = {
    "python": ["requirements.txt", "pyproject.toml"],
    "node":   ["package.json"],
    "flutter": ["pubspec.yaml"],
    "java":   ["pom.xml"],
    "rust":   ["Cargo.toml"],
}


# ---------------------------------------------------------------------------
# Ecosystem detection
# ---------------------------------------------------------------------------

def detect_ecosystems(languages: list[dict]) -> list[str]:
    """Return a deduplicated list of ecosystem labels inferred from language names."""
    seen: set[str] = set()
    ecosystems: list[str] = []
    for lang in languages:
        name = lang.get("name", "").lower()
        eco = _LANGUAGE_TO_ECOSYSTEM.get(name)
        if eco and eco not in seen:
            seen.add(eco)
            ecosystems.append(eco)
    return ecosystems


# ---------------------------------------------------------------------------
# File fetcher
# ---------------------------------------------------------------------------

def fetch_file(client: httpx.Client, owner: str, repo: str, filepath: str) -> str | None:
    """Fetch and decode a single file from a repository.

    Returns decoded text content or None if not found / on error.
    """
    url = f"{_GITHUB_REST_BASE}/repos/{owner}/{repo}/contents/{filepath}"

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.get(url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
        except httpx.RequestError as exc:
            print(
                f"    [!] Network error fetching {filepath} from {repo} "
                f"(attempt {attempt}): {exc}",
                file=sys.stderr,
            )
            if attempt < _MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            return None

        if response.status_code == 404:
            return None  # file simply doesn't exist

        if response.status_code in (403, 429):
            retry_after = int(response.headers.get("Retry-After", _RATE_LIMIT_BACKOFF))
            print(
                f"    [!] Rate limited. Waiting {retry_after}s...",
                file=sys.stderr,
            )
            time.sleep(retry_after)
            continue

        if not response.is_success:
            print(
                f"    [!] HTTP {response.status_code} fetching {filepath} from {repo} "
                f"(attempt {attempt})",
                file=sys.stderr,
            )
            if attempt < _MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            return None

        data = response.json()
        # GitHub returns base64-encoded content for file contents API
        encoded = data.get("content", "")
        decoded = base64.b64decode(encoded.replace("\n", "")).decode("utf-8", errors="replace")
        return decoded

    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch dependency files for filtered repositories.")
    parser.add_argument(
        "--readmes",
        default="output/repositories_with_readmes.json",
        help="Path to repositories_with_readmes.json",
    )
    parser.add_argument(
        "--filtered",
        default="output/filtered_repositories.json",
        help="Path to filtered_repositories.json (used for language data)",
    )
    args = parser.parse_args()

    readmes_path = Path(args.readmes)
    filtered_path = Path(args.filtered)

    for p in (readmes_path, filtered_path):
        if not p.exists():
            print(f"Error: '{p}' not found.", file=sys.stderr)
            sys.exit(1)

    readmes_data = json.loads(readmes_path.read_text(encoding="utf-8"))
    filtered_data = json.loads(filtered_path.read_text(encoding="utf-8"))

    username: str = readmes_data["username"]

    # Build a lookup: repo_name → language list from filtered data
    lang_lookup: dict[str, list[dict]] = {
        r["name"]: r.get("languages", [])
        for r in filtered_data["repositories"]
    }

    # Build a lookup: repo_name → readme from readmes data
    readme_lookup: dict[str, str | None] = {
        r["repo_name"]: r.get("readme")
        for r in readmes_data["repositories"]
    }

    repo_names = list(readme_lookup.keys())
    print(
        f"Fetching dependency files for {len(repo_names)} repositories (owner: {username})...",
        file=sys.stderr,
    )

    results = []
    total_files_found = 0
    total_files_missing = 0

    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        for i, repo_name in enumerate(repo_names, 1):
            languages = lang_lookup.get(repo_name, [])
            ecosystems = detect_ecosystems(languages)
            language_names = [l["name"] for l in languages]

            print(
                f"  [{i}/{len(repo_names)}] {repo_name} "
                f"(languages: {', '.join(language_names) or 'none'}, "
                f"ecosystems: {', '.join(ecosystems) or 'none'})",
                file=sys.stderr,
            )

            dependencies: dict[str, str | None] = {}

            for eco in ecosystems:
                for dep_file in _ECOSYSTEM_FILES.get(eco, []):
                    content = fetch_file(client, owner=username, repo=repo_name, filepath=dep_file)
                    if content is not None:
                        print(f"    ✓ {dep_file}", file=sys.stderr)
                        dependencies[dep_file] = content
                        total_files_found += 1
                    else:
                        print(f"    — {dep_file} not found", file=sys.stderr)
                        total_files_missing += 1

            results.append({
                "repo_name": repo_name,
                "readme": readme_lookup.get(repo_name),
                "languages": language_names,
                "ecosystems": ecosystems,
                "dependencies": dependencies,
            })

            if i < len(repo_names):
                time.sleep(0.5)

    # Statistics
    print("── Dependency Fetch Statistics ────────────", file=sys.stderr)
    print(f"  Repositories processed   : {len(repo_names)}", file=sys.stderr)
    print(f"  Dependency files found   : {total_files_found}", file=sys.stderr)
    print(f"  Dependency files missing : {total_files_missing}", file=sys.stderr)
    print("───────────────────────────────────────────", file=sys.stderr)

    output = {
        "username": username,
        "repositories": results,
    }
    formatted = json.dumps(output, indent=2, ensure_ascii=False)
    print(formatted)

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "repositories_with_dependencies.json"
    output_file.write_text(formatted, encoding="utf-8")

    print(f"\nSaved to {output_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
