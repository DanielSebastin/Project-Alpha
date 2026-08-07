from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    llm_api_key: str = ""           # from LLM_API_KEY env var
    llm_endpoint: str = ""          # from LLM_ENDPOINT env var
    llm_model: str = "gpt-4o-mini"
    llm_timeout: float = 30.0
    max_pdf_size_bytes: int = 10 * 1024 * 1024  # 10 MB
    max_retries: int = 3
    github_token: str = ""          # from GITHUB_TOKEN env var

    class Config:
        env_file = ".env"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Using lru_cache avoids re-reading the environment on every call and
    prevents module-level instantiation failures when env vars are absent
    (e.g. during testing without a .env file).
    """
    return Settings()
