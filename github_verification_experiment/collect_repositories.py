"""collect_repositories.py — CLI script to fetch GitHub repository metadata.

Usage:
    python collect_repositories.py <github_username>

Example:
    python collect_repositories.py DanielSebastin

Output:
    - Prints formatted JSON to stdout
    - Saves result to output/repositories.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from graphql_client import GitHubGraphQLClient


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python collect_repositories.py <github_username>", file=sys.stderr)
        sys.exit(1)

    username = sys.argv[1]

    print(f"Fetching repositories for '{username}'...", file=sys.stderr)

    try:
        client = GitHubGraphQLClient()
        result = client.fetch_repositories(username)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        sys.exit(1)

    # Serialize using Pydantic (preserves field names and types correctly)
    output_dict = result.model_dump()

    formatted = json.dumps(output_dict, indent=2, default=str)

    # Print to stdout
    print(formatted)

    # Save to output/repositories.json
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "repositories.json"
    output_file.write_text(formatted, encoding="utf-8")

    print(
        f"\nSaved {len(result.repositories)} repositories to {output_file}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
