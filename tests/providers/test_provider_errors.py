import asyncio
from json import JSONDecodeError

import httpx
import pytest

from bot.providers.errors import ProviderError
from bot.providers.github import GitHubProvider
from bot.providers.stackoverflow import StackOverflowProvider
from bot.providers.wikipedia import WikipediaProvider


@pytest.mark.parametrize(
    "provider_class",
    [GitHubProvider, WikipediaProvider, StackOverflowProvider],
)
@pytest.mark.parametrize(
    ("error_class", "kind"),
    [
        (httpx.ReadTimeout, "http_timeout"),
        (httpx.ConnectError, "network"),
        (httpx.RemoteProtocolError, "network"),
    ],
)
def test_provider_preserves_request_error(provider_class, error_class, kind):
    original_error = error_class("test failure")

    def handler(request: httpx.Request) -> httpx.Response:
        raise original_error

    async def run_search() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        ) as client:
            provider = provider_class(client=client, user_agent="test")

            with pytest.raises(ProviderError) as exc_info:
                await provider.search("python asyncio")

            assert exc_info.value.kind == kind
            assert exc_info.value.status_code is None
            assert exc_info.value.__cause__ is original_error

    asyncio.run(run_search())


@pytest.mark.parametrize(
    "provider_class",
    [GitHubProvider, WikipediaProvider, StackOverflowProvider],
)
def test_provider_rejects_invalid_json(provider_class):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            text="<html>Service unavailable</html>",
            headers={"Content-Type": "text/html"},
        )

    async def run_search() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        ) as client:
            provider = provider_class(client=client, user_agent="test")

            with pytest.raises(ProviderError) as exc_info:
                await provider.search("python asyncio")

            error = exc_info.value
            assert error.kind == "invalid_response"
            assert error.status_code == 200
            assert str(error) == (
                f"{provider.source_name} API returned invalid JSON"
            )
            assert isinstance(error.__cause__, JSONDecodeError)

    asyncio.run(run_search())
