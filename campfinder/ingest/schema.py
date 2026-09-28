"""What the extractor is asked to produce. Every field is optional: unknown stays unknown."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    field: str = Field(description="The listing field this supports, e.g. 'price_per_week' or 'sessions[0].start_date'")
    quote: str = Field(description="Short verbatim quote from the source that supports the value")
    confidence: float = Field(ge=0, le=1, description="How sure the value is correct for the 2027 season")


class ProposedSession(BaseModel):
    name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    age_min: int | None = None
    age_max: int | None = None
    price: float | None = Field(default=None, description="Total price for this session in USD")
    availability: Literal["open", "waitlist", "full", "unknown"] = "unknown"
    registration_opens_at: date | None = None


class ProposedListing(BaseModel):
    name: str | None = None
    operator_name: str | None = None
    website_url: str | None = None
    registration_url: str | None = None
    email: str | None = None
    phone: str | None = None
    street_address: str | None = None
    city: str | None = None
    state: str | None = Field(default=None, description="Two-letter state code")
    zip: str | None = None
    camp_type: Literal["day", "sleepaway", "specialty"] | None = None
    primary_categories: list[str] = Field(default_factory=list, description="From: Sports, Arts, STEM, Nature, Performing arts, Technology, Academic, Faith-based, Special needs")
    age_min: int | None = None
    age_max: int | None = None
    grade_min: int | None = None
    grade_max: int | None = None
    description_short: str | None = Field(default=None, description="One or two plain sentences, in the camp's own terms")
    activities: list[str] = Field(default_factory=list)
    price_per_week: float | None = None
    price_min: float | None = None
    price_max: float | None = None
    deposit_required: bool | None = None
    financial_aid: bool | None = None
    extended_care: bool | None = None
    transportation: bool | None = None
    meals_included: bool | None = None
    refund_policy_summary: str | None = None
    special_needs_notes: str | None = None
    swim_waterfront_notes: str | None = None
    aca_accredited: bool | None = None
    season_year: int | None = None
    sessions: list[ProposedSession] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list, description="Fields a person should look up or ask the camp about")
    warnings: list[str] = Field(default_factory=list, description="Anything odd: old season, conflicting prices, page looks like a directory not the camp itself")

    def confidence_for(self, field: str) -> float | None:
        for e in self.evidence:
            if e.field == field:
                return e.confidence
        return None
