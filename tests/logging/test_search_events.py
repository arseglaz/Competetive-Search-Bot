import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from structlog.contextvars import bound_contextvars, get_contextvars

from bot.handlers import search as handler_module
from bot.models.search_result import SearchResult
from bot.providers.errors import ProviderError
from bot.services import search_service


@pytest.fixture
def events(monkeypatch):
    records = []

    class Recorder:
        async def ainfo(self, event, **fields):
            records.append(dict(get_contextvars(), event=event, level="info", **fields))

        async def awarning(self, event, **fields):
            records.append(dict(get_contextvars(), event=event, level="warning", **fields))

        async def aexception(self, event, **fields):
            records.append(dict(get_contextvars(), event=event, level="error", **fields))

    recorder = Recorder()
    monkeypatch.setattr(search_service, "logger", recorder)
    monkeypatch.setattr(handler_module, "logger", recorder)
    return records


class Provider:
    def __init__(self, name, behavior):
        self.source_name = name
        self.behavior = behavior

    async def search(self, query):
        await asyncio.sleep(0)
        if self.behavior == "error":
            raise ProviderError("unavailable", kind="network")
        if self.behavior == "timeout":
            await asyncio.Event().wait()
        if self.behavior == "empty":
            return []
        return [SearchResult(title=query, description="result", url="https://example.com", source=self.source_name)]


@pytest.mark.parametrize(
    "behaviors,outcome,count,failed",
    [
        (["ok", "ok"], "complete", 2, []),
        (["empty", "empty"], "empty", 0, []),
        (["ok", "error"], "partial", 1, ["GitHub"]),
        (["ok", "timeout"], "partial", 1, ["GitHub"]),
        (["error", "error"], "failed", 0, ["Wikipedia", "GitHub"]),
        (["empty", "error"], "failed", 0, ["GitHub"]),
    ],
)
def test_search_and_reply_events(events, behaviors, outcome, count, failed):
    async def run():
        providers = [Provider(name, behavior) for name, behavior in zip(["Wikipedia", "GitHub"], behaviors)]
        service = search_service.SearchService(providers, search_timeout_seconds=0.02)

        async def answer(text):
            assert not any(e["event"] == "reply_sent" for e in events)

        message = SimpleNamespace(text="python", answer=AsyncMock(side_effect=answer))
        await handler_module.search_message(message, service)
        message.answer.assert_awaited_once()
        assert "request_id" not in get_contextvars()

    asyncio.run(run())
    assert events[0]["event"] == "search_started"
    assert events[-1]["event"] == "reply_sent"
    ids = {e["request_id"] for e in events}
    assert len(ids) == 1 and next(iter(ids))
    summary, = [e for e in events if e["event"] == "search_completed"]
    assert (summary["outcome"], summary["results_count"], summary["failed_sources"]) == (outcome, count, failed)
    assert summary["duration_ms"] >= 0
    for record in events:
        if record["event"] == "provider_completed":
            assert record["results_count"] in (0, 1)
            assert record["duration_ms"] >= 0
    if outcome == "empty":
        assert all(e["level"] == "info" for e in events)


def test_concurrent_requests_have_separate_ids_and_restore_context(events):
    async def run():
        both_started = asyncio.Event()
        ids_by_query = {}
        replies = {}

        class SynchronizedProvider(Provider):
            async def search(self, query):
                ids_by_query[query] = get_contextvars()["request_id"]
                if len(ids_by_query) == 2:
                    both_started.set()
                await both_started.wait()
                return await super().search(query)

        service = search_service.SearchService([SynchronizedProvider("Wikipedia", "ok")])

        async def request(query):
            async def answer(text):
                replies[query] = get_contextvars()["request_id"]
            await handler_module.search_message(SimpleNamespace(text=query, answer=answer), service)
            assert get_contextvars()["request_id"] == "parent"

        with bound_contextvars(request_id="parent"):
            async with asyncio.timeout(1):
                await asyncio.gather(request("first"), request("second"))
            assert get_contextvars()["request_id"] == "parent"
        assert ids_by_query == replies
        assert len(set(replies.values())) == 2
        assert "parent" not in replies.values()
        assert {e["request_id"] for e in events} == set(replies.values())

    asyncio.run(run())


@pytest.mark.parametrize("cancel", [False, True])
def test_failed_or_cancelled_delivery_is_not_logged_as_sent(events, cancel):
    async def run():
        error = asyncio.CancelledError() if cancel else RuntimeError("send failed")
        message = SimpleNamespace(text="python", answer=AsyncMock(side_effect=error))
        service = search_service.SearchService([Provider("Wikipedia", "ok")])
        with pytest.raises(type(error)):
            await handler_module.search_message(message, service)
        assert "request_id" not in get_contextvars()
        message.answer.assert_awaited_once()

    asyncio.run(run())
    assert any(e["event"] == "search_completed" for e in events)
    assert not any(e["event"] == "reply_sent" for e in events)
    assert events[-1]["event"] == ("reply_cancelled" if cancel else "reply_failed")


def test_cancelled_search_has_no_completed_or_sent_event(events):
    async def run():
        started = asyncio.Event()

        class WaitingProvider(Provider):
            async def search(self, query):
                started.set()
                await asyncio.Event().wait()

        service = search_service.SearchService([WaitingProvider("Wikipedia", "timeout")])
        message = SimpleNamespace(text="python", answer=AsyncMock())
        async with asyncio.timeout(1):
            task = asyncio.create_task(handler_module.search_message(message, service))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        message.answer.assert_not_awaited()

    asyncio.run(run())
    assert [e["event"] for e in events] == ["search_started", "search_cancelled"]


def test_direct_service_calls_get_fresh_ids(events):
    async def run():
        service = search_service.SearchService([])
        await service.search("first")
        await service.search("second")
        assert "request_id" not in get_contextvars()

    asyncio.run(run())
    assert events[0]["request_id"] == events[1]["request_id"]
    assert events[2]["request_id"] == events[3]["request_id"]
    assert events[0]["request_id"] != events[2]["request_id"]
