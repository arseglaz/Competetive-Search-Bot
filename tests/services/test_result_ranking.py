from bot.models.search_result import SearchResult
from bot.services.result_ranking import rank_results


def test_rank_results_prefers_title_matches() -> None:
    weak_result = SearchResult(
        title="Event computing",
        description="Mentions python asyncio semaphore in a long snippet.",
        url="https://example.com/event",
        source="Wikipedia",
    )
    strong_result = SearchResult(
        title="Using a semaphore with asyncio in Python",
        description="Score: 12 | Answers: 2 | Accepted",
        url="https://example.com/semaphore",
        source="Stack Overflow",
    )

    ranked_results = rank_results(
        "python asyncio semaphore",
        [weak_result, strong_result],
    )

    assert ranked_results[0] == strong_result


def test_rank_results_filters_irrelevant_results_when_relevant_exists() -> None:
    irrelevant_result = SearchResult(
        title="Event computing",
        description="Generic operating system article.",
        url="https://example.com/event",
        source="Wikipedia",
    )
    relevant_result = SearchResult(
        title="Python asyncio semaphore crawler",
        description="Python | 10 stars",
        url="https://example.com/repo",
        source="GitHub",
    )

    ranked_results = rank_results(
        "python asyncio semaphore",
        [irrelevant_result, relevant_result],
    )

    assert ranked_results == [relevant_result]


def test_rank_results_keeps_original_results_when_all_are_weak() -> None:
    first_result = SearchResult(
        title="Event computing",
        description="Generic operating system article.",
        url="https://example.com/event",
        source="Wikipedia",
    )
    second_result = SearchResult(
        title="Coroutine",
        description="General programming article.",
        url="https://example.com/coroutine",
        source="Wikipedia",
    )

    ranked_results = rank_results(
        "python asyncio semaphore",
        [first_result, second_result],
    )

    assert ranked_results == [first_result, second_result]
