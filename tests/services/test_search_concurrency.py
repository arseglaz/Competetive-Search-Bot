import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from bot.models.search_result import SearchResult
from bot.providers.errors import ProviderError
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


def test_cancelling_waiting_search_preserves_active_search_and_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        active = asyncio.Event()
        release = asyncio.Event()
        waiting = asyncio.Event()
        calls: list[str] = []
        original = search_service._search_provider

        async def observe_start(provider, query, **kwargs):
            if query == "cancelled":
                waiting.set()
            return await original(provider, query, **kwargs)

        monkeypatch.setattr(search_service, "_search_provider", observe_start)

        class Provider:
            source_name = "Source"

            async def search(self, query: str) -> list[SearchResult]:
                calls.append(query)
                if query == "active":
                    active.set()
                    await release.wait()
                return []

        service = SearchService([Provider()], max_concurrent_per_provider=1)
        async with asyncio.timeout(2):
            async with asyncio.TaskGroup() as tasks:
                first = tasks.create_task(service.search("active"))
                await active.wait()
                second = tasks.create_task(service.search("cancelled"))
                # The observer continues into the occupied semaphore before yielding.
                await waiting.wait()
                second.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await second
                assert not first.done()
                assert calls == ["active"]
                release.set()
                assert (await first).failed_sources == []
                assert (await service.search("next")).failed_sources == []
        assert calls == ["active", "next"]
        search_service.logger.awarning.assert_not_awaited()

    asyncio.run(run())


def test_concurrent_searches_keep_results_and_failures_with_their_query() -> None:
    async def run() -> None:
        release = asyncio.Event()
        full = asyncio.Event()
        active = 0

        class Provider:
            def __init__(self, name: str) -> None:
                self.source_name = name

            async def search(self, query: str) -> list[SearchResult]:
                nonlocal active
                active += 1
                if active == 6:
                    full.set()
                try:
                    await release.wait()
                    await asyncio.sleep(0)
                    if self.source_name == "Second" and int(query) % 2:
                        raise ProviderError("query-specific failure", kind="network")
                    return [SearchResult(
                        title=query, description=query,
                        url=f"https://example.com/{query}", source=self.source_name,
                    )]
                finally:
                    active -= 1

        service = SearchService([Provider("First"), Provider("Second")])
        async with asyncio.timeout(2):
            async with asyncio.TaskGroup() as group:
                tasks = [group.create_task(service.search(str(i))) for i in range(20)]
                await full.wait()
                release.set()
        for i, task in enumerate(tasks):
            response = task.result()
            expected_sources = ["First"] if i % 2 else ["First", "Second"]
            assert [r.source for r in response.results] == expected_sources
            assert all(r.title == r.description == str(i) for r in response.results)
            assert all(r.url == f"https://example.com/{i}" for r in response.results)
            assert response.failed_sources == (["Second"] if i % 2 else [])
        assert active == 0

    asyncio.run(run())


def test_timeout_burst_drains_active_calls_and_service_recovers() -> None:
    async def run() -> None:
        class Provider:
            source_name = "Source"
            active = 0
            peak = 0

            async def search(self, query: str) -> list[SearchResult]:
                self.active += 1
                self.peak = max(self.peak, self.active)
                try:
                    if query != "recovery":
                        await asyncio.Event().wait()
                    return [SearchResult(
                        title=query, description=query,
                        url="https://example.com", source=self.source_name,
                    )]
                finally:
                    self.active -= 1

        provider = Provider()
        service = SearchService([provider], search_timeout_seconds=0.1)
        async with asyncio.timeout(2):
            responses = await asyncio.gather(*(service.search(str(i)) for i in range(30)))
            assert all(r.results == [] and r.failed_sources == ["Source"] for r in responses)
            assert provider.active == 0
            assert provider.peak == 3
            response = await service.search("recovery")
            assert [r.title for r in response.results] == ["recovery"]
            assert response.failed_sources == []
            assert provider.active == 0

    asyncio.run(run())
