import asyncio
from typing import Protocol

import structlog
from structlog.typing import FilteringBoundLogger

from bot.models.search_response import SearchFailure, SearchResponse
from bot.models.search_result import SearchResult

logger: FilteringBoundLogger = structlog.get_logger()


class SearchProvider(Protocol):
    source_name: str

    async def search(self, query: str) -> list[SearchResult]:
        pass


class SearchService:
    def __init__(self, providers: list[SearchProvider]):
        self._providers = providers

    async def search(self, query: str) -> SearchResponse:
        provider_results = await asyncio.gather(
            *(provider.search(query) for provider in self._providers),
            return_exceptions=True,
        )

        results: list[SearchResult] = []
        failures: list[SearchFailure] = []

        for provider, provider_result in zip(self._providers, provider_results):
            if isinstance(provider_result, Exception):
                await logger.awarning(
                    "Search provider failed",
                    source=provider.source_name,
                    error_type=type(provider_result).__name__,
                    error=str(provider_result),
                )
                failures.append(SearchFailure(source=provider.source_name))
                continue

            results.extend(provider_result)

        return SearchResponse(results=results, failures=failures)
