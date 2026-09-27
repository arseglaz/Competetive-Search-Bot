import asyncio

import httpx
import pytest
from bot.providers.errors import ProviderError

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

            with pytest.raises(ProviderError) as exc_info:
                await provider.search("python asyncio")

            assert exc_info.value.kind == "http_status"
            assert exc_info.value.status_code == 500
            assert isinstance(exc_info.value.__cause__, httpx.HTTPStatusError)

    asyncio.run(run_search())


@pytest.mark.parametrize("payload", [
    {"error": {"code": "internal_api_error", "info": "Search failed"}},
    {"errors": [{"code": "internal_api_error", "text": "Search failed"}]},
    {"error": {"code": "badvalue"}, "query": {"search": []}},
])
def test_http_200_api_error_is_not_an_empty_search(payload):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload),
        )) as client:
            with pytest.raises(ProviderError) as error:
                await WikipediaProvider(client, "test").search("python")
        assert error.value.kind == "api_error"
        assert error.value.status_code == 200
    asyncio.run(run())


@pytest.mark.parametrize("payload", [{}, [], {"query": {}}, {"query": {"search": None}}])
def test_missing_or_invalid_search_list_is_not_an_empty_search(payload):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload),
        )) as client:
            with pytest.raises(ProviderError) as error:
                await WikipediaProvider(client, "test").search("python")
        assert error.value.kind == "invalid_response"
    asyncio.run(run())


def test_nonfatal_warning_does_not_discard_valid_results():
    async def run():
        payload = {"warnings": {"query": {"*": "Nonfatal warning"}},
                   "query": {"search": [{"title": "Python", "pageid": 1}]}}
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload),
        )) as client:
            results = await WikipediaProvider(client, "test").search("python")
        assert [result.title for result in results] == ["Python"]
    asyncio.run(run())
