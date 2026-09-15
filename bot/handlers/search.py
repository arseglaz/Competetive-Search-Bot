from html import escape

from aiogram import Router
from aiogram.types import Message

from bot.models.search_result import SearchResult
from bot.providers.wikipedia import WikipediaProvider

router = Router(name="search")

@router.message()
async def search_message(
        message: Message,
        wikipedia_provider: WikipediaProvider
) -> None:

    query = message.text
    if query is None:
        await message.answer("Please send a text search query")
        return

    results: list[SearchResult] = await wikipedia_provider.search(query)

    if not results:
        await message.answer(f'No Wikipedia results found for "{escape(query)}".')
        return

    lines: list[str] = [f'Found {len(results)} result(s) for "{escape(query)}":']
    for i, item in enumerate(results, start=1):
        lines.append(
            f"\n<b>{i}. {escape(item.title)}</b>\n"
            f"{escape(item.description)}\n"
            f'<a href="{escape(item.url, quote=True)}">Read more</a>'
        )

    await message.answer("\n".join(lines))


