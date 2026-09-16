import asyncio

import httpx
import pytest

from bot.providers.github import GitHubProvider, _build_description


def test_build_description_includes_repository_details() -> None:
    item = {
        "description": "Modern Telegram Bot API framework",
        "language": "Python",
        "stargazers_count": 5000,
    }

    assert (
        _build_description(item)
        == "Modern Telegram Bot API framework\nPython | 5000 stars"
    )


def test_build_description_handles_missing_optional_fields() -> None:
    item = {
        "description": None,
        "language": None,
    }

    assert _build_description(item) == "Unknown language | 0 stars"


def test_search_returns_normalized_search_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Accept"] == "application/vnd.github+json"
        assert request.headers["User-Agent"] == "CompetitiveSearchBot/0.1 test"
        assert request.headers["X-GitHub-Api-Version"] == "2022-11-28"
        assert request.url.params["q"] == "telegram bot"
        assert request.url.params["per_page"] == "3"
        assert request.url.params["sort"] == "stars"
        assert request.url.params["order"] == "desc"

        return httpx.Response(
            status_code=200,
            json={
                "items": [
                    {
                        "full_name": "aiogram/aiogram",
                        "description": "Modern Telegram Bot API framework",
                        "html_url": "https://github.com/aiogram/aiogram",
                        "language": "Python",
                        "stargazers_count": 5000,
                    }
                ]
            },
        )

    async def run_search() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = GitHubProvider(
                client=client,
                user_agent="CompetitiveSearchBot/0.1 test",
            )

            results = await provider.search("telegram bot")

        assert len(results) == 1
        assert results[0].title == "aiogram/aiogram"
        assert results[0].description == (
            "Modern Telegram Bot API framework\nPython | 5000 stars"
        )
        assert results[0].url == "https://github.com/aiogram/aiogram"
        assert results[0].source == "GitHub"

    asyncio.run(run_search())


def test_search_uses_custom_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["per_page"] == "1"
        return httpx.Response(status_code=200, json={"items": []})

    async def run_search() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = GitHubProvider(client=client, user_agent="test", limit=1)

            results = await provider.search("python")

        assert results == []

    asyncio.run(run_search())


def test_search_raises_for_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=403, request=request)

    async def run_search() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = GitHubProvider(client=client, user_agent="test")

            with pytest.raises(httpx.HTTPStatusError):
                await provider.search("telegram bot")

    asyncio.run(run_search())
