from html import escape
import asyncio
from time import perf_counter

import structlog
from structlog.typing import FilteringBoundLogger

from aiogram import Router
from aiogram.types import Message

from bot.models.search_result import SearchResult
from bot.models.search_response import SearchResponse
from bot.services.search_service import SearchService
from bot.request_logging import request_log_context

logger: FilteringBoundLogger = structlog.get_logger(__name__)

SOURCE_ORDER = ["Wikipedia", "GitHub", "Stack Overflow"]
MAX_QUERY_LENGTH = 512
MAX_MESSAGE_LENGTH = 4096
OMITTED_RESULTS_NOTICE = "\nSome results were omitted to fit one message."


router = Router(name="search")


@router.message()
async def search_message(
    message: Message,
    search_service: SearchService,
) -> None:
    with request_log_context(new=True):
        await _search_and_reply(message, search_service)


async def _search_and_reply(message: Message, search_service: SearchService) -> None:
    started = perf_counter()
    query = message.text
    if query is None or not query.strip():
        await logger.ainfo("search_skipped", reason="empty_or_non_text_message")
        await _send_reply(message, "Please send a text search query", started)
        return

    query = query.strip()
    if len(query) > MAX_QUERY_LENGTH:
        await logger.ainfo("search_skipped", reason="query_too_long")
        await _send_reply(
            message, f"Please shorten your search query to {MAX_QUERY_LENGTH} characters or fewer.", started,
        )
        return

    search_response = await search_service.search(query)
    await _send_reply(message, _format_response(query, search_response), started)


def _format_response(query: str, search_response: SearchResponse) -> str:
    results = search_response.results
    displayed_query = escape(_shorten(query, 120))

    if results:
        header = f'Found {len(results)} result(s) for "{displayed_query}":'
    elif search_response.failed_sources:
        header = f'Search incomplete for "{displayed_query}": no results available.'
    else:
        header = f'No results found for "{displayed_query}".'

    footer = ""
    if search_response.failed_sources:
        failed_sources = ", ".join(
            escape(source)
            for source in search_response.failed_sources
        )
        footer = f"\n\nUnavailable sources: {failed_sources}"

    sections = [
        _format_section(source, results)
        for source in SOURCE_ORDER
        if source not in search_response.failed_sources
    ] if results else []
    full_text = "\n".join([header, *(line for section in sections for line in section)]) + footer
    if _message_length(full_text) <= MAX_MESSAGE_LENGTH:
        return full_text

    text = header
    suffix = "\n" + OMITTED_RESULTS_NOTICE + footer
    for section in sections:
        heading, *entries = section
        if not entries:
            if _message_length(text + "\n" + heading + suffix) <= MAX_MESSAGE_LENGTH:
                text += "\n" + heading
            continue
        included_heading = False
        for entry in entries:
            block = ("" if included_heading else "\n" + heading) + "\n" + entry
            if _message_length(text + block + suffix) <= MAX_MESSAGE_LENGTH:
                text += block
                included_heading = True
    return text + suffix


def _message_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 1] + "…"


async def _send_reply(message: Message, text: str, started: float) -> None:
    sending_started = perf_counter()
    try:
        await message.answer(text)
    except asyncio.CancelledError:
        await logger.ainfo(
            "reply_cancelled", duration_ms=round((perf_counter() - started) * 1000, 3),
        )
        raise
    except Exception as exc:
        await logger.aexception(
            "reply_failed", error_type=type(exc).__name__, exc_info=exc,
            duration_ms=round((perf_counter() - started) * 1000, 3),
        )
        raise
    await logger.ainfo(
        "reply_sent",
        duration_ms=round((perf_counter() - started) * 1000, 3),
        send_duration_ms=round((perf_counter() - sending_started) * 1000, 3),
    )


def _format_section(source_name: str, results: list[SearchResult]) -> list[str]:
    source_results = [
        result
        for result in results
        if result.source == source_name
    ]

    if not source_results:
        return [f"\n<b>{source_name}</b>\nNo results found."]

    lines: list[str] = [f"\n<b>{source_name}</b>"]
    for i, item in enumerate(source_results, start=1):
        lines.append(
            f"\n<b>{i}. {escape(_shorten(item.title, 120))}</b>\n"
            f"{escape(_shorten(item.description, 240))}\n"
            f'<a href="{escape(item.url, quote=True)}">Open result</a>'
        )

    return lines
