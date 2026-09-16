import asyncio

import httpx
import pytest

from bot.providers.wikipedia import WikipediaProvider, _clean_snippet


def test_clean_snippet_removes_html_tags_and_unescapes_entities() -> None:
    snippet = (
        'Python is a <span class="searchmatch">programming</span> '
        "language &amp; runtime"
    )

    assert _clean_snippet(snippet) == "Python is a programming language & runtime"


def test_search_returns_normalized_search_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"] == "CompetitiveSearchBot/0.1 test"
        assert request.url.params["action"] == "query"
        assert request.url.params["list"] == "search"
        assert request.url.params["srsearch"] == "python asyncio"
        assert request.url.params["format"] == "json"
        assert request.url.params["srlimit"] == "3"
        assert request.url.params["srprop"] == "snippet"

        return httpx.Response(
            status_code=200,
            json={
                "query": {
                    "search": [
                        {
                            "title": "Asyncio",
                            "snippet": (
                                'Python <span class="searchmatch">asyncio</span> '
                                "library &amp; concurrency"
                            ),
                            "pageid": 12345,
                        }
                    ]
                }
            },
        )

    async def run_search() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = WikipediaProvider(
                client=client,
                user_agent="CompetitiveSearchBot/0.1 test",
            )

            results = await provider.search("python asyncio")

        assert len(results) == 1
        assert results[0].title == "Asyncio"
        assert results[0].description == "Python asyncio library & concurrency"
        assert results[0].url == "https://en.wikipedia.org/?curid=12345"
        assert results[0].source == "Wikipedia"

    asyncio.run(run_search())


def test_search_returns_empty_list_when_response_has_no_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json={"query": {"search": []}})

    async def run_search() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = WikipediaProvider(client=client, user_agent="test")

            results = await provider.search("unknown query")

        assert results == []

    asyncio.run(run_search())


def test_search_raises_for_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=500, request=request)

    async def run_search() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = WikipediaProvider(client=client, user_agent="test")

            with pytest.raises(httpx.HTTPStatusError):
                await provider.search("python asyncio")

    asyncio.run(run_search())
