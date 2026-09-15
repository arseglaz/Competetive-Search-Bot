from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name="start")

START_MESSAGE = (
    "<b>Competitive Search Bot</b>\n"
    "@competitive_search_bot\n\n"
    "Send any text query and I will search across:\n"
    "- Wikipedia articles\n"
    "- GitHub repositories\n"
    "- Stack Overflow questions\n\n"
    "Searches run concurrently. If one source is unavailable, I will still show "
    "results from the others.\n\n"
    "Try: <code>python asyncio semaphore</code>"
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(START_MESSAGE)
