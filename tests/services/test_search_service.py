import asyncio
from unittest.mock import AsyncMock

import pytest

from bot.models.search_result import SearchResult
from bot.providers.errors import ProviderError
from bot.services import search_service
from bot.services.search_service import SearchService


@pytest.mark.parametrize(
    "timeout",
    [0.0, -1.0, float("inf"), float("-inf"), float("nan")],
)
def test_search_rejects_invalid_timeout(timeout: float) -> None:
    with pytest.raises(
        ValueError,
        match="provider_timeout_seconds must be finite and greater than zero",
    ):
        SearchService([], provider_timeout_seconds=timeout)


@pytest.mark.parametrize("timeout", [0.01, 5.0])
def test_search_accepts_positive_finite_timeout(timeout: float) -> None:
    SearchService([], provider_timeout_seconds=timeout)


class FakeProvider:
    def __init__(self, source: str, delay: float = 0) -> None:
        self._source = source
        self.source_name = source
        self._delay = delay
        self.received_query: str | None = None

    async def search(self, query: str) -> list[SearchResult]:
        self.received_query = query
        await asyncio.sleep(self._delay)
        return [
            SearchResult(
                title=f"{self._source} title",
                description=f"{self._source} description",
                url=f"https://example.com/{self._source}",
                source=self._source,
            )
        ]


class FailingProvider:
    source_name = "Failing"

    async def search(self, query: str) -> list[SearchResult]:
        raise ProviderError("provider failed", kind="network")


class WaitingProvider:
    def __init__(self, source: str) -> None:
        self.source_name = source
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()

    async def search(self, query: str) -> list[SearchResult]:
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.stopped.set()
        return []


@pytest.fixture
def warning_log(monkeypatch):
    log = AsyncMock()
    monkeypatch.setattr(search_service, "logger", log)
    return log.awarning


@pytest.mark.parametrize("timeout", [0.01, 0.2])
def test_timeout_preserves_results_and_logs(warning_log, timeout) -> None:
    async def run_search() -> None:
        slow = WaitingProvider("Slow")
        service = SearchService(
            [FakeProvider("Wikipedia"), FakeProvider("GitHub"), slow],
            provider_timeout_seconds=timeout,
        )
        response = await asyncio.wait_for(service.search("test"), timeout=1)
        assert [result.source for result in response.results] == ["Wikipedia", "GitHub"]
        assert response.failed_sources == ["Slow"]
        assert slow.stopped.is_set()
        warning_log.assert_awaited_once_with(
            "provider_search_timed_out", source="Slow", timeout_seconds=timeout,
        )

    asyncio.run(run_search())


def test_all_providers_time_out(warning_log) -> None:
    async def run_search() -> None:
        service = SearchService(
            [WaitingProvider("First"), WaitingProvider("Second")],
            provider_timeout_seconds=0.01,
        )
        response = await asyncio.wait_for(service.search("test"), timeout=1)
        assert response.results == []
        assert response.failed_sources == ["First", "Second"]
        assert warning_log.await_count == 2

    asyncio.run(run_search())


def test_provider_error_log_contains_exception(warning_log) -> None:
    asyncio.run(SearchService([FailingProvider()]).search("test"))
    warning_log.assert_awaited_once()
    call = warning_log.await_args
    assert call.args == ("provider_search_failed",)
    assert call.kwargs["source"] == "Failing"
    assert call.kwargs["error_kind"] == "network"
    assert call.kwargs["error_type"] == "ProviderError"
    assert call.kwargs["error_message"] == "provider failed"
    assert call.kwargs["status_code"] is None
    assert isinstance(call.kwargs["exc_info"], ProviderError)


def test_unexpected_error_preserves_results_and_logs(monkeypatch) -> None:
    log = AsyncMock()
    monkeypatch.setattr(search_service, "logger", log)
    original_error = RuntimeError("programming bug")

    class BrokenProvider:
        source_name = "Broken"

        async def search(self, query: str) -> list[SearchResult]:
            raise original_error

    async def run_search() -> None:
        service = SearchService(
            providers=[
                FakeProvider("Wikipedia"),
                BrokenProvider(),
                FakeProvider("GitHub"),
            ]
        )
        response = await service.search("test")
        assert [result.source for result in response.results] == [
            "Wikipedia", "GitHub",
        ]
        assert response.failed_sources == ["Broken"]
        log.aexception.assert_awaited_once_with(
            "provider_search_unexpected_error",
            source="Broken",
            error_type="RuntimeError",
            error_message="programming bug",
            exc_info=original_error,
        )
        log.awarning.assert_not_awaited()

    asyncio.run(run_search())


def test_empty_provider_result_is_not_a_failure(monkeypatch) -> None:
    log = AsyncMock()
    monkeypatch.setattr(search_service, "logger", log)

    class EmptyProvider:
        source_name = "Stack Overflow"

        async def search(self, query: str) -> list[SearchResult]:
            return []

    async def run_search() -> None:
        service = SearchService([
            FakeProvider("Wikipedia"), FakeProvider("GitHub"), EmptyProvider(),
        ])
        response = await service.search("test")
        assert [result.source for result in response.results] == ["Wikipedia", "GitHub"]
        assert response.failed_sources == []
        log.awarning.assert_not_awaited()
        log.aexception.assert_not_awaited()

    asyncio.run(run_search())


def test_external_cancellation_propagates(warning_log) -> None:
    async def run_search() -> None:
        provider = WaitingProvider("Waiting")
        task = asyncio.create_task(SearchService([provider]).search("test"))
        await asyncio.wait_for(provider.started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert provider.stopped.is_set()
        warning_log.assert_not_awaited()

    asyncio.run(run_search())


def test_search_collects_results_from_all_providers() -> None:
    async def run_search() -> None:
        first_provider = FakeProvider("First")
        second_provider = FakeProvider("Second")
        service = SearchService(providers=[first_provider, second_provider])

        search_response = await service.search("python asyncio")

        assert first_provider.received_query == "python asyncio"
        assert second_provider.received_query == "python asyncio"
        assert [result.source for result in search_response.results] == [
            "First",
            "Second",
        ]
        assert search_response.failed_sources == []

    asyncio.run(run_search())


def test_search_runs_providers_concurrently() -> None:
    async def run_search() -> None:
        started: set[str] = set()
        all_started = asyncio.Event()

        class SynchronizedProvider(FakeProvider):
            async def search(self, query: str) -> list[SearchResult]:
                started.add(self.source_name)

                if len(started) == 2:
                    all_started.set()

                await all_started.wait()
                return await super().search(query)

        service = SearchService(
            providers=[
                SynchronizedProvider("First"),
                SynchronizedProvider("Second"),
            ],
        )

        async with asyncio.timeout(1.0):
            response = await service.search("python asyncio")

        assert [result.source for result in response.results] == [
            "First",
            "Second",
        ]
        assert response.failed_sources == []

    asyncio.run(run_search())


def test_search_keeps_successful_results_when_provider_fails() -> None:
    async def run_search() -> None:
        service = SearchService(providers=[FakeProvider("First"), FailingProvider()])

        search_response = await service.search("python asyncio")

        assert [result.source for result in search_response.results] == ["First"]
        assert search_response.failed_sources == ["Failing"]

    asyncio.run(run_search())
