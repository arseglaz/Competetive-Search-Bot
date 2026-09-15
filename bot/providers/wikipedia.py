import html
import re

import httpx

from bot.models.search_result import SearchResult

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_ARTICLE_URL = "https://en.wikipedia.org/?curid={page_id}"
SOURCE_NAME = "Wikipedia"

_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def _clean_snippet(snippet: str) -> str:
    # MediaWiki wraps matches in <span class="searchmatch"> and may include
    # HTML entities (e.g. &quot;) - strip tags, then unescape entities.
    without_tags = _HTML_TAG_PATTERN.sub("", snippet)
    return html.unescape(without_tags)


class WikipediaProvider:
    source_name = SOURCE_NAME

    def __init__(self, client: httpx.AsyncClient, user_agent: str, limit: int = 5):
        self._client = client
        self._user_agent = user_agent
        self._limit = limit

    async def search(self, query: str) -> list[SearchResult]:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": self._limit,
            "format": "json",
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
