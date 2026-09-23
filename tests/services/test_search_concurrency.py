import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from bot.models.search_result import SearchResult
from bot.services import search_service
from bot.services.search_service import SearchService, _search_provider


@pytest.fixture(autouse=True)
def mock_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(search_service, "logger", AsyncMock())


@pytest.mark.parametrize("limit", [0, -1, 1.5, True])
def test_invalid_concurrency_limit_is_rejected(limit: Any) -> None:
    with pytest.raises(ValueError, match="max_concurrent_per_provider"):
        SearchService([], max_concurrent_per_provider=limit)


def test_provider_limits_are_shared_across_searches_and_independent() -> None:
    async def run() -> None:
        release_slow = asyncio.Event()
        slow_full = asyncio.Event()
        fast_finished = asyncio.Event()

        class SlowProvider:
            source_name = "Slow"
            active = 0
            peak = 0

            async def search(self, query: str) -> list[SearchResult]:
                self.active += 1
                self.peak = max(self.peak, self.active)
                if self.active == 2:
                    slow_full.set()
                try:
                    await release_slow.wait()
                    return []
                finally:
                    self.active -= 1

        class FastProvider:
            source_name = "Fast"
            calls = 0

            async def search(self, query: str) -> list[SearchResult]:
                self.calls += 1
                if self.calls == 6:
                    fast_finished.set()
                return []

        slow = SlowProvider()
        service = SearchService(
            [slow, FastProvider()], max_concurrent_per_provider=2,
        )
        searches = asyncio.gather(*(service.search(str(i)) for i in range(6)))
        try:
            async with asyncio.timeout(1):
                await slow_full.wait()
                await fast_finished.wait()
            assert slow.active == 2
        finally:
            release_slow.set()
            responses = await searches

        assert slow.peak == 2
        assert slow.active == 0
        assert all(response.failed_sources == [] for response in responses)

    asyncio.run(run())


def test_waiting_for_slot_uses_deadline_without_starting_provider() -> None:
    async def run() -> None:
        class BusyProvider:
            source_name = "Busy"
            called = False

            async def search(self, query: str) -> list[SearchResult]:
                self.called = True
                return []

        provider = BusyProvider()
        semaphore = asyncio.Semaphore(1)
        await semaphore.acquire()
        try:
            response = await asyncio.wait_for(
                _search_provider(
                    provider,
                    "test",
                    semaphore=semaphore,
                    deadline=asyncio.get_running_loop().time() + 0.01,
                    timeout_seconds=0.01,
                ),
                timeout=1,
            )
            assert response.failed_source == "Busy"
            assert response.results == []
            assert not provider.called
        finally:
            semaphore.release()

        # Cancelling a waiter must not consume the next available slot.
        await asyncio.wait_for(semaphore.acquire(), timeout=1)
        semaphore.release()

    asyncio.run(run())


def test_all_providers_receive_same_search_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_deadlines: list[float] = []
    original_timeout_at = asyncio.timeout_at

    def record_deadline(deadline: float) -> asyncio.Timeout:
        seen_deadlines.append(deadline)
        return original_timeout_at(deadline)

    monkeypatch.setattr(asyncio, "timeout_at", record_deadline)

    async def run() -> None:
        providers = []
        for name in ("First", "Second", "Third"):
            provider = AsyncMock()
            provider.source_name = name
            provider.search.return_value = []
            providers.append(provider)
        await SearchService(providers).search("test")

    asyncio.run(run())
    assert len(seen_deadlines) == 3
    assert len(set(seen_deadlines)) == 1


@pytest.mark.parametrize("failure", ["timeout", "error", "cancel"])
def test_slot_is_released_after_unsuccessful_operation(failure: str) -> None:
    async def run() -> None:
        started = asyncio.Event()

        class Provider:
            source_name = "Source"

            async def search(self, query: str) -> list[SearchResult]:
                if query == "next":
                    return []
                started.set()
                if failure == "error":
                    raise RuntimeError("broken provider")
                await asyncio.Event().wait()
                return []

        service = SearchService(
            [Provider()], search_timeout_seconds=0.02,
            max_concurrent_per_provider=1,
        )
        task = asyncio.create_task(service.search("first"))
        if failure == "cancel":
            await asyncio.wait_for(started.wait(), timeout=1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            response = await asyncio.wait_for(task, timeout=1)
            assert response.failed_sources == ["Source"]

        response = await asyncio.wait_for(service.search("next"), timeout=1)
        assert response.failed_sources == []

    asyncio.run(run())
