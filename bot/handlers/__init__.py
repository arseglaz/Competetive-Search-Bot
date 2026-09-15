from aiogram import Router

from . import (
    start,
    search,
)


def get_routers() -> list[Router]:
    return [
        start.router,
        search.router,
    ]
