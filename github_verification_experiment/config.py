"""config.py — loads environment variables for the GitHub verification experiment."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from this module's directory
_ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(_ENV_PATH)

GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")

if not GITHUB_TOKEN:
    raise EnvironmentError(
        "GITHUB_TOKEN is not set. "
        "Create github_verification_experiment/.env with GITHUB_TOKEN=<your_token>"
    )

GITHUB_GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
