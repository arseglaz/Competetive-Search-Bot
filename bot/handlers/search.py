from html import escape

from aiogram import Router
from aiogram.types import Message

from bot.models.search_result import SearchResult
from bot.providers.github import GitHubProvider
from bot.providers.wikipedia import WikipediaProvider

router = Router(name="search")


@router.message()
async def search_message(
    message: Message,
    wikipedia_provider: WikipediaProvider,
    github_provider: GitHubProvider,
) -> None:
    query = message.text
    if not query:
        await message.answer("Please send a text query to search for.")
        return

    wikipedia_results = await wikipedia_provider.search(query)
    github_results = await github_provider.search(query)
    results = [*wikipedia_results, *github_results]

    if not results:
        await message.answer(f'No results found for "{escape(query)}".')
        return

    lines = [f'Found {len(results)} result(s) for "{escape(query)}":']
    lines.extend(_format_section("Wikipedia", wikipedia_results))
    lines.extend(_format_section("GitHub", github_results))

    await message.answer("\n".join(lines))


def _format_section(source_name: str, results: list[SearchResult]) -> list[str]:
    if not results:
        return [f"\n<b>{source_name}</b>\nNo results found."]

    lines = [f"\n<b>{source_name}</b>"]
    for i, item in enumerate(results, start=1):
        lines.append(
            f"\n<b>{i}. {escape(item.title)}</b>\n"
            f"{escape(item.description)}\n"
            f'<a href="{escape(item.url)}">Open result</a>'
        )

    return lines
