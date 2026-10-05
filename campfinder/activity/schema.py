"""
The Family Activity schema, v1.

One shape for every kind of kids' program (camps, classes, lessons, leagues, after-school
programs), so family assistants integrate once. Field names follow schema.org where a
close match exists (Event, Course, Offer, typicalAgeRange).

Versions (all additive; nothing is renamed or removed within v1):
- 2026-10-01: camps and their dated sessions.
- 2026-10-02: year-round programs. A Session can now be a recurring offering with a
  `schedule` (weekdays, times, RRULE, no-class dates), `term`, `skill_level`, `prices`
  (full term, per class, drop-in, trial...), and an `enrollment` window. Programs gain
  `skill_levels`, `trial_available` and `membership_required`. Session dates may be null
  for an ongoing program with no published term. Verification adds `provider_verified`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

SCHEMA_VERSION = "2026-10-02"

ProgramKind = Literal["camp", "class", "lesson", "league", "after_school", "event"]
Availability = Literal["open", "limited", "waitlist", "full", "unknown"]
Weekday = Literal["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
PriceType = Literal["full_term", "per_class", "drop_in", "trial", "registration_fee", "membership", "monthly"]
VerificationStatus = Literal["team_verified", "provider_verified", "camp_verified", "claimed", "unverified"]


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
    per_class: float | None = Field(
        default=None, description="Lowest price of a single class or lesson, stated or full-term price divided by class count.",
    )
    options: list["PriceOption"] = Field(default_factory=list, description="Every listed price, for recurring programs.")


class PriceOption(BaseModel):
    type: PriceType
    amount: float
    currency: Literal["USD"] = "USD"
    audience: str | None = Field(default=None, description="Who pays this price, e.g. 'member', 'non-member', 'resident'.")
    covers: str | None = Field(default=None, description="e.g. '8 classes', 'per month'.")
    notes: str | None = None


class Schedule(BaseModel):
    """When a recurring offering meets. Times are local wall-clock times in `timezone`."""

    days_of_week: list[Weekday] = Field(default_factory=list)
    start_time: str | None = Field(default=None, description="'HH:MM', 24-hour.")
    end_time: str | None = Field(default=None, description="'HH:MM', 24-hour.")
    timezone: str = "America/New_York"
    rrule: str | None = Field(default=None, description="RFC 5545 recurrence rule, e.g. 'FREQ=WEEKLY;BYDAY=TU'.")
    exdates: list[date] = Field(default_factory=list, description="Published no-class dates (holidays, breaks).")
    meeting_count: int | None = Field(default=None, description="Number of meetings in the term, when the provider states it.")
    next_meeting: date | None = None
    summary: str | None = Field(default=None, description="Plain-language summary, e.g. 'Tuesdays 4–4:30pm'.")


class EnrollmentWindow(BaseModel):
    opens: date | None = None
    closes: date | None = None
    status: Literal["upcoming", "open", "closed", "unknown"] = "unknown"


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

    status: VerificationStatus
    last_updated: datetime | None = None
    accredited_by: list[str] = Field(default_factory=list, description="e.g. ['ACA'].")
    fields_verified: list[str] = Field(default_factory=list)
    fields_unverified: list[str] = Field(default_factory=list)
    fields_missing: list[str] = Field(default_factory=list)


class Session(BaseModel):
    """A camp session (a dated block of days) or a recurring offering of a class, lesson or league."""

    id: UUID
    program_id: UUID
    name: str | None = None
    start_date: date | None = Field(default=None, description="First day. Always set for camps.")
    end_date: date | None = Field(default=None, description="Last day, inclusive. Always set for camps.")
    length_weeks: float | None = None
    price: float | None = Field(default=None, description="Camps: session price. Recurring: lowest full-term price.")
    availability: Availability = "unknown"
    spots_left: int | None = Field(default=None, description="Spots left, when the camp or our team has told us. Null means unknown, not full.")
    spots_updated_at: datetime | None = Field(default=None, description="When spots_left was last set; quote it with the number.")
    full_season: bool = False
    calendar_url: str = Field(description="iCalendar file for this session; no API key needed.")
    # Recurring offerings (classes, lessons, leagues, after-school). Null for camps.
    term: str | None = Field(default=None, description="e.g. 'Fall Session 1', 'Spring 2027'.")
    skill_level: str | None = None
    ages: AgeRange | None = Field(default=None, description="When this offering's ages differ from the program's.")
    location: Location | None = Field(default=None, description="When this offering meets somewhere other than the program's location.")
    schedule: Schedule | None = None
    prices: list[PriceOption] = Field(default_factory=list)
    enrollment: EnrollmentWindow | None = None
    drop_in_allowed: bool | None = None


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
    skill_levels: list[str] = Field(default_factory=list, description="Levels offered, e.g. ['Stage 1', 'Stage 2'].")
    trial_available: bool | None = Field(default=None, description="A trial or first class at reduced or no cost.")
    trial_notes: str | None = None
    membership_required: bool | None = None


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
    days_of_week: list[Weekday] = Field(default_factory=list, description="Days the family can do a recurring activity.")
    earliest_start: str | None = Field(default=None, description="'HH:MM'. Earliest a recurring activity can start.")
    latest_end: str | None = Field(default=None, description="'HH:MM'. Latest it can end.")
    max_price_per_week: float | None = None
    needs: list[str] = Field(
        default_factory=list, max_length=10,
        description="Logistics like 'extended care', 'transportation'. No names or contact details.",
    )
    results_shown: int | None = Field(default=None, description="How many programs you showed the family.")
    satisfied: bool | None = Field(default=None, description="Whether the family found something suitable.")


class DemandAck(BaseModel):
    accepted: bool = True


Price.model_rebuild()
