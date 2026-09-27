import html
from json import JSONDecodeError
import re

import httpx

from bot.models.search_result import SearchResult
from bot.providers.errors import ProviderError

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_ARTICLE_URL = "https://en.wikipedia.org/?curid={page_id}"
SOURCE_NAME = "Wikipedia"
SNIPPET_TAG_RE = re.compile(r"<.*?>")
RESULTS_LIMIT = 3


def _clean_snippet(snippet: str) -> str:
    without_tags = SNIPPET_TAG_RE.sub("", snippet)
    return html.unescape(without_tags)


class WikipediaProvider:
    source_name = SOURCE_NAME

    def __init__(
        self,
        client: httpx.AsyncClient,
        user_agent: str,
    ) -> None:
        self._client = client
        self._user_agent = user_agent

    async def search(self, query: str) -> list[SearchResult]:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": RESULTS_LIMIT,
            "srprop": "snippet",
        }
        headers = {"User-Agent": self._user_agent}

        try:
            response = await self._client.get(
                WIKIPEDIA_API_URL,
                params=params,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "Wikipedia API request timed out",
                kind="http_timeout",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                "Wikipedia API returned an unsuccessful status",
                kind="http_status",
                status_code=exc.response.status_code,
            ) from exc
        except (httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            raise ProviderError(
                "Failed to communicate with Wikipedia API",
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
        if isinstance(data, dict) and ("error" in data or data.get("errors")):
            raise ProviderError(
                "Wikipedia API reported an error",
                kind="api_error",
                status_code=response.status_code,
            )
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("query"), dict)
            or not isinstance(data["query"].get("search"), list)
        ):
            raise ProviderError(
                "Wikipedia API returned an invalid search response",
                kind="invalid_response",
                status_code=response.status_code,
            )
        raw_results = data["query"]["search"]

        return [
            SearchResult(
                title=item["title"],
                description=_clean_snippet(item.get("snippet", "")),
                url=WIKIPEDIA_ARTICLE_URL.format(page_id=item["pageid"]),
                source=SOURCE_NAME,
            )
            for item in raw_results
        ]
