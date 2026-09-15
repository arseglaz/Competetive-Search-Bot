import asyncio

import pytest

from bot.models.search_result import SearchResult
from bot.services.search_service import SearchProvider, SearchService


def create_search_service(
    providers: list[SearchProvider],
    provider_timeout_seconds: float = 1.0,
    max_concurrent_provider_calls: int = 10,
) -> SearchService:
    return SearchService(
        providers=providers,
        provider_timeout_seconds=provider_timeout_seconds,
        max_concurrent_provider_calls=max_concurrent_provider_calls,
    )


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


class SlowProvider:
    source_name = "Slow Source"

    async def search(self, query: str) -> list[SearchResult]:
        await asyncio.sleep(1)
        return []


class ConcurrentTrackingState:
    def __init__(self) -> None:
        self.active_count = 0
        self.max_active_count = 0


class ConcurrentTrackingProvider:
    source_name = "Concurrent Tracking Source"

    def __init__(self, state: ConcurrentTrackingState) -> None:
        self._state = state

    async def search(self, query: str) -> list[SearchResult]:
        self._state.active_count += 1
        self._state.max_active_count = max(
            self._state.max_active_count,
            self._state.active_count,
        )
        try:
            await asyncio.sleep(0.01)
            return []
        finally:
            self._state.active_count -= 1


@pytest.mark.asyncio
async def test_search_returns_successful_results() -> None:
    service = create_search_service(providers=[SuccessfulProvider()])

    response = await service.search("python")

    assert len(response.results) == 1
    assert response.results[0].title == "python result"
    assert response.failures == []


@pytest.mark.asyncio
async def test_search_keeps_successful_results_when_provider_fails() -> None:
    service = create_search_service(
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
    service = create_search_service(providers=[EmptyProvider()])

    response = await service.search("missing")

    assert response.results == []
    assert response.failures == []


@pytest.mark.asyncio
async def test_search_returns_failures_when_all_providers_fail() -> None:
    service = create_search_service(
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


@pytest.mark.asyncio
async def test_search_marks_slow_provider_as_failure_after_timeout() -> None:
    service = create_search_service(
        providers=[
            SuccessfulProvider(),
            SlowProvider(),
        ],
        provider_timeout_seconds=0.01,
    )

    response = await service.search("timeout")

    assert len(response.results) == 1
    assert response.results[0].source == "Successful Source"
    assert len(response.failures) == 1
    assert response.failures[0].source == "Slow Source"


@pytest.mark.asyncio
async def test_search_limits_concurrent_provider_calls() -> None:
    state = ConcurrentTrackingState()
    service = create_search_service(
        providers=[
            ConcurrentTrackingProvider(state),
            ConcurrentTrackingProvider(state),
            ConcurrentTrackingProvider(state),
        ],
        max_concurrent_provider_calls=1,
    )

    await service.search("semaphore")

    assert state.max_active_count == 1
