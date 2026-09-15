from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name="start")

START_MESSAGE = (
    "Hi! I'm a search bot, currently in active development.\n\n"
    "<b>Available now:</b>\n"
    "- Just send me any text, and I'll search Wikipedia for it\n\n"
    "<b>Planned:</b>\n"
    "- GitHub repository search\n"
    "- Stack Overflow question search\n"
    "- Concurrent search across all sources at once\n\n"
    "To try it, just type something and send it, no command needed."
)

@router.message(CommandStart())             # [2]
async def cmd_start(
        message: Message,
) -> None:

    await message.answer(START_MESSAGE)


