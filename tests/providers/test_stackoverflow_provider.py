import asyncio

import httpx
import pytest

from bot.providers.stackoverflow import StackOverflowProvider, _build_description


def test_build_description_includes_question_details() -> None:
    item = {
        "answer_count": 3,
        "score": 12,
        "accepted_answer_id": 123,
    }

    assert _build_description(item) == "Answers: 3 | Score: 12 | Accepted answer: Yes"


def test_build_description_handles_missing_optional_fields() -> None:
    item = {}

    assert _build_description(item) == "Answers: 0 | Score: 0 | Accepted answer: No"


def test_search_returns_normalized_search_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"] == "CompetitiveSearchBot/0.1 test"
        assert request.url.params["order"] == "desc"
        assert request.url.params["sort"] == "relevance"
        assert request.url.params["q"] == "python asyncio"
        assert request.url.params["site"] == "stackoverflow"
        assert request.url.params["pagesize"] == "3"

        return httpx.Response(
            status_code=200,
            json={
                "items": [
                    {
                        "title": "Python asyncio &amp; gather",
                        "answer_count": 2,
                        "score": 7,
                        "accepted_answer_id": 456,
                        "link": "https://stackoverflow.com/questions/123/example",
                    }
                ]
            },
        )

    async def run_search() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = StackOverflowProvider(
                client=client,
                user_agent="CompetitiveSearchBot/0.1 test",
            )

            results = await provider.search("python asyncio")

        assert len(results) == 1
        assert results[0].title == "Python asyncio & gather"
        assert results[0].description == (
            "Answers: 2 | Score: 7 | Accepted answer: Yes"
        )
        assert results[0].url == "https://stackoverflow.com/questions/123/example"
        assert results[0].source == "Stack Overflow"

    asyncio.run(run_search())


def test_search_uses_custom_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["pagesize"] == "1"
        return httpx.Response(status_code=200, json={"items": []})

    async def run_search() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = StackOverflowProvider(client=client, user_agent="test", limit=1)

            results = await provider.search("python")

        assert results == []

    asyncio.run(run_search())


def test_search_raises_for_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=502, request=request)

    async def run_search() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = StackOverflowProvider(client=client, user_agent="test")

            with pytest.raises(httpx.HTTPStatusError):
                await provider.search("python asyncio")

    asyncio.run(run_search())
