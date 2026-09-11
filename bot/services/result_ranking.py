import re

from bot.models.search_result import SearchResult

SOURCE_PRIORITY = {
    "Stack Overflow": 3,
    "GitHub": 2,
    "Wikipedia": 1,
}
MIN_RELEVANCE_SCORE = 2
_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_+#]+")


def rank_results(query: str, results: list[SearchResult]) -> list[SearchResult]:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return results

    scored_results = [
        (result, _calculate_score(query_tokens, result))
        for result in results
    ]
    relevant_results = [
        (result, score)
        for result, score in scored_results
        if score >= MIN_RELEVANCE_SCORE
    ]

    if not relevant_results:
        relevant_results = scored_results

    return [
        result
        for result, _ in sorted(
            relevant_results,
            key=lambda item: (
                item[1],
                SOURCE_PRIORITY.get(item[0].source, 0),
            ),
            reverse=True,
        )
    ]


def _calculate_score(query_tokens: set[str], result: SearchResult) -> int:
    title_tokens = _tokenize(result.title)
    description_tokens = _tokenize(result.description)

    title_matches = len(query_tokens & title_tokens)
    description_matches = len(query_tokens & description_tokens)

    score = title_matches * 3 + description_matches

    if result.source == "Stack Overflow" and "Accepted" in result.description:
        score += 1

    if result.source == "GitHub" and "Python" in result.description:
        score += 1

    return score


def _tokenize(text: str) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN_PATTERN.findall(text)
        if len(token) > 1
    }
