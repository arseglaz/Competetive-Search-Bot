import asyncio
import math
import structlog

from dataclasses import dataclass
from typing import Protocol

from bot.models.search_response import SearchResponse
from bot.models.search_result import SearchResult
from bot.providers.errors import ProviderError

logger = structlog.get_logger(__name__)


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
    timeout_seconds: float,
) -> ProviderSearchResponse:
    try:
        async with asyncio.timeout(timeout_seconds):
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
        provider_timeout_seconds: float = 5.0,
    ) -> None:
        if (
            not math.isfinite(provider_timeout_seconds)
            or provider_timeout_seconds <= 0
        ):
            raise ValueError(
                "provider_timeout_seconds must be finite and greater than zero"
            )

        self._providers = providers
        self._providers_timeout_seconds = provider_timeout_seconds

    async def search(self, query: str) -> SearchResponse:
        provider_responses = await asyncio.gather(
            *(
                _search_provider(
                    provider,
                    query,
                    timeout_seconds=self._providers_timeout_seconds
                )
                for provider in self._providers)
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
