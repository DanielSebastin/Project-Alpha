"""readme_fetcher.py — Fetch README content for each filtered repository.

Usage:
    python readme_fetcher.py [--input <path>]

Defaults:
    --input  output/filtered_repositories.json

Output:
    output/repositories_with_readmes.json

Each entry:
    {
        "repo_name": "...",
        "readme": "..."   # decoded text, or null if not found
    }
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
# Seconds to wait when rate-limited before retrying
_RATE_LIMIT_BACKOFF = 60
_MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# README fetcher
# ---------------------------------------------------------------------------

def fetch_readme(client: httpx.Client, owner: str, repo: str) -> str | None:
    """Fetch and decode the README for *owner*/*repo*.

    Returns the decoded README text, or None if no README exists.
    Handles 404 (no README), 403/429 (rate limit), and transient errors.
    """
    url = f"{_GITHUB_REST_BASE}/repos/{owner}/{repo}/readme"

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.get(url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
        except httpx.RequestError as exc:
            print(f"  [!] Network error fetching {repo} (attempt {attempt}): {exc}", file=sys.stderr)
            if attempt < _MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            return None

        if response.status_code == 404:
            # No README — not an error
            return None

        if response.status_code in (403, 429):
            # Rate limited — check Retry-After or fall back to backoff
            retry_after = int(response.headers.get("Retry-After", _RATE_LIMIT_BACKOFF))
            print(
                f"  [!] Rate limited on {repo}. Waiting {retry_after}s...",
                file=sys.stderr,
            )
            time.sleep(retry_after)
            continue

        if not response.is_success:
            print(
                f"  [!] HTTP {response.status_code} fetching README for {repo} "
                f"(attempt {attempt})",
                file=sys.stderr,
            )
            if attempt < _MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            return None

        # Success — decode base64 content
        data = response.json()
        encoded = data.get("content", "")
        # GitHub encodes with newlines in the base64 string
        decoded = base64.b64decode(encoded.replace("\n", "")).decode("utf-8", errors="replace")
        return decoded

    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch READMEs for filtered repositories.")
    parser.add_argument(
        "--input",
        default="output/filtered_repositories.json",
        help="Path to filtered_repositories.json (default: output/filtered_repositories.json)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file '{input_path}' not found.", file=sys.stderr)
        print("Run repository_filter.py first to generate it.", file=sys.stderr)
        sys.exit(1)

    data = json.loads(input_path.read_text(encoding="utf-8"))
    username: str = data["username"]
    repositories: list[dict] = data["repositories"]

    print(f"Fetching READMEs for {len(repositories)} repositories (owner: {username})...", file=sys.stderr)

    results = []
    found = 0
    missing = 0

    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        for i, repo in enumerate(repositories, 1):
            repo_name = repo["name"]
            print(f"  [{i}/{len(repositories)}] {repo_name}", file=sys.stderr, end=" ")

            readme = fetch_readme(client, owner=username, repo=repo_name)

            if readme is not None:
                print("✓", file=sys.stderr)
                found += 1
            else:
                print("— no README", file=sys.stderr)
                missing += 1

            results.append({
                "repo_name": repo_name,
                "readme": readme,
            })

            # Small delay between requests to be a good API citizen
            if i < len(repositories):
                time.sleep(0.5)

    # Statistics
    print("── README Fetch Statistics ────────────────", file=sys.stderr)
    print(f"  Repositories processed : {len(repositories)}", file=sys.stderr)
    print(f"  READMEs found          : {found}", file=sys.stderr)
    print(f"  READMEs missing        : {missing}", file=sys.stderr)
    print("───────────────────────────────────────────", file=sys.stderr)

    # Save output
    output = {
        "username": username,
        "repositories": results,
    }
    formatted = json.dumps(output, indent=2, ensure_ascii=False)
    print(formatted)

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "repositories_with_readmes.json"
    output_file.write_text(formatted, encoding="utf-8")

    print(f"\nSaved to {output_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
