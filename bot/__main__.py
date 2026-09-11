import asyncio

import structlog
from structlog.typing import FilteringBoundLogger

from aiogram import Bot, Dispatcher
from bot.config import Settings
from bot.handlers import get_routers
from bot.logging_config import get_structlog_config

logger: FilteringBoundLogger = structlog.get_logger()

async def main() -> None:
    # Чтение конфигурации (toml-файл или env vars – не важно)
    settings = Settings()
    # Конфигурирование логгера
    structlog.configure(**get_structlog_config(settings.logs))

    # Создание объекта бота. Обязательный аргумент token – читаем токен
    # из конфигурации. Поскольку токен помечен как SecretStr, то необходимо
    # дополнительно вызывать get_secret_value().
    bot = Bot(
        token=settings.bot.token.get_secret_value(),
    )

    # Создание объекта диспетчера и привязка роутеров
    dp = Dispatcher()
    # Небольшой лайфхак: include_routers() принимает на вход
    # произвольное количество аргументов
    # get_routers() возвращает список: [A, B, C,...]
    # и этот список будет передан как набор аргументов:
    # include_routers(A, B, C,...)
    dp.include_routers(*get_routers())

    # Запуск бота в режиме поллинга
    await logger.ainfo("Starting polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await logger.ainfo("Bot stopped")


asyncio.run(main())