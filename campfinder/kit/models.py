"""The family info kit: what camps ask for at registration, entered once."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class Contact(BaseModel):
    name: str = Field(max_length=120)
    relationship: str | None = Field(default=None, max_length=60)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=200)


class Household(BaseModel):
    parents: list[Contact] = Field(default_factory=list, max_length=4)
    home_address: str | None = Field(default=None, max_length=300)
    emergency_contacts: list[Contact] = Field(default_factory=list, max_length=6)
    authorized_pickups: list[Contact] = Field(default_factory=list, max_length=10)
    insurance_provider: str | None = Field(default=None, max_length=120)
    insurance_member_id: str | None = Field(default=None, max_length=60)
    insurance_group_number: str | None = Field(default=None, max_length=60)
    pediatrician_name: str | None = Field(default=None, max_length=120)
    pediatrician_phone: str | None = Field(default=None, max_length=40)


class Child(BaseModel):
    name: str = Field(max_length=80, description="As the family wants it on forms.")
    date_of_birth: date | None = None
    grade: str | None = Field(default=None, max_length=20)
    allergies: str | None = Field(default=None, max_length=1000)
    medications: str | None = Field(default=None, max_length=1000)
    medical_conditions: str | None = Field(default=None, max_length=1000)
    dietary_needs: str | None = Field(default=None, max_length=500)
    swim_ability: str | None = Field(default=None, max_length=200)
    tshirt_size: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=1000)


class InfoKit(BaseModel):
    household: Household = Field(default_factory=Household)
    children: list[Child] = Field(default_factory=list, max_length=10)


HOUSEHOLD_FIELDS = [f for f in Household.model_fields]
CHILD_FIELDS = [f for f in Child.model_fields if f != "name"]


class ShareCreate(BaseModel):
    recipient: str = Field(min_length=1, max_length=120, description="Who this is for, e.g. 'Riverside STEM Camp'.")
    camp_id: UUID | None = None
    children: list[str] = Field(default_factory=list, max_length=10, description="Names of the kids included.")
    household_fields: list[str] = Field(default_factory=list)
    child_fields: list[str] = Field(default_factory=list)
    expires_in_days: int = Field(default=30, ge=1, le=365)


class ShareSummary(BaseModel):
    id: UUID
    recipient: str
    camp_id: UUID | None = None
    children: list[str]
    household_fields: list[str]
    child_fields: list[str]
    fields_shared: int
    fields_total: int
    expires_at: datetime
    revoked_at: datetime | None = None
    open_count: int = 0
    last_opened_at: datetime | None = None
    created_at: datetime
    active: bool


class ShareCreated(BaseModel):
    share: ShareSummary
    url: str = Field(description="Shown once. Send it to the camp; it stops working on expiry or revoke.")


class SharedPackage(BaseModel):
    recipient: str
    expires_at: datetime
    household: dict
    children: list[dict]
