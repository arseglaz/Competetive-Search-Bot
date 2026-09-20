import asyncio

from bot.models.search_result import SearchResult
from bot.services.search_service import SearchService


class FakeProvider:
    def __init__(self, source: str, delay: float = 0) -> None:
        self._source = source
        self.source_name = source
        self._delay = delay
        self.received_query: str | None = None

    async def search(self, query: str) -> list[SearchResult]:
        self.received_query = query
        await asyncio.sleep(self._delay)
        return [
            SearchResult(
                title=f"{self._source} title",
                description=f"{self._source} description",
                url=f"https://example.com/{self._source}",
                source=self._source,
            )
        ]


class FailingProvider:
    source_name = "Failing"

    async def search(self, query: str) -> list[SearchResult]:
        raise RuntimeError("provider failed")


def test_search_collects_results_from_all_providers() -> None:
    async def run_search() -> None:
        first_provider = FakeProvider("First")
        second_provider = FakeProvider("Second")
        service = SearchService(providers=[first_provider, second_provider])

        search_response = await service.search("python asyncio")

        assert first_provider.received_query == "python asyncio"
        assert second_provider.received_query == "python asyncio"
        assert [result.source for result in search_response.results] == [
            "First",
            "Second",
        ]
        assert search_response.failed_sources == []

    asyncio.run(run_search())


def test_search_runs_providers_concurrently() -> None:
    async def run_search() -> None:
        service = SearchService(
            providers=[
                FakeProvider("First", delay=0.05),
                FakeProvider("Second", delay=0.05),
            ],
        )

        start_time = asyncio.get_running_loop().time()
        await service.search("python asyncio")
        elapsed = asyncio.get_running_loop().time() - start_time

        assert elapsed < 0.09

    asyncio.run(run_search())


def test_search_keeps_successful_results_when_provider_fails() -> None:
    async def run_search() -> None:
        service = SearchService(providers=[FakeProvider("First"), FailingProvider()])

        search_response = await service.search("python asyncio")

        assert [result.source for result in search_response.results] == ["First"]
        assert search_response.failed_sources == ["Failing"]

    asyncio.run(run_search())
