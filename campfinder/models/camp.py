"""Pydantic models for camp listings as the API returns them."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SessionSummary(BaseModel):
    id: UUID
    name: str | None = None
    start_date: date
    end_date: date
    age_min: int | None = None
    age_max: int | None = None
    price: float | None = None
    full_season: bool = False
    availability: str = "unknown"
    spots_total: int | None = None
    spots_available: int | None = None
    registration_opens_at: datetime | None = None

    @classmethod
    def from_row(cls, s: dict[str, Any]) -> "SessionSummary":
        return cls(
            id=s["id"], name=s.get("name"), start_date=s["start_date"], end_date=s["end_date"],
            age_min=s.get("age_min"), age_max=s.get("age_max"),
            price=float(s["price"]) if s.get("price") is not None else None,
            full_season=s.get("full_season") or False,
            availability=s.get("availability", "unknown"),
            spots_total=s.get("spots_total"), spots_available=s.get("spots_available"),
            registration_opens_at=s.get("registration_opens_at"),
        )


class AccreditationSummary(BaseModel):
    status: str  # "confirmed", "not_confirmed"
    source: str | None = None


class TrustSummary(BaseModel):
    verification_status: str
    last_updated: datetime | None = None
    # When the owner last said "looks right" to the listing email.
    confirmed_by_camp_at: datetime | None = None
    fields_verified: list[str] = Field(default_factory=list)
    fields_unverified: list[str] = Field(default_factory=list)
    fields_missing: list[str] = Field(default_factory=list)
    accreditation: AccreditationSummary


class CampBase(BaseModel):
    id: UUID
    slug: str
    name: str
    city: str
    state: str
    camp_type: str
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
    updated_at: datetime | None = None
    description_short: str | None = None
    hero_image_url: str | None = None
    detail_url: str | None = None


def _money(v: Any) -> float | None:
    return float(v) if v is not None else None


class CampSearchResult(CampBase):
    """Slimmer representation used in search results."""

    distance_miles: float | None = None
    match_score: float | None = None
    match_reasons: list[str] = Field(default_factory=list)
    next_session: SessionSummary | None = None

    @classmethod
    def from_row(cls, c: dict[str, Any], *, site_url: str) -> "CampSearchResult":
        sessions = c.get("sessions") or []
        return cls(
            id=c["id"], slug=c["slug"], name=c["name"], city=c["city"], state=c["state"],
            camp_type=c["camp_type"], primary_categories=list(c.get("primary_categories") or []),
            age_min=c.get("age_min"), age_max=c.get("age_max"),
            price_per_week=_money(c.get("price_per_week")), price_min=_money(c.get("price_min")),
            price_max=_money(c.get("price_max")),
            transportation=c.get("transportation") or False, extended_care=c.get("extended_care") or False,
            meals_included=c.get("meals_included") or False, financial_aid=c.get("financial_aid") or False,
            aca_accredited=c.get("aca_accredited"), verification_status=c["verification_status"],
            updated_at=c.get("updated_at"), description_short=c.get("description_short"),
            hero_image_url=c.get("hero_image_url"), detail_url=f"{site_url}/camps/{c['slug']}",
            distance_miles=round(c["distance_miles"], 1) if c.get("distance_miles") is not None else None,
            match_score=c.get("match_score"), match_reasons=c.get("match_reasons", []),
            next_session=SessionSummary.from_row(sessions[0]) if sessions else None,
        )


class CampDetail(CampBase):
    """Full camp record returned by GET /camps/{id}."""

    operator_name: str | None = None
    website_url: str | None = None
    registration_url: str | None = None
    email: str | None = None
    phone: str | None = None
    street_address: str | None = None
    zip: str
    lat: float
    lng: float
    region: str | None = None
    secondary_categories: list[str] = Field(default_factory=list)
    gender_policy: str | None = None
    grade_min: int | None = None
    grade_max: int | None = None
    description_full: str | None = None
    activities: list[str] = Field(default_factory=list)
    indoor_outdoor: str | None = None
    travel_field_trips: bool = False
    religious_affiliation: str | None = None
    deposit_required: bool | None = None
    refund_policy_summary: str | None = None
    special_needs_notes: str | None = None
    medical_support_notes: str | None = None
    swim_waterfront_notes: str | None = None
    aca_source_url: str | None = None
    last_reviewed_at: datetime | None = None
    sources: list[str] = Field(default_factory=list)
    faq: list[dict[str, Any]] | None = None
    is_active: bool = True
    season_year: int | None = None
    created_at: datetime | None = None
    sessions: list[SessionSummary] = Field(default_factory=list)
    trust_summary: TrustSummary | None = None

    @classmethod
    def from_row(
        cls, c: dict[str, Any], *, sessions: list[dict[str, Any]], trust: TrustSummary, site_url: str
    ) -> "CampDetail":
        data = {k: v for k, v in c.items() if k in cls.model_fields}
        for key in ("price_min", "price_max", "price_per_week"):
            data[key] = _money(c.get(key))
        for key in ("primary_categories", "secondary_categories", "activities", "sources"):
            data[key] = list(c.get(key) or [])
        data["detail_url"] = f"{site_url}/camps/{c['slug']}"
        data["sessions"] = [SessionSummary.from_row(s) for s in sessions]
        data["trust_summary"] = trust
        return cls(**data)
