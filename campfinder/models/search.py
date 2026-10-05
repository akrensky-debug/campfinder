"""Search request and response, shared by the API, the agent and the MCP server."""

from __future__ import annotations

from pydantic import BaseModel, Field

from campfinder.models.camp import CampSearchResult


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
