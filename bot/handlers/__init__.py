from aiogram import Router

from . import (
    start_help,
    search,
)


def get_routers() -> list[Router]:
    return [
        start_help.router,
        search.router,
    ]
