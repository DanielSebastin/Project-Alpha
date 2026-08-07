"""repository_filter.py — Filter and rank GitHub repositories from collected metadata.

Usage:
    python repository_filter.py [--input <path>] [--max <n>]

Defaults:
    --input  output/repositories.json
    --max    10

Output:
    output/filtered_repositories.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from models import GitHubRepositoriesResult, RepositoryMetadata

# ---------------------------------------------------------------------------
# Filtering logic
# ---------------------------------------------------------------------------

def filter_repositories(
    result: GitHubRepositoriesResult,
    max_count: int = 10,
) -> tuple[list[RepositoryMetadata], dict]:
    """Filter, sort, and trim repositories.

    Steps:
    1. Remove forked repositories
    2. Remove archived repositories
    3. Sort by updatedAt descending
    4. Keep top *max_count*

    Returns:
        (filtered_repos, stats) where stats is a dict with counts.
    """
    total = len(result.repositories)

    # Step 1 & 2: remove forks and archived
    active = [r for r in result.repositories if not r.is_fork and not r.is_archived]
    removed = total - len(active)

    # Step 3: sort by updatedAt descending (ISO 8601 strings sort correctly lexicographically)
    active.sort(key=lambda r: r.updated_at, reverse=True)

    # Step 4: keep top N
    selected = active[:max_count]

    stats = {
        "total_found": total,
        "removed": removed,
        "selected": len(selected),
    }

    return selected, stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Filter GitHub repositories metadata.")
    parser.add_argument(
        "--input",
        default="output/repositories.json",
        help="Path to input repositories.json (default: output/repositories.json)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=10,
        help="Maximum number of repositories to keep (default: 10)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file '{input_path}' not found.", file=sys.stderr)
        print("Run collect_repositories.py first to generate it.", file=sys.stderr)
        sys.exit(1)

    # Load
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    result = GitHubRepositoriesResult.model_validate(raw)

    # Filter
    filtered, stats = filter_repositories(result, max_count=args.max)

    # Print statistics
    print("── Filter Statistics ──────────────────────", file=sys.stderr)
    print(f"  Total repositories found : {stats['total_found']}", file=sys.stderr)
    print(f"  Repositories removed     : {stats['removed']} (forks + archived)", file=sys.stderr)
    print(f"  Repositories selected    : {stats['selected']}", file=sys.stderr)
    print("───────────────────────────────────────────", file=sys.stderr)

    # Build output
    output = {
        "username": result.username,
        "filter_stats": stats,
        "repositories": [r.model_dump() for r in filtered],
    }
    formatted = json.dumps(output, indent=2, default=str)

    # Print to stdout
    print(formatted)

    # Save
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "filtered_repositories.json"
    output_file.write_text(formatted, encoding="utf-8")

    print(f"\nSaved to {output_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
