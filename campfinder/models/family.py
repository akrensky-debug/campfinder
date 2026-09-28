"""
Pydantic models for the family profile.

Field limits are deliberate: we collect what a camp needs to take a child for
a week, and nothing that would only be useful to an advertiser.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

ZIP_PATTERN = r"^\d{5}(-\d{4})?$"


class FamilyUpdate(BaseModel):
    first_name: str | None = Field(default=None, max_length=80)
    zip: str | None = Field(default=None, pattern=ZIP_PATTERN)
    accept_privacy_policy: bool = False


class FamilyResponse(BaseModel):
    id: UUID
    email: str
    first_name: str | None = None
    zip: str | None = None
    privacy_policy_version: str | None = None
    consented_at: datetime | None = None
    created_at: datetime


class ChildInput(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    birth_year: int = Field(ge=2000, le=2030)
    birth_month: int | None = Field(default=None, ge=1, le=12)
    interests: list[str] = Field(default_factory=list, max_length=20)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("interests")
    @classmethod
    def _clean_interests(cls, v: list[str]) -> list[str]:
        cleaned = [i.strip().lower()[:40] for i in v if i.strip()]
        return list(dict.fromkeys(cleaned))


class ChildUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    birth_year: int | None = Field(default=None, ge=2000, le=2030)
    birth_month: int | None = Field(default=None, ge=1, le=12)
    interests: list[str] | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=2000)


class ChildResponse(BaseModel):
    id: UUID
    first_name: str
    birth_year: int
    birth_month: int | None = None
    age: int
    interests: list[str] = Field(default_factory=list)
    notes: str | None = None
    updated_at: datetime

    @classmethod
    def from_row(cls, r: dict[str, Any], *, today: date | None = None) -> "ChildResponse":
        today = today or date.today()
        age = today.year - r["birth_year"]
        if r.get("birth_month") and today.month < r["birth_month"]:
            age -= 1
        return cls(
            id=r["id"], first_name=r["first_name"], birth_year=r["birth_year"],
            birth_month=r.get("birth_month"), age=max(age, 0),
            interests=list(r.get("interests") or []), notes=r.get("notes"), updated_at=r["updated_at"],
        )


class MedicalInput(BaseModel):
    allergies: str | None = Field(default=None, max_length=2000)
    medications: str | None = Field(default=None, max_length=2000)
    medical_notes: str | None = Field(default=None, max_length=4000)
    emergency_contact_name: str | None = Field(default=None, max_length=120)
    emergency_contact_phone: str | None = Field(default=None, max_length=40)
    pickup_authorized: list[str] = Field(default_factory=list, max_length=10)


class MedicalResponse(MedicalInput):
    child_id: UUID
    updated_at: datetime


class FamilyExport(BaseModel):
    """Everything we hold, in one download."""

    exported_at: datetime
    family: dict[str, Any]
    children: list[dict[str, Any]]
    spot_requests: list[dict[str, Any]]
    registration_alerts: list[dict[str, Any]]
