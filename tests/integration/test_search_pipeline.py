"""Real dispatcher/handlers/service/providers; only external API boundaries are fake."""

import asyncio
from contextlib import asynccontextmanager
from html import escape
from xml.etree import ElementTree

import httpx
import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from aiogram.types import Update
from structlog.contextvars import get_contextvars

from bot.handlers import get_routers, search as handler_module
from bot.handlers.start import START_MESSAGE
from bot.providers.github import GitHubProvider
from bot.providers.stackoverflow import StackOverflowProvider
from bot.providers.wikipedia import WikipediaProvider
from bot.services import search_service
from bot.services.search_service import SearchService


SOURCES = {
    "en.wikipedia.org": "Wikipedia",
    "api.github.com": "GitHub",
    "api.stackexchange.com": "Stack Overflow",
}


@pytest.fixture(scope="module")
def dispatcher():
    # Production routers can only be attached once; reuse this dispatcher.
    dp = Dispatcher()
    dp.include_routers(*get_routers())
    return dp


@pytest.fixture
def events(monkeypatch):
    records = []

    class Recorder:
        async def record(self, event, **fields):
            records.append(dict(get_contextvars(), event=event, **fields))

        ainfo = awarning = aexception = record

    recorder = Recorder()
    monkeypatch.setattr(handler_module, "logger", recorder)
    monkeypatch.setattr(search_service, "logger", recorder)
    return records


class TelegramSession(BaseSession):
    def __init__(self, reject=False):
        super().__init__()
        self.reject = reject
        self.sent = []

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):
        raise AssertionError("Unexpected file download")
        yield  # Keep the BaseSession async iterator interface.

    async def make_request(self, bot, method, timeout=None):
        assert isinstance(method, SendMessage), f"Unexpected Telegram method: {method}"
        files = {}
        payload = {
            key: self.prepare_value(value, bot=bot, files=files)
            for key, value in method.model_dump(warnings=False).items()
        }
        self.sent.append((payload, get_contextvars().get("request_id")))
        assert not files
        parsed = ElementTree.fromstring("<message>" + method.text + "</message>")
        visible = "".join(parsed.itertext())
        assert 0 < len(visible.encode("utf-16-le")) // 2 <= 4096
        if self.reject:
            body = {"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"}
            status = 403
        else:
            body = {"ok": True, "result": {
                "message_id": len(self.sent), "date": 1700000000,
                "chat": {"id": int(payload["chat_id"]), "type": "private"},
                "text": method.text,
            }}
            status = 200
        return self.check_response(bot, method, status, self.json_dumps(body)).result


class SearchAPI:
    def __init__(self, mode="success", simultaneous=0):
        self.mode = mode
        self.simultaneous = simultaneous
        self.ready = asyncio.Event()
        self.calls = []
        self.cancelled = []

    async def __call__(self, request):
        source = SOURCES[request.url.host]
        query = request.url.params["srsearch" if source == "Wikipedia" else "q"]
        self.calls.append((source, query, get_contextvars()["request_id"]))
        if self.simultaneous:
            if len(self.calls) == self.simultaneous:
                self.ready.set()
            await self.ready.wait()
        if self.mode == "all_failed" or (source == "GitHub" and self.mode == "http_error"):
            return httpx.Response(500)
        if source == "Wikipedia" and self.mode == "wiki_api_error":
            return httpx.Response(200, json={"error": {"code": "internal_api_error", "info": "Search unavailable"}})
        if source == "GitHub":
            if self.mode == "rate_limit":
                return httpx.Response(429)
            if self.mode == "network_error":
                raise httpx.ConnectError("simulated connection failure", request=request)
            if self.mode == "invalid_json":
                return httpx.Response(200, content=b"not json")
            if self.mode == "timeout":
                try:
                    await asyncio.Event().wait()
                finally:
                    self.cancelled.append(source)
        empty = self.mode == "empty"
        if source == "Wikipedia":
            payload = {"query": {"search": [] if empty else [{
                "title": f"Wiki {query}", "pageid": 42,
                "snippet": '<span class="searchmatch">Async</span> &amp; tasks',
            }]}}
        elif source == "GitHub":
            payload = {"items": [] if empty else [{
                "full_name": f"repo/{query}", "description": "Code <sample> & examples",
                "html_url": "https://github.com/example/repo", "language": "Python",
                "stargazers_count": 7,
            }]}
        else:
            payload = {"items": [] if empty else [{
                "title": f"Question {escape(query)}", "link": "https://stackoverflow.com/questions/42",
                "answer_count": 2, "score": 4, "accepted_answer_id": 43,
            }]}
        if self.mode == "long_results":
            if source == "Wikipedia":
                items = payload["query"]["search"]
                items[0].update(title="😀<&>" * 300, snippet="Long &amp; snippet " * 300)
            else:
                items = payload["items"]
                if source == "GitHub":
                    items[0].update(full_name="😀<&>" * 300, description="Description & details " * 300)
                else:
                    items[0]["title"] = "😀&lt;&amp;&gt;" * 300
            items *= 3
        return httpx.Response(200, json=payload)


def incoming(bot, text="python", chat_id=101):
    message = {
        "message_id": 1, "date": 1700000000,
        "chat": {"id": chat_id, "type": "private"},
        "from": {"id": chat_id, "is_bot": False, "first_name": "Test"},
    }
    if text is None:
        message["sticker"] = {
            "file_id": "test", "file_unique_id": "test", "type": "regular",
            "width": 64, "height": 64, "is_animated": False, "is_video": False,
        }
    else:
        message["text"] = text
        if text == "/start":
            message["entities"] = [{"type": "bot_command", "offset": 0, "length": 6}]
    return Update.model_validate({"update_id": chat_id, "message": message}, context={"bot": bot})


@asynccontextmanager
async def application(api, *, reject=False):
    session = TelegramSession(reject=reject)
    async with Bot(token="123456:TEST_TOKEN", session=session,
                   default=DefaultBotProperties(parse_mode="HTML")) as bot:
        async with httpx.AsyncClient(transport=httpx.MockTransport(api)) as client:
            service = SearchService([
                WikipediaProvider(client, "integration-test"),
                GitHubProvider(client, "integration-test"),
                StackOverflowProvider(client, "integration-test"),
            ], search_timeout_seconds=0.1 if api.mode == "timeout" else 5)
            yield bot, service, session


@pytest.mark.parametrize("mode,outcome,count,failed", [
    ("success", "complete", 3, []),
    ("empty", "empty", 0, []),
    ("http_error", "partial", 2, ["GitHub"]),
    ("rate_limit", "partial", 2, ["GitHub"]),
    ("network_error", "partial", 2, ["GitHub"]),
    ("invalid_json", "partial", 2, ["GitHub"]),
    ("timeout", "partial", 2, ["GitHub"]),
    ("all_failed", "failed", 0, ["Wikipedia", "GitHub", "Stack Overflow"]),
])
def test_message_to_search_to_reply(dispatcher, events, mode, outcome, count, failed):
    async def run():
        api = SearchAPI(mode)
        async with application(api) as (bot, service, session):
            async with asyncio.timeout(2):
                await dispatcher.feed_update(bot, incoming(bot, "  python  "), search_service=service)
            (payload, request_id), = session.sent
            assert payload["chat_id"] == "101"
            assert payload["parse_mode"] == "HTML"
            assert sorted((source, query) for source, query, _ in api.calls) == [
                ("GitHub", "python"), ("Stack Overflow", "python"), ("Wikipedia", "python"),
            ]
            text = payload["text"]
            if count:
                assert text.startswith(f'Found {count} result(s) for "python":')
                assert "Wiki python" in text and "Question python" in text
                assert "Async &amp; tasks" in text
                assert '<a href="https://en.wikipedia.org/?curid=42">Open result</a>' in text
                assert "Answers: 2 | Score: 4 | Accepted answer: Yes" in text
                if not failed:
                    assert "repo/python" in text
                    assert "Code &lt;sample&gt; &amp; examples\nPython | 7 stars" in text
                    assert text.index("<b>Wikipedia</b>") < text.index("<b>GitHub</b>") < text.index("<b>Stack Overflow</b>")
            elif failed:
                assert text.startswith('Search incomplete for "python": no results available.')
            else:
                assert text == 'No results found for "python".'
            if failed:
                assert text.endswith("Unavailable sources: " + ", ".join(failed))
                assert all(f"<b>{source}</b>" not in text for source in failed)
            else:
                assert "Unavailable sources:" not in text
            if mode == "timeout":
                assert api.cancelled == ["GitHub"]
            assert {e["request_id"] for e in events} == {request_id}
            assert {rid for _, _, rid in api.calls} == {request_id}
            summary, = [e for e in events if e["event"] == "search_completed"]
            assert (summary["outcome"], summary["results_count"], summary["failed_sources"]) == (outcome, count, failed)
            assert events[-1]["event"] == "reply_sent"

    asyncio.run(run())


@pytest.mark.parametrize("text", ["/start", None, "   "])
def test_non_search_messages_bypass_providers(dispatcher, events, text):
    async def run():
        api = SearchAPI()
        async with application(api) as (bot, service, session):
            await dispatcher.feed_update(bot, incoming(bot, text), search_service=service)
            (payload, _), = session.sent
            assert payload["text"] == (START_MESSAGE if text == "/start" else "Please send a text search query")
            assert not api.calls
            assert not any(e["event"] == "search_started" for e in events)

    asyncio.run(run())


def test_html_is_escaped_through_entire_pipeline(dispatcher, events):
    async def run():
        api = SearchAPI()
        query = '<b>async</b> & "tasks"'
        async with application(api) as (bot, service, session):
            await dispatcher.feed_update(bot, incoming(bot, query), search_service=service)
            (payload, _), = session.sent
            assert query not in payload["text"]
            assert payload["text"].count(escape(query)) == 4  # Query and three titles.
            assert {q for _, q, _ in api.calls} == {query}

    asyncio.run(run())


def test_concurrent_chats_receive_their_own_reply(dispatcher, events):
    async def run():
        api = SearchAPI(simultaneous=6)
        async with application(api) as (bot, service, session):
            async with asyncio.timeout(2):
                await asyncio.gather(*(
                    dispatcher.feed_update(bot, incoming(bot, query, chat_id), search_service=service)
                    for chat_id, query in [(101, "first"), (202, "second")]
                ))
            assert len(session.sent) == 2
            assert {payload["chat_id"] for payload, _ in session.sent} == {"101", "202"}
            assert len({rid for _, rid in session.sent}) == 2
            for payload, rid in session.sent:
                own, other = ("first", "second") if payload["chat_id"] == "101" else ("second", "first")
                assert own in payload["text"] and other not in payload["text"]
                assert payload["text"].startswith("Found 3 result(s)")
                assert {q for _, q, call_id in api.calls if call_id == rid} == {own}
                assert [e["event"] for e in events if e["request_id"] == rid].count("reply_sent") == 1

    asyncio.run(run())


def test_telegram_rejection_propagates_without_success_log(dispatcher, events):
    async def run():
        api = SearchAPI()
        async with application(api, reject=True) as (bot, service, session):
            with pytest.raises(TelegramForbiddenError):
                await dispatcher.feed_update(bot, incoming(bot), search_service=service)
            assert len(session.sent) == 1
            assert len(api.calls) == 3
            assert any(e["event"] == "search_completed" for e in events)
            assert events[-1]["event"] == "reply_failed"
            assert not any(e["event"] == "reply_sent" for e in events)

    asyncio.run(run())


def test_wikipedia_api_error_preserves_other_sources(dispatcher, events):
    async def run():
        api = SearchAPI("wiki_api_error")
        async with application(api) as (bot, service, session):
            await dispatcher.feed_update(bot, incoming(bot), search_service=service)
            (payload, _), = session.sent
            assert payload["text"].startswith("Found 2 result(s)")
            assert "repo/python" in payload["text"] and "Question python" in payload["text"]
            assert "<b>Wikipedia</b>" not in payload["text"]
            assert payload["text"].endswith("Unavailable sources: Wikipedia")
            failure, = [e for e in events if e["event"] == "provider_search_failed"]
            assert failure["error_kind"] == "api_error" and failure["status_code"] == 200
            summary, = [e for e in events if e["event"] == "search_completed"]
            assert summary["outcome"] == "partial"
    asyncio.run(run())


def test_large_results_are_sent_once_with_valid_length_and_links(dispatcher, events):
    async def run():
        api = SearchAPI("long_results")
        async with application(api) as (bot, service, session):
            await dispatcher.feed_update(bot, incoming(bot), search_service=service)
            (payload, _), = session.sent
            parsed = ElementTree.fromstring("<message>" + payload["text"] + "</message>")
            assert payload["text"].startswith("Found 9 result(s)")
            assert "…" in payload["text"]
            assert list(parsed.iter("a"))
            assert events[-1]["event"] == "reply_sent"
    asyncio.run(run())


def test_oversized_query_gets_short_reply_without_http_requests(dispatcher, events):
    async def run():
        api = SearchAPI()
        async with application(api) as (bot, service, session):
            await dispatcher.feed_update(bot, incoming(bot, "x" * 4096), search_service=service)
            (payload, _), = session.sent
            assert payload["text"] == "Please shorten your search query to 512 characters or fewer."
            assert not api.calls
            assert events[0]["event"] == "search_skipped"
            assert events[-1]["event"] == "reply_sent"
    asyncio.run(run())
