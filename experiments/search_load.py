import asyncio
import json
import logging
import platform
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from time import perf_counter

import structlog

from bot.models.search_result import SearchResult
from bot.services.search_service import SearchService

REPEATS = 5
QUERY = "python asyncio"
DELAYS = {"Wikipedia": 0.05, "GitHub": 0.10, "Stack Overflow": 0.20}


@dataclass
class SimulatedProvider:
    source_name: str
    delay_seconds: float

    async def search(self, query: str) -> list[SearchResult]:
        await asyncio.sleep(self.delay_seconds)
        return [SearchResult(
            title=query,
            description=f"Simulated result from {self.source_name}",
            url="https://example.com/",
            source=self.source_name,
        )]


async def sequential_search(providers: list[SimulatedProvider]) -> list[SearchResult]:
    results = []
    for provider in providers:
        results.extend(await provider.search(QUERY))
    return results


async def main() -> None:
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))
    providers = [SimulatedProvider(name, delay) for name, delay in DELAYS.items()]
    service = SearchService(
        providers=providers,
        search_timeout_seconds=5.0,
        max_concurrent_per_provider=3,
    )
    samples = {"sequential_ms": [], "concurrent_ms": []}

    expected = await sequential_search(providers)
    warmup = await service.search(QUERY)
    assert warmup.results == expected and not warmup.failed_sources

    for repeat in range(REPEATS):
        modes = ("sequential_ms", "concurrent_ms")
        if repeat % 2:
            modes = tuple(reversed(modes))
        for mode in modes:
            started = perf_counter()
            if mode == "sequential_ms":
                results = await sequential_search(providers)
            else:
                response = await service.search(QUERY)
                assert not response.failed_sources
                results = response.results
            elapsed_ms = (perf_counter() - started) * 1000
            assert results == expected, "Both modes must return the same results"
            samples[mode].append(round(elapsed_ms, 3))

    sequential_ms = median(samples["sequential_ms"])
    concurrent_ms = median(samples["concurrent_ms"])
    report = {
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "mode": "simulated_io",
        "query": QUERY,
        "repeats": REPEATS,
        "warmup_pairs": 1,
        "provider_delays_seconds": DELAYS,
        "results_per_search": len(expected),
        "search_timeout_seconds": 5.0,
        "max_concurrent_per_provider": 3,
        "samples": samples,
        "median_sequential_ms": sequential_ms,
        "median_concurrent_ms": concurrent_ms,
        "speedup": round(sequential_ms / concurrent_ms, 3),
    }
    output = Path(__file__).parent / "results" / "search_load.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("| Mode | Median search time |")
    print("|---|---:|")
    print(f"| Sequential | {sequential_ms:.3f} ms |")
    print(f"| Concurrent (`SearchService`) | {concurrent_ms:.3f} ms |")
    print(f"\nSpeedup: **{sequential_ms / concurrent_ms:.2f}x**. Python {platform.python_version()}, {REPEATS} measurements per mode.")


if __name__ == "__main__":
    asyncio.run(main())
