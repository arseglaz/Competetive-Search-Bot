from typing import Any
from json import JSONDecodeError

import html
import httpx

from bot.models.search_result import SearchResult
from bot.providers.errors import ProviderError

STACK_OVERFLOW_SEARCH_URL = "https://api.stackexchange.com/2.3/search/advanced"
SOURCE_NAME = "Stack Overflow"
RESULTS_LIMIT = 3


class StackOverflowProvider:
    source_name = SOURCE_NAME

    def __init__(
        self,
        client: httpx.AsyncClient,
        user_agent: str,
        limit: int = RESULTS_LIMIT,
    ) -> None:
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

        try:
            response = await self._client.get(
                STACK_OVERFLOW_SEARCH_URL,
                params=params,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "Stack Overflow API request timed out",
                kind="http_timeout",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                "Stack Overflow API returned an unsuccessful status",
                kind="http_status",
                status_code=exc.response.status_code,
            ) from exc
        except (httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            raise ProviderError(
                "Failed to communicate with Stack Overflow API",
                kind="network",
            ) from exc
        try:
            data = response.json()
        except JSONDecodeError as exc:
            raise ProviderError(
                f"{self.source_name} API returned invalid JSON",
                kind="invalid_response",
                status_code=response.status_code,
            ) from exc

        return [
            SearchResult(
                title=html.unescape(item["title"]),
                description=_build_description(item),
                url=item["link"],
                source=SOURCE_NAME,
            )
            for item in data.get("items", [])
        ]


def _build_description(item: dict[str, Any]) -> str:
    details = [
        f"Answers: {item.get('answer_count', 0)}",
        f"Score: {item.get('score', 0)}",
        f"Accepted answer: {_format_accepted_answer(item)}",
    ]
    return " | ".join(details)


def _format_accepted_answer(item: dict[str, Any]) -> str:
    return "Yes" if item.get("accepted_answer_id") else "No"
