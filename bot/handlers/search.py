from html import escape

from aiogram import Router
from aiogram.types import Message

from bot.models.search_result import SearchResult
from bot.services.search_service import SearchService

SOURCE_ORDER = ["Wikipedia", "GitHub", "Stack Overflow"]


router = Router(name="search")

@router.message()
async def search_message(
    message: Message,
    search_service: SearchService,
) -> None:
    query = message.text
    if query is None or not query.strip():
        await message.answer("Please send a text search query")
        return

    query = query.strip()

    search_response = await search_service.search(query)
    results = search_response.results

    if not results:
        lines: list[str] = [f'No results found for "{escape(query)}".']

        if search_response.failed_sources:
            failed_sources = ", ".join(
                escape(source)
                for source in search_response.failed_sources
            )
            lines.append(f"\nUnavailable sources: {failed_sources}")

        await message.answer("\n".join(lines))
        return

    lines: list[str] = [f'Found {len(results)} result(s) for "{escape(query)}":']
    for source_name in SOURCE_ORDER:
        lines.extend(_format_section(source_name, results))

    if search_response.failed_sources:
        failed_sources = ", ".join(
            escape(source)
            for source in search_response.failed_sources
        )
        lines.append(f"\nUnavailable sources: {failed_sources}")

    await message.answer("\n".join(lines))


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
            f"\n<b>{i}. {escape(item.title)}</b>\n"
            f"{escape(item.description)}\n"
            f'<a href="{escape(item.url, quote=True)}">Open result</a>'
        )

    return lines
