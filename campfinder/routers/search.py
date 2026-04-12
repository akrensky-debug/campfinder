"""POST /api/v1/search — Search camps by parent constraints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from campfinder.database import get_supabase
from campfinder.models.camp import CampSearchResult
from campfinder.services.search import search_camps

router = APIRouter()


class SearchRequest(BaseModel):
    location: str
    radius_miles: float = 30.0
    age: int | None = None
    camp_type: str | None = None
    categories: list[str] | None = None
    weeks: list[str] | None = None
    max_price_per_week: float | None = None
    requires_transport: bool = False
    requires_extended_care: bool = False
    requires_meals: bool = False
    requires_financial_aid: bool = False
    requires_accreditation: bool = False
    limit: int = Field(default=10, ge=1, le=50)
    sort: str = "best_match"


class SearchResponse(BaseModel):
    results: list[CampSearchResult]
    total: int
    location: str
    radius_miles: float


@router.post("/search", response_model=SearchResponse, summary="Search camps")
async def search(req: SearchRequest) -> SearchResponse:
    """
    Search camps by location and optional filters.
    Results are scored and ranked with match_reasons explaining each result.
    """
    client = get_supabase()

    camps = await search_camps(
        client,
        location=req.location,
        radius_miles=req.radius_miles,
        age=req.age,
        camp_type=req.camp_type,
        categories=req.categories,
        weeks=req.weeks,
        max_price_per_week=req.max_price_per_week,
        requires_transport=req.requires_transport,
        requires_extended_care=req.requires_extended_care,
        requires_meals=req.requires_meals,
        requires_financial_aid=req.requires_financial_aid,
        requires_accreditation=req.requires_accreditation,
        limit=req.limit,
        sort=req.sort,
    )

    results = [_to_search_result(c) for c in camps]
    return SearchResponse(
        results=results,
        total=len(results),
        location=req.location,
        radius_miles=req.radius_miles,
    )


def _to_search_result(camp: dict[str, Any]) -> CampSearchResult:
    return CampSearchResult(
        id=camp["id"],
        name=camp["name"],
        city=camp["city"],
        state=camp["state"],
        camp_type=camp["camp_type"],
        is_day_camp=camp.get("is_day_camp") or False,
        is_sleepaway=camp.get("is_sleepaway") or False,
        is_specialty=camp.get("is_specialty") or False,
        primary_categories=list(camp.get("primary_categories") or []),
        age_min=camp.get("age_min"),
        age_max=camp.get("age_max"),
        price_per_week=float(camp["price_per_week"]) if camp.get("price_per_week") else None,
        price_min=float(camp["price_min"]) if camp.get("price_min") else None,
        price_max=float(camp["price_max"]) if camp.get("price_max") else None,
        transportation=camp.get("transportation") or False,
        extended_care=camp.get("extended_care") or False,
        meals_included=camp.get("meals_included") or False,
        financial_aid=camp.get("financial_aid") or False,
        aca_accredited=camp.get("aca_accredited"),
        verification_status=camp.get("verification_status", "unverified"),
        last_updated_date=camp.get("last_updated_date"),
        description_short=camp.get("description_short"),
        hero_image_url=camp.get("hero_image_url"),
        distance_miles=camp.get("distance_miles"),
        match_score=camp.get("match_score"),
        match_reasons=camp.get("match_reasons", []),
        detail_url=camp.get("detail_url"),
    )
