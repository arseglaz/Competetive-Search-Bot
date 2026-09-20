from pydantic import BaseModel

from bot.models.search_result import SearchResult


class SearchResponse(BaseModel):
    results: list[SearchResult]
    failed_sources: list[str]
