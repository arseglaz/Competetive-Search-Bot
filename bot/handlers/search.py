from html import escape

from aiogram import Router
from aiogram.types import Message

from bot.providers.wikipedia import WikipediaProvider

router = Router(name="search")


@router.message()
async def search_message(
    message: Message,
    wikipedia_provider: WikipediaProvider,
) -> None:
    query = message.text
    if not query:
        await message.answer("Please send a text query to search for.")
        return

    results = await wikipedia_provider.search(query)

    if not results:
        await message.answer(f'No Wikipedia results found for "{escape(query)}".')
        return

    lines = [f'Found {len(results)} result(s) for "{escape(query)}":']
    for i, item in enumerate(results, start=1):
        lines.append(
            f"\n<b>{i}. {escape(item.title)}</b>\n"
            f"{escape(item.description)}\n"
            f'<a href="{escape(item.url)}">Read more</a>'
        )

    await message.answer("\n".join(lines))
