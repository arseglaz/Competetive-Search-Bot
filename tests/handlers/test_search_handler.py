import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from xml.etree import ElementTree

import pytest

from bot.handlers.search import search_message
from bot.handlers import search as handler_module
from bot.models.search_response import SearchResponse
from bot.models.search_result import SearchResult


@pytest.fixture(autouse=True)
def mock_logger(monkeypatch):
    monkeypatch.setattr(handler_module, "logger", AsyncMock())


@pytest.mark.parametrize(
    ("has_results", "failed_sources", "expected"),
    [
        (False, [], 'No results found for "python".'),
        (False, ["GitHub"], "Search incomplete"),
        (
            False,
            ["Wikipedia", "GitHub", "Stack Overflow"],
            "Search incomplete",
        ),
        (True, ["GitHub"], "Found 1 result(s)"),
        (True, [], "Found 1 result(s)"),
    ],
)
def test_search_message(has_results, failed_sources, expected):
    results = (
        [
            SearchResult(
                title="Python",
                description="Programming language",
                url="https://example.com/python",
                source="Wikipedia",
            )
        ]
        if has_results
        else []
    )
    message = SimpleNamespace(text="python", answer=AsyncMock())
    service = SimpleNamespace(
        search=AsyncMock(
            return_value=SearchResponse(
                results=results,
                failed_sources=failed_sources,
            )
        )
    )

    asyncio.run(search_message(message, service))

    service.search.assert_awaited_once_with("python")
    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert expected in text

    if failed_sources:
        assert "Unavailable sources: " + ", ".join(failed_sources) in text
        for source in failed_sources:
            assert f"<b>{source}</b>" not in text
    else:
        assert "Unavailable sources:" not in text

    if has_results:
        assert "<b>Wikipedia</b>" in text
        assert "https://example.com/python" in text
        assert "<b>Stack Overflow</b>\nNo results found." in text


@pytest.mark.parametrize("length", [511, 512, 513, 4096])
def test_long_query_is_rejected_before_search_or_displayed_safely(length):
    query = "a" * length
    message = SimpleNamespace(text=query, answer=AsyncMock())
    service = SimpleNamespace(search=AsyncMock(return_value=SearchResponse(results=[], failed_sources=[])))
    asyncio.run(search_message(message, service))
    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert len(text) <= 4096
    if length > 512:
        service.search.assert_not_awaited()
        assert text == "Please shorten your search query to 512 characters or fewer."
    else:
        service.search.assert_awaited_once_with(query)
        assert text.startswith("No results found")
        assert "…" in text


@pytest.mark.parametrize("content", ["x" * 1000, '😀<&"' * 1000])
@pytest.mark.parametrize("failed", [[], ["GitHub"]])
def test_oversized_results_remain_one_valid_html_message(content, failed):
    results = [
        SearchResult(title=content, description=content,
                     url=f'https://example.com/{source.replace(" ", "")}/{i}?x=1&y=2', source=source)
        for source in ["Wikipedia", "GitHub", "Stack Overflow"] if source not in failed
        for i in range(3)
    ]
    message = SimpleNamespace(text="python", answer=AsyncMock())
    service = SimpleNamespace(search=AsyncMock(return_value=SearchResponse(results=results, failed_sources=failed)))
    asyncio.run(search_message(message, service))
    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    parsed = ElementTree.fromstring("<message>" + text + "</message>")
    visible = "".join(parsed.itertext())
    assert len(visible.encode("utf-16-le")) // 2 <= 4096
    assert "…" in visible
    links = [node.attrib["href"] for node in parsed.iter("a")]
    assert links and set(links) <= {r.url for r in results}
    if len(links) < len(results):
        assert "Some results were omitted" in visible
    if failed:
        assert visible.endswith("Unavailable sources: GitHub")


def test_single_oversized_link_is_skipped_without_cutting_html():
    response = SearchResponse(results=[
        SearchResult(title="Huge link", description="Description", url="https://example.com/" + "x" * 5000, source="Wikipedia"),
        SearchResult(title="Small link", description="Description", url="https://example.com/small", source="Wikipedia"),
    ], failed_sources=[])
    text = handler_module._format_response("python", response)
    parsed = ElementTree.fromstring("<message>" + text + "</message>")
    assert len(text.encode("utf-16-le")) // 2 <= 4096
    assert [a.attrib["href"] for a in parsed.iter("a")] == ["https://example.com/small"]
    assert "Some results were omitted" in text


def test_response_at_length_limit_is_kept_and_over_limit_is_shortened():
    item = SearchResult(title="Title", description="Description", url="https://example.com/", source="Wikipedia")
    response = SearchResponse(results=[item], failed_sources=[])
    initial = handler_module._format_response("python", response)
    item.url += "x" * (4096 - len(initial))
    exact = handler_module._format_response("python", response)
    assert len(exact) == 4096
    assert "Some results were omitted" not in exact
    item.url += "x"
    shortened = handler_module._format_response("python", response)
    ElementTree.fromstring("<message>" + shortened + "</message>")
    assert len(shortened) <= 4096
    assert "Some results were omitted" in shortened
