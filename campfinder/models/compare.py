"""Side-by-side comparison request and response."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class CompareRequest(BaseModel):
    camp_ids: list[UUID] = Field(..., min_length=2, max_length=5)
    reference_location: str | None = None


class SessionRange(BaseModel):
    session_id: UUID
    name: str | None
    start_date: str
    end_date: str
    price: float | None


class CampComparison(BaseModel):
    camp_id: UUID
    name: str
    city: str
    state: str
    camp_type: str
    age_min: int | None
    age_max: int | None
    price_min: float | None
    price_max: float | None
    price_per_week: float | None
    session_count: int
    sessions: list[SessionRange]
    transportation: bool
    extended_care: bool
    meals_included: bool
    aca_accredited: bool | None
    verification_status: str
    refund_policy_summary: str | None
    primary_categories: list[str]
    distance_miles: float | None = None


class CompareResponse(BaseModel):
    camps: list[CampComparison]
    differences: list[str]
