import asyncio

from typing import Protocol

from bot.models.search_result import SearchResult


class SearchProvider(Protocol):
    async def search(self, query: str) -> list[SearchResult]:
        ...


class SearchService:
    def __init__(self, providers: list[SearchProvider]) -> None:
        self._providers = providers

    async def search(self, query: str) -> list[SearchResult]:
        providers_results = await asyncio.gather(
            *(provider.search(query) for provider in self._providers)
        )
        return [
            result
            for results in providers_results
            for result in results
        ]
