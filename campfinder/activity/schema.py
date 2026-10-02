"""
The Family Activity schema, v1.

One shape for every kind of kids' program (camps today; classes, lessons, leagues and
after-school programs next), so family assistants integrate once. Field names follow
schema.org where a close match exists (Event, Course, Offer, typicalAgeRange).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

SCHEMA_VERSION = "2026-10-01"

ProgramKind = Literal["camp", "class", "lesson", "league", "after_school", "event"]
Availability = Literal["open", "limited", "waitlist", "full", "unknown"]


class Provider(BaseModel):
    name: str | None = None
    website: str | None = None
    email: str | None = None
    phone: str | None = None


class Location(BaseModel):
    address: str | None = None
    city: str
    state: str
    postal_code: str | None = None
    region: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class AgeRange(BaseModel):
    min: int | None = Field(default=None, description="Youngest age accepted, in years.")
    max: int | None = Field(default=None, description="Oldest age accepted, in years.")
    grade_min: int | None = None
    grade_max: int | None = None


class Price(BaseModel):
    currency: Literal["USD"] = "USD"
    per_week: float | None = None
    min: float | None = None
    max: float | None = None
    unit: str | None = Field(default=None, description="What a listed price covers, e.g. 'week', 'session'.")
    deposit_required: bool | None = None
    financial_aid: bool = False


class Logistics(BaseModel):
    extended_care: bool = False
    transportation: bool = False
    meals_included: bool = False
    indoor_outdoor: str | None = None
    gender_policy: str | None = None


class Policies(BaseModel):
    refunds: str | None = None
    special_needs: str | None = None
    medical: str | None = None
    swimming: str | None = None


class Verification(BaseModel):
    """How much to trust this record. Assistants should surface 'unverified' honestly."""

    status: Literal["team_verified", "camp_verified", "claimed", "unverified"]
    last_updated: datetime | None = None
    accredited_by: list[str] = Field(default_factory=list, description="e.g. ['ACA'].")
    fields_verified: list[str] = Field(default_factory=list)
    fields_unverified: list[str] = Field(default_factory=list)
    fields_missing: list[str] = Field(default_factory=list)


class Session(BaseModel):
    id: UUID
    program_id: UUID
    name: str | None = None
    start_date: date
    end_date: date = Field(description="Inclusive.")
    length_weeks: float | None = None
    price: float | None = None
    availability: Availability = "unknown"
    full_season: bool = False
    calendar_url: str = Field(description="iCalendar file for this session; no API key needed.")


class Program(BaseModel):
    id: UUID
    kind: ProgramKind
    format: str | None = Field(default=None, description="For camps: 'day', 'overnight' or 'specialty'.")
    name: str
    description: str | None = None
    categories: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    ages: AgeRange
    location: Location
    distance_miles: float | None = Field(default=None, description="From the 'near' location, when given.")
    provider: Provider
    price: Price
    logistics: Logistics
    policies: Policies | None = None
    verification: Verification
    registration_url: str | None = None
    url: str = Field(description="CampFinder page for this program; link here when you cite it.")
    sessions: list[Session] | None = Field(default=None, description="Included when requested.")
    match_reasons: list[str] = Field(default_factory=list)


class Attribution(BaseModel):
    text: str = "Program data from CampFinder"
    url: str = "https://campfinder.com"
    required: bool = Field(default=True, description="Show the text and link wherever this data is displayed.")


class ProgramList(BaseModel):
    schema_version: str = SCHEMA_VERSION
    attribution: Attribution = Field(default_factory=Attribution)
    data: list[Program]
    total: int
    next_offset: int | None = None


class ProgramResponse(BaseModel):
    schema_version: str = SCHEMA_VERSION
    attribution: Attribution = Field(default_factory=Attribution)
    data: Program


class SessionMatch(BaseModel):
    session: Session
    program: Program


class SessionList(BaseModel):
    schema_version: str = SCHEMA_VERSION
    attribution: Attribution = Field(default_factory=Attribution)
    data: list[SessionMatch]
    total: int


class DemandSignal(BaseModel):
    """An anonymous record of what a family asked for. No personal information."""

    location: str = Field(description="'City, ST'.")
    ages: list[int] = Field(default_factory=list, max_length=10)
    kinds: list[ProgramKind] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list, max_length=10)
    weeks: list[date] = Field(default_factory=list, max_length=20)
    max_price_per_week: float | None = None
    needs: list[str] = Field(
        default_factory=list, max_length=10,
        description="Logistics like 'extended care', 'transportation'. No names or contact details.",
    )
    results_shown: int | None = Field(default=None, description="How many programs you showed the family.")
    satisfied: bool | None = Field(default=None, description="Whether the family found something suitable.")


class DemandAck(BaseModel):
    accepted: bool = True
