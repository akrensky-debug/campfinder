"""Pydantic v2 models for lead capture and camp submissions."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class LeadCreate(BaseModel):
    parent_email: str = Field(..., min_length=3)
    first_name: str | None = None
    parent_zip: str | None = None
    child_age_band: str | None = None       # e.g. "6-8", "9-11"
    weeks_needed: int | None = None
    interests: list[str] | None = None
    target_camp_id: str | None = None
    search_context: dict[str, Any] | None = None
    message: str | None = None
    consent_flag: bool = False
    source: str = "search_gate"
    matched_camp_ids: list[str] | None = None


class LeadResponse(BaseModel):
    id: UUID
    parent_email: str
    lead_status: str
    created_at: datetime | None = None


class CampSubmissionCreate(BaseModel):
    name: str
    city: str
    state: str = Field(..., min_length=2, max_length=2)
    zip: str | None = None
    camp_type: str | None = None
    website_url: str | None = None
    email: str
    phone: str | None = None
    contact_name: str | None = None
    contact_role: str | None = None
    age_min: int | None = None
    age_max: int | None = None
    description: str | None = None
    primary_categories: list[str] | None = None
    notes: str | None = None


class CampSubmissionResponse(BaseModel):
    id: UUID
    name: str
    status: str
    created_at: datetime | None = None


class ClaimInitiate(BaseModel):
    camp_id: str
    email: str
    contact_name: str | None = None
    role: str | None = None


class ClaimVerify(BaseModel):
    token: str
