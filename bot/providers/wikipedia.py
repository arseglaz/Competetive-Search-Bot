import html
import re

import httpx

from bot.models.search_result import SearchResult

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_ARTICLE_URL = "https://en.wikipedia.org/?curid={page_id}"
SOURCE_NAME = "Wikipedia"
SNIPPET_TAG_RE = re.compile(r"<.*?>")
RESULTS_LIMIT = 3


def _clean_snippet(snippet: str) -> str:
    without_tags = SNIPPET_TAG_RE.sub("", snippet)
    return html.unescape(without_tags)


class WikipediaProvider:
    def __init__(self, client: httpx.AsyncClient, user_agent: str) -> None:
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

        response = await self._client.get(
            WIKIPEDIA_API_URL,
            params=params,
            headers=headers,
        )
        response.raise_for_status()

        data = response.json()
        raw_results = data.get("query", {}).get("search", [])

        return [
            SearchResult(
                title=item["title"],
                description=_clean_snippet(item.get("snippet", "")),
                url=WIKIPEDIA_ARTICLE_URL.format(page_id=item["pageid"]),
                source=SOURCE_NAME,
            )
            for item in raw_results
        ]

