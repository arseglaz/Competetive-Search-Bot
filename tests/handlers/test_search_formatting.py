from bot.handlers.search import format_search_response
from bot.models.search_response import SearchFailure, SearchResponse
from bot.models.search_result import SearchResult


def test_format_search_response_escapes_external_text() -> None:
    response = SearchResponse(
        results=[
            SearchResult(
                title="<repo>",
                description='Description with "quotes" and <tags>',
                url='https://example.com/search?q=<query>"',
                source="GitHub",
            )
        ],
        failures=[],
    )

    message = format_search_response("<python>", response)

    assert "&lt;python&gt;" in message
    assert '<a href="https://example.com/search?q=&lt;query&gt;&quot;">&lt;repo&gt;</a>' in message
    assert "&lt;tags&gt;" in message


def test_format_search_response_shows_unavailable_sources() -> None:
    response = SearchResponse(
        results=[
            SearchResult(
                title="asyncio",
                description="Python concurrency",
                url="https://example.com/asyncio",
                source="Wikipedia",
            )
        ],
        failures=[SearchFailure(source="GitHub")],
    )

    message = format_search_response("asyncio", response)

    assert "Wikipedia" in message
    assert "GitHub is temporarily unavailable." in message
    assert "<b>GitHub</b>\nNo results found." not in message
    assert "<b>Stack Overflow</b>\nNo results found." not in message


def test_format_search_response_handles_empty_successful_search() -> None:
    response = SearchResponse(results=[], failures=[])

    message = format_search_response("unknown query", response)

    assert message == 'No results found for "unknown query".'


def test_format_search_response_shortens_long_descriptions() -> None:
    response = SearchResponse(
        results=[
            SearchResult(
                title="Long description result",
                description="x" * 220,
                url="https://example.com/long",
                source="Wikipedia",
            )
        ],
        failures=[],
    )

    message = format_search_response("long", response)

    assert "x" * 220 not in message
    assert "..." in message


def test_format_search_response_indents_multiline_descriptions() -> None:
    response = SearchResponse(
        results=[
            SearchResult(
                title="Repository",
                description="Async crawler\nPython | 10 stars",
                url="https://example.com/repo",
                source="GitHub",
            )
        ],
        failures=[],
    )

    message = format_search_response("async crawler", response)

    assert "   Async crawler\n   Python | 10 stars" in message
