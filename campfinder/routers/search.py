"""POST /api/v1/search: search camps by a parent's constraints."""

from __future__ import annotations

from typing import Literal

import asyncpg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from campfinder.config import Settings, get_settings
from campfinder.database import get_conn
from campfinder.models.camp import CampSearchResult
from campfinder.services.search import search_camps

router = APIRouter()


class SearchRequest(BaseModel):
    location: str = Field(min_length=2, max_length=120, description="City, ST")
    radius_miles: float = Field(default=30.0, ge=1, le=150)
    age: int | None = Field(default=None, ge=0, le=21)
    camp_type: Literal["day", "sleepaway", "specialty"] | None = None
    categories: list[str] | None = Field(default=None, max_length=10)
    weeks: list[str] | None = Field(default=None, max_length=15, description="ISO Monday dates")
    max_price_per_week: float | None = Field(default=None, ge=0)
    requires_transport: bool = False
    requires_extended_care: bool = False
    requires_meals: bool = False
    requires_financial_aid: bool = False
    requires_accreditation: bool = False
    limit: int = Field(default=10, ge=1, le=50)
    sort: Literal["best_match", "distance", "price"] = "best_match"


class SearchResponse(BaseModel):
    results: list[CampSearchResult]
    total: int
    location: str
    radius_miles: float
    location_recognised: bool


@router.post("/search", response_model=SearchResponse, summary="Search camps")
async def search(
    req: SearchRequest,
    conn: asyncpg.Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings),
) -> SearchResponse:
    """Camps within the radius that meet every hard constraint, ranked with match_reasons."""
    camps = await search_camps(conn, **req.model_dump())
    if camps is None:
        return SearchResponse(results=[], total=0, location=req.location,
                              radius_miles=req.radius_miles, location_recognised=False)
    results = [CampSearchResult.from_row(c, site_url=settings.site_url) for c in camps]
    return SearchResponse(results=results, total=len(results), location=req.location,
                          radius_miles=req.radius_miles, location_recognised=True)
