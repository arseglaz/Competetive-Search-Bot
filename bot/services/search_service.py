import asyncio

from dataclasses import dataclass
from typing import Protocol

from bot.models.search_response import SearchResponse
from bot.models.search_result import SearchResult


class SearchProvider(Protocol):
    source_name: str

    async def search(self, query: str) -> list[SearchResult]:
        ...


@dataclass
class ProviderSearchResponse:
    results: list[SearchResult]
    failed_source: str | None = None


async def _search_provider(
    provider: SearchProvider,
    query: str,
) -> ProviderSearchResponse:
    try:
        results = await provider.search(query)
    except Exception:
        return ProviderSearchResponse(
            results=[],
            failed_source=provider.source_name,
        )
    return ProviderSearchResponse(results=results)


class SearchService:
    def __init__(self, providers: list[SearchProvider]) -> None:
        self._providers = providers

    async def search(self, query: str) -> SearchResponse:
        provider_responses = await asyncio.gather(
            *(_search_provider(provider, query) for provider in self._providers)
        )

        return SearchResponse(
            results=[
                result
                for response in provider_responses
                for result in response.results
            ],
            failed_sources=[
                response.failed_source
                for response in provider_responses
                if response.failed_source is not None
            ],
        )
