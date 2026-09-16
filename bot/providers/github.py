from typing import Any

import httpx

from bot.models.search_result import SearchResult

GITHUB_SEARCH_REPOSITORIES_URL = "https://api.github.com/search/repositories"
SOURCE_NAME = "GitHub"
DEFAULT_RESULTS_LIMIT = 3
GITHUB_API_VERSION = "2022-11-28"


class GitHubProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        user_agent: str,
        limit: int = DEFAULT_RESULTS_LIMIT,
    ) -> None:
        self._client = client
        self._user_agent = user_agent
        self._limit = limit

    async def search(self, query: str) -> list[SearchResult]:
        params = {
            "q": query,
            "per_page": self._limit,
            "sort": "stars",
            "order": "desc",
        }

        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": self._user_agent,
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }

        response = await self._client.get(
            GITHUB_SEARCH_REPOSITORIES_URL,
            params=params,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

        return [
            SearchResult(
                title=item["full_name"],
                description=_build_description(item),
                url=item["html_url"],
                source=SOURCE_NAME,
            )
            for item in data.get("items", [])
        ]


def _build_description(item: dict[str, Any]) -> str:
    description_parts: list[str] = []

    if item.get("description"):
        description_parts.append(item["description"])

    language = item.get("language") or "Unknown language"
    stars_count = item.get("stargazers_count", 0)
    description_parts.append(f"{language} | {stars_count} stars")

    return "\n".join(description_parts)
