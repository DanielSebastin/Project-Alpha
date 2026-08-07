"""graphql_client.py — GitHub GraphQL client for fetching repository metadata."""
from __future__ import annotations

import httpx

from config import GITHUB_GRAPHQL_ENDPOINT, GITHUB_TOKEN
from models import GitHubRepositoriesResult, Language, RepositoryMetadata

# ---------------------------------------------------------------------------
# GraphQL query
# ---------------------------------------------------------------------------

_REPOS_QUERY = """
query FetchRepositories($username: String!, $first: Int!) {
  user(login: $username) {
    repositories(
      first: $first
      orderBy: { field: UPDATED_AT, direction: DESC }
      ownerAffiliations: OWNER
    ) {
      nodes {
        name
        description
        isFork
        isArchived
        updatedAt
        repositoryTopics(first: 20) {
          nodes {
            topic {
              name
            }
          }
        }
        languages(first: 20, orderBy: { field: SIZE, direction: DESC }) {
          nodes {
            name
            color
          }
        }
      }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class GitHubGraphQLClient:
    """Thin synchronous client for the GitHub GraphQL API."""

    def __init__(self) -> None:
        self._endpoint = GITHUB_GRAPHQL_ENDPOINT
        self._headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Content-Type": "application/json",
        }

    def fetch_repositories(self, username: str, limit: int = 100) -> GitHubRepositoriesResult:
        """Fetch up to *limit* repositories for *username*, ordered by most recently updated.

        Raises:
            httpx.HTTPStatusError  — on non-2xx response
            ValueError             — if the GraphQL response contains errors or the user is not found
        """
        payload = {
            "query": _REPOS_QUERY,
            "variables": {"username": username, "first": limit},
        }

        with httpx.Client(timeout=30.0) as client:
            response = client.post(self._endpoint, json=payload, headers=self._headers)

        response.raise_for_status()
        data = response.json()

        # GraphQL errors surface in data["errors"] even on HTTP 200
        if "errors" in data:
            messages = "; ".join(e.get("message", "unknown") for e in data["errors"])
            raise ValueError(f"GitHub GraphQL error: {messages}")

        user_node = data.get("data", {}).get("user")
        if user_node is None:
            raise ValueError(f"GitHub user '{username}' not found.")

        repos: list[RepositoryMetadata] = []
        for node in user_node["repositories"]["nodes"]:
            topics = [
                t["topic"]["name"]
                for t in node.get("repositoryTopics", {}).get("nodes", [])
            ]
            languages = [
                Language(name=lang["name"], color=lang.get("color"))
                for lang in node.get("languages", {}).get("nodes", [])
            ]
            repos.append(
                RepositoryMetadata(
                    name=node["name"],
                    description=node.get("description"),
                    is_fork=node["isFork"],
                    is_archived=node["isArchived"],
                    updated_at=node["updatedAt"],
                    topics=topics,
                    languages=languages,
                )
            )

        return GitHubRepositoriesResult(username=username, repositories=repos)
