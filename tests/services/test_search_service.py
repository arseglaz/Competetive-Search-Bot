import pytest

from bot.models.search_result import SearchResult
from bot.services.search_service import SearchService


class SuccessfulProvider:
    source_name = "Successful Source"

    async def search(self, query: str) -> list[SearchResult]:
        return [
            SearchResult(
                title=f"{query} result",
                description="Found by successful provider.",
                url="https://example.com/success",
                source=self.source_name,
            )
        ]


class EmptyProvider:
    source_name = "Empty Source"

    async def search(self, query: str) -> list[SearchResult]:
        return []


class FailedProvider:
    source_name = "Failed Source"

    async def search(self, query: str) -> list[SearchResult]:
        raise RuntimeError("Provider failed")


@pytest.mark.asyncio
async def test_search_returns_successful_results() -> None:
    service = SearchService(providers=[SuccessfulProvider()])

    response = await service.search("python")

    assert len(response.results) == 1
    assert response.results[0].title == "python result"
    assert response.failures == []


@pytest.mark.asyncio
async def test_search_keeps_successful_results_when_provider_fails() -> None:
    service = SearchService(
        providers=[
            SuccessfulProvider(),
            FailedProvider(),
        ]
    )

    response = await service.search("asyncio")

    assert len(response.results) == 1
    assert response.results[0].source == "Successful Source"
    assert len(response.failures) == 1
    assert response.failures[0].source == "Failed Source"


@pytest.mark.asyncio
async def test_search_keeps_empty_provider_as_successful() -> None:
    service = SearchService(providers=[EmptyProvider()])

    response = await service.search("missing")

    assert response.results == []
    assert response.failures == []


@pytest.mark.asyncio
async def test_search_returns_failures_when_all_providers_fail() -> None:
    service = SearchService(
        providers=[
            FailedProvider(),
            FailedProvider(),
        ]
    )

    response = await service.search("httpx")

    assert response.results == []
    assert [failure.source for failure in response.failures] == [
        "Failed Source",
        "Failed Source",
    ]
