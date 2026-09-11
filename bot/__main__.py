import asyncio

import httpx
import structlog
from structlog.typing import FilteringBoundLogger

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from bot.config import Settings
from bot.handlers import get_routers
from bot.logging_config import get_structlog_config
from bot.providers.github import GitHubProvider
from bot.providers.stackoverflow import StackOverflowProvider
from bot.providers.wikipedia import WikipediaProvider
from bot.services.search_service import SearchService

logger: FilteringBoundLogger = structlog.get_logger()


async def main() -> None:
    settings = Settings()
    structlog.configure(**get_structlog_config(settings.logs))

    bot = Bot(
        token=settings.bot.token.get_secret_value(),
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    async with httpx.AsyncClient() as client:
        wikipedia_provider = WikipediaProvider(
            client=client,
            user_agent=settings.http.user_agent,
        )
        github_provider = GitHubProvider(
            client=client,
            user_agent=settings.http.user_agent,
        )
        stackoverflow_provider = StackOverflowProvider(
            client=client,
            user_agent=settings.http.user_agent,
        )
        search_service = SearchService(
            providers=[
                wikipedia_provider,
                github_provider,
                stackoverflow_provider,
            ],
            provider_timeout_seconds=settings.search.provider_timeout_seconds,
            max_concurrent_provider_calls=settings.search.max_concurrent_provider_calls,
        )

        dp = Dispatcher(search_service=search_service)
        dp.include_routers(*get_routers())

        await logger.ainfo("Starting polling...")
        try:
            await dp.start_polling(bot)
        finally:
            await logger.ainfo("Bot stopped")


asyncio.run(main())
