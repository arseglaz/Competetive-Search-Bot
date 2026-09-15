from html import escape

from aiogram import Router
from aiogram.types import Message

from bot.models.search_response import SearchResponse
from bot.models.search_result import SearchResult
from bot.services.search_service import SearchService

router = Router(name="search")
SOURCE_ORDER = ["Stack Overflow", "GitHub", "Wikipedia"]
MAX_DESCRIPTION_LENGTH = 180


@router.message()
async def search_message(
    message: Message,
    search_service: SearchService,
) -> None:
    query = message.text
    if not query:
        await message.answer("Please send a text query to search for.")
        return

    search_response = await search_service.search(query)
    await message.answer(format_search_response(query, search_response))


def format_search_response(query: str, search_response: SearchResponse) -> str:
    if not search_response.results and not search_response.failures:
        return f'No results found for "{escape(query)}".'

    if search_response.results:
        lines = [
            f"<b>Results for:</b> <code>{escape(query)}</code>"
        ]
    else:
        lines = [f'No results found for "{escape(query)}".']

    failed_sources = {failure.source for failure in search_response.failures}
    for source_name in SOURCE_ORDER:
        if source_name in failed_sources:
            continue
        lines.extend(_format_section(source_name, search_response.results))

    if search_response.failures:
        lines.append("\n<b>Unavailable sources</b>")
        for failure in search_response.failures:
            lines.append(f"{escape(failure.source)} is temporarily unavailable.")

    return "\n".join(lines)


def _format_section(source_name: str, results: list[SearchResult]) -> list[str]:
    source_results = [
        result
        for result in results
        if result.source == source_name
    ]

    if not source_results:
        return []

    lines = [f"\n<b>{source_name}</b>"]
    for i, item in enumerate(source_results, start=1):
        lines.append(
            f'{i}. <a href="{escape(item.url)}">{escape(item.title)}</a>\n'
            f"   {_format_description(item.description)}"
        )

    return lines


def _shorten_text(text: str) -> str:
    if len(text) <= MAX_DESCRIPTION_LENGTH:
        return text

    return text[: MAX_DESCRIPTION_LENGTH - 1].rstrip() + "..."


def _format_description(text: str) -> str:
    description = escape(_shorten_text(text))
    return "\n   ".join(description.splitlines())
