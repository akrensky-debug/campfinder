"""POST /api/v1/compare — Side-by-side camp comparison."""

from __future__ import annotations

from fastapi import APIRouter

from campfinder.models.compare import CompareRequest, CompareResponse
from campfinder.services import compare

router = APIRouter()


@router.post("/compare", response_model=CompareResponse, summary="Compare camps")
async def compare_camps(req: CompareRequest) -> CompareResponse:
    """Accept 2–5 camp IDs and return a structured comparison with plain-language differences."""
    return compare.compare_camps(req)
