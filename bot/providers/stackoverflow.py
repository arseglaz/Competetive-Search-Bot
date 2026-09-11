import html

import httpx

from bot.models.search_result import SearchResult

STACK_OVERFLOW_SEARCH_URL = "https://api.stackexchange.com/2.3/search/advanced"
SOURCE_NAME = "Stack Overflow"


class StackOverflowProvider:
    source_name = SOURCE_NAME

    def __init__(self, client: httpx.AsyncClient, user_agent: str, limit: int = 5):
        self._client = client
        self._user_agent = user_agent
        self._limit = limit

    async def search(self, query: str) -> list[SearchResult]:
        params = {
            "order": "desc",
            "sort": "relevance",
            "q": query,
            "site": "stackoverflow",
            "pagesize": self._limit,
        }
        headers = {"User-Agent": self._user_agent}

        response = await self._client.get(
            STACK_OVERFLOW_SEARCH_URL,
            params=params,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

        return [
            SearchResult(
                title=html.unescape(item["title"]),
                description=_build_description(item),
                url=item["link"],
                source=SOURCE_NAME,
            )
            for item in data.get("items", [])
        ]


def _build_description(item: dict) -> str:
    details = [
        f"Score: {item.get('score', 0)}",
        f"Answers: {item.get('answer_count', 0)}",
    ]
    if item.get("accepted_answer_id"):
        details.append("Accepted")

    return " | ".join(details)
