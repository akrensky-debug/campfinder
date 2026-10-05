"""POST /api/v1/search — Search camps by parent constraints."""

from __future__ import annotations

from fastapi import APIRouter

from campfinder.models.search import SearchRequest, SearchResponse
from campfinder.services.search import run_search

router = APIRouter()


@router.post("/search", response_model=SearchResponse, summary="Search camps")
async def search(req: SearchRequest) -> SearchResponse:
    """
    Search camps by location and optional filters.
    Results are scored and ranked with match_reasons explaining each result.
    """
    return await run_search(req)
