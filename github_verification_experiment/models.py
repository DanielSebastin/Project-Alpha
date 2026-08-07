"""models.py — Pydantic models for GitHub GraphQL repository metadata."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class Language(BaseModel):
    name: str
    color: Optional[str] = None


class RepositoryMetadata(BaseModel):
    name: str
    description: Optional[str] = None
    is_fork: bool
    is_archived: bool
    updated_at: str
    topics: list[str] = []
    languages: list[Language] = []


class GitHubRepositoriesResult(BaseModel):
    username: str
    repositories: list[RepositoryMetadata] = []
