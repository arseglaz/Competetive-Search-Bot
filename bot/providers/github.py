import httpx

from bot.models.search_result import SearchResult

GITHUB_SEARCH_REPOSITORIES_URL = "https://api.github.com/search/repositories"
SOURCE_NAME = "GitHub"


class GitHubProvider:
    source_name = SOURCE_NAME

    def __init__(self, client: httpx.AsyncClient, user_agent: str, limit: int = 5):
        self._client = client
        self._user_agent = user_agent
        self._limit = limit

    async def search(self, query: str) -> list[SearchResult]:
        params = {
            "q": query,
            "per_page": self._limit,
        }
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": self._user_agent,
            "X-GitHub-Api-Version": "2022-11-28",
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


def _build_description(item: dict) -> str:
    description_parts = []

    if item.get("description"):
        description_parts.append(item["description"])

    details = [
        f"Stars: {item.get('stargazers_count', 0)}",
        f"Language: {item.get('language') or 'Unknown'}",
    ]
    description_parts.append(" | ".join(details))

    return "\n".join(description_parts)
