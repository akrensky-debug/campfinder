"""Pydantic models for spot requests, alerts, claims, submissions and events."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Spot requests ──────────────────────────────────────────────────────────

class SpotRequestCreate(BaseModel):
    child_id: UUID
    session_id: UUID
    parent_note: str | None = Field(default=None, max_length=1000)


class SpotRequestResponse(BaseModel):
    id: UUID
    child_id: UUID
    child_first_name: str | None = None
    camp_id: UUID
    camp_name: str | None = None
    session_id: UUID
    session_name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    price: float | None = None
    status: str
    parent_note: str | None = None
    camp_note: str | None = None
    responded_at: datetime | None = None
    created_at: datetime

    @classmethod
    def from_row(cls, r: dict[str, Any]) -> "SpotRequestResponse":
        data = {k: v for k, v in r.items() if k in cls.model_fields}
        data["price"] = float(r["price"]) if r.get("price") is not None else None
        return cls(**data)


class SpotRequestAnswer(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    answer: Literal["confirm", "decline"]
    camp_note: str | None = Field(default=None, max_length=1000)


# ── Registration alerts ────────────────────────────────────────────────────

class AlertCreate(BaseModel):
    email: EmailStr
    camp_id: UUID


class AlertResponse(BaseModel):
    id: UUID
    camp_id: UUID
    status: str
    created_at: datetime


# ── Operators ──────────────────────────────────────────────────────────────

class ClaimInitiate(BaseModel):
    camp_id: UUID
    email: EmailStr
    contact_name: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, max_length=80)


class CampSubmissionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    city: str = Field(min_length=2, max_length=80)
    state: str = Field(min_length=2, max_length=2)
    zip: str | None = Field(default=None, pattern=r"^\d{5}(-\d{4})?$")
    camp_type: Literal["day", "sleepaway", "specialty"] | None = None
    website_url: str | None = Field(default=None, max_length=500)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    contact_name: str | None = Field(default=None, max_length=120)
    contact_role: str | None = Field(default=None, max_length=80)
    age_min: int | None = Field(default=None, ge=0, le=21)
    age_max: int | None = Field(default=None, ge=0, le=21)
    description: str | None = Field(default=None, max_length=4000)
    primary_categories: list[str] = Field(default_factory=list, max_length=10)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("state")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class CampSubmissionResponse(BaseModel):
    id: UUID
    name: str
    status: str
    created_at: datetime


# ── Analytics ──────────────────────────────────────────────────────────────

ALLOWED_EVENTS = {
    "page_view", "search_submitted", "results_viewed", "camp_detail_viewed",
    "outbound_site_clicked", "planner_used", "compare_used", "alert_created",
    "spot_request_started", "spot_request_submitted", "camp_submission_started",
    "claim_flow_started", "signup_started", "signup_completed",
}


class AnalyticsEvent(BaseModel):
    event: str = Field(max_length=60)
    session_id: str | None = Field(default=None, max_length=64)
    page: str | None = Field(default=None, max_length=300)
    properties: dict[str, str | int | float | bool | None] | None = None

    @field_validator("event")
    @classmethod
    def _known_event(cls, v: str) -> str:
        if v not in ALLOWED_EVENTS:
            raise ValueError("unknown event")
        return v

    @field_validator("properties")
    @classmethod
    def _small_and_anonymous(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is None:
            return None
        if len(v) > 20:
            raise ValueError("too many properties")
        for key, value in v.items():
            if "email" in key.lower() or "phone" in key.lower() or "name" in key.lower():
                raise ValueError("identifying properties are not accepted")
            if isinstance(value, str) and (len(value) > 200 or "@" in value):
                raise ValueError("property value not accepted")
        return v
