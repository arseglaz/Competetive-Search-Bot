import asyncio
import math
from dataclasses import dataclass
from typing import Protocol

import structlog
from structlog.typing import FilteringBoundLogger

from bot.models.search_response import SearchResponse
from bot.models.search_result import SearchResult
from bot.providers.errors import ProviderError

logger: FilteringBoundLogger = structlog.get_logger(__name__)


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
    *,
    semaphore: asyncio.Semaphore,
    deadline: float,
    timeout_seconds: float,
) -> ProviderSearchResponse:
    try:
        async with asyncio.timeout_at(deadline):
            async with semaphore:
                results = await provider.search(query)
    except TimeoutError:
        await logger.awarning(
            "provider_search_timed_out",
            source=provider.source_name,
            timeout_seconds=timeout_seconds,
        )
        return ProviderSearchResponse(
            results=[],
            failed_source=provider.source_name,
        )
    except ProviderError as exc:
        await logger.awarning(
            "provider_search_failed",
            source=provider.source_name,
            error_kind=exc.kind,
            error_type=type(exc).__name__,
            error_message=str(exc),
            status_code=exc.status_code,
            exc_info=exc,
        )
        return ProviderSearchResponse(
            results=[],
            failed_source=provider.source_name,
        )
    except Exception as exc:
        await logger.aexception(
            "provider_search_unexpected_error",
            source=provider.source_name,
            error_type=type(exc).__name__,
            error_message=str(exc),
            exc_info=exc,
        )
        return ProviderSearchResponse(
            results=[],
            failed_source=provider.source_name,
        )
    return ProviderSearchResponse(results=results)


class SearchService:
    def __init__(
        self,
        providers: list[SearchProvider],
        *,
        search_timeout_seconds: float = 5.0,
        max_concurrent_per_provider: int = 3,
    ) -> None:
        if (
            not math.isfinite(search_timeout_seconds)
            or search_timeout_seconds <= 0
        ):
            raise ValueError(
                "search_timeout_seconds must be finite and greater than zero"
            )
        if (
            isinstance(max_concurrent_per_provider, bool)
            or not isinstance(max_concurrent_per_provider, int)
            or max_concurrent_per_provider <= 0
        ):
            raise ValueError("max_concurrent_per_provider must be a positive integer")

        self._providers = list(providers)
        self._search_timeout_seconds = search_timeout_seconds
        self._provider_semaphores = [
            asyncio.Semaphore(max_concurrent_per_provider)
            for _ in self._providers
        ]

    async def search(self, query: str) -> SearchResponse:
        deadline = asyncio.get_running_loop().time() + self._search_timeout_seconds
        provider_responses = await asyncio.gather(
            *(
                _search_provider(
                    provider,
                    query,
                    semaphore=semaphore,
                    deadline=deadline,
                    timeout_seconds=self._search_timeout_seconds,
                )
                for provider, semaphore in zip(
                    self._providers,
                    self._provider_semaphores,
                    strict=True,
                )
            )
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
