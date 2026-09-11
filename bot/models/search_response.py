from pydantic import BaseModel

from bot.models.search_result import SearchResult


class SearchFailure(BaseModel):
    source: str


class SearchResponse(BaseModel):
    results: list[SearchResult]
    failures: list[SearchFailure]
