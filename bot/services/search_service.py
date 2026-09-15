import asyncio
from typing import Protocol

import structlog
from structlog.typing import FilteringBoundLogger

from bot.models.search_response import SearchFailure, SearchResponse
from bot.models.search_result import SearchResult
from bot.services.result_ranking import rank_results

logger: FilteringBoundLogger = structlog.get_logger()


class SearchProvider(Protocol):
    source_name: str

    async def search(self, query: str) -> list[SearchResult]:
        pass


class SearchService:
    def __init__(
        self,
        providers: list[SearchProvider],
        provider_timeout_seconds: float,
        max_concurrent_provider_calls: int,
    ):
        self._providers = providers
        self._provider_timeout_seconds = provider_timeout_seconds
        self._semaphore = asyncio.Semaphore(max_concurrent_provider_calls)

    async def search(self, query: str) -> SearchResponse:
        provider_results = await asyncio.gather(
            *(self._search_provider(provider, query) for provider in self._providers),
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

        return SearchResponse(
            results=rank_results(query, results),
            failures=failures,
        )

    async def _search_provider(
        self,
        provider: SearchProvider,
        query: str,
    ) -> list[SearchResult]:
        async with self._semaphore:
            return await asyncio.wait_for(
                provider.search(query),
                timeout=self._provider_timeout_seconds,
            )
