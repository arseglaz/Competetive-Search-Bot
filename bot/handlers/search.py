from html import escape

from aiogram import Router
from aiogram.types import Message

from bot.models.search_result import SearchResult
from bot.services.search_service import SearchService

router = Router(name="search")
SOURCE_ORDER = ["Wikipedia", "GitHub", "Stack Overflow"]


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

    if not search_response.results and not search_response.failures:
        await message.answer(f'No results found for "{escape(query)}".')
        return

    if search_response.results:
        lines = [
            f'Found {len(search_response.results)} result(s) for "{escape(query)}":'
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

    await message.answer("\n".join(lines))


def _format_section(source_name: str, results: list[SearchResult]) -> list[str]:
    source_results = [
        result
        for result in results
        if result.source == source_name
    ]

    if not source_results:
        return [f"\n<b>{source_name}</b>\nNo results found."]

    lines = [f"\n<b>{source_name}</b>"]
    for i, item in enumerate(source_results, start=1):
        lines.append(
            f"\n<b>{i}. {escape(item.title)}</b>\n"
            f"{escape(item.description)}\n"
            f'<a href="{escape(item.url)}">Open result</a>'
        )

    return lines
