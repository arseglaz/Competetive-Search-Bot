import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers.search import search_message
from bot.models.search_response import SearchResponse
from bot.models.search_result import SearchResult


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
