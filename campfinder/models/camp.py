"""Pydantic v2 models for camp records."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SessionSummary(BaseModel):
    id: UUID
    name: str | None = None
    start_date: str  # ISO date string
    end_date: str
    length_days: int | None = None
    length_weeks: float | None = None
    price: float | None = None
    full_season: bool = False
    availability: str = "unknown"


class AccreditationSummary(BaseModel):
    status: str  # "confirmed", "not_confirmed"
    source: str | None = None


class TrustSummary(BaseModel):
    verification_status: str
    last_updated: datetime | None = None
    fields_verified: list[str] = Field(default_factory=list)
    fields_unverified: list[str] = Field(default_factory=list)
    fields_missing: list[str] = Field(default_factory=list)
    accreditation: AccreditationSummary


class CampDetail(BaseModel):
    """Full camp record returned by GET /camps/{id}."""

    id: UUID
    name: str
    operator_name: str | None = None
    website_url: str | None = None
    registration_url: str | None = None
    email: str | None = None
    phone: str | None = None
    street_address: str | None = None
    city: str
    state: str
    zip: str
    region: str | None = None
    camp_type: str
    is_day_camp: bool = False
    is_sleepaway: bool = False
    is_specialty: bool = False
    primary_categories: list[str] = Field(default_factory=list)
    secondary_categories: list[str] = Field(default_factory=list)
    gender_policy: str | None = None
    age_min: int | None = None
    age_max: int | None = None
    grade_min: int | None = None
    grade_max: int | None = None
    description_short: str | None = None
    description_full: str | None = None
    activities: list[str] = Field(default_factory=list)
    indoor_outdoor: str | None = None
    sports_focus: bool = False
    arts_focus: bool = False
    stem_focus: bool = False
    nature_focus: bool = False
    travel_field_trips: bool = False
    religious_affiliation: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    price_per_week: float | None = None
    price_per: str | None = None
    deposit_required: bool | None = None
    financial_aid: bool = False
    extended_care: bool = False
    transportation: bool = False
    meals_included: bool = False
    refund_policy_summary: str | None = None
    special_needs_notes: str | None = None
    medical_support_notes: str | None = None
    swim_waterfront_notes: str | None = None
    aca_accredited: bool | None = None
    aca_source_url: str | None = None
    verification_status: str
    last_reviewed_date: datetime | None = None
    last_updated_date: datetime | None = None
    sources: list[str] = Field(default_factory=list)
    parent_review_count: int = 0
    parent_review_avg: float | None = None
    hero_image_url: str | None = None
    gallery_image_urls: list[str] = Field(default_factory=list)
    faq: list[dict[str, Any]] | None = None
    is_active: bool = True
    season_year: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    sessions: list[SessionSummary] = Field(default_factory=list)
    trust_summary: TrustSummary | None = None
    detail_url: str | None = None


class CampSearchResult(BaseModel):
    """Slimmer representation used in search results."""

    id: UUID
    name: str
    city: str
    state: str
    camp_type: str
    is_day_camp: bool = False
    is_sleepaway: bool = False
    is_specialty: bool = False
    primary_categories: list[str] = Field(default_factory=list)
    age_min: int | None = None
    age_max: int | None = None
    price_per_week: float | None = None
    price_min: float | None = None
    price_max: float | None = None
    transportation: bool = False
    extended_care: bool = False
    meals_included: bool = False
    financial_aid: bool = False
    aca_accredited: bool | None = None
    verification_status: str
    last_updated_date: datetime | None = None
    description_short: str | None = None
    hero_image_url: str | None = None
    distance_miles: float | None = None
    match_score: float | None = None
    match_reasons: list[str] = Field(default_factory=list)
    detail_url: str | None = None
