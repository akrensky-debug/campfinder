"""Pydantic v2 models for camp submissions and the claim flow."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


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
