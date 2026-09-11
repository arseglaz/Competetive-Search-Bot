from aiogram import Router
from aiogram.filters import CommandStart    # [1]
from aiogram.types import Message

router = Router(name="start")


@router.message(CommandStart())             # [2]
async def cmd_start(
        message: Message,
) -> None:
    await message.answer("Привет!")


@router.message()                           # [3]
async def any_message(
        message: Message,
) -> None:
    await message.answer("Я тебя не понимаю")