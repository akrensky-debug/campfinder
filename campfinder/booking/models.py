"""Registration day: windows, tracked registrations, form mappings, packages, reminders."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Status = Literal["watching", "registered", "waitlisted", "cancelled"]
PaymentStatus = Literal["unpaid", "deposit", "paid", "refunded"]


# ---------------------------------------------------------------------------
# Tracked registrations
# ---------------------------------------------------------------------------

class RegistrationCreate(BaseModel):
    camp_id: UUID
    session_id: UUID | None = None
    child_name: str | None = Field(default=None, max_length=80, description="First name, as in the family profile.")
    opens_at: datetime | None = Field(default=None, description="When registration opens, if the family knows and we don't.")
    notes: str | None = Field(default=None, max_length=1000)


class RegistrationUpdate(BaseModel):
    """What the parent records after she registers, joins a waitlist or pays. Only fields sent are changed."""
    session_id: UUID | None = None
    child_name: str | None = Field(default=None, max_length=80)
    status: Status | None = None
    payment_status: PaymentStatus | None = None
    amount_paid: float | None = Field(default=None, ge=0, le=100000)
    paid_on: date | None = None
    balance_due: float | None = Field(default=None, ge=0, le=100000)
    payment_due_date: date | None = None
    forms_due_date: date | None = None
    opens_at: datetime | None = None
    confirmation_number: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=1000)
    remind: bool | None = None


class Registration(BaseModel):
    id: UUID
    camp_id: UUID
    camp_name: str
    session_id: UUID | None = None
    session_name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    child_name: str | None = None
    status: Status
    payment_status: PaymentStatus
    amount_paid: float | None = None
    paid_on: date | None = None
    balance_due: float | None = None
    payment_due_date: date | None = None
    forms_due_date: date | None = None
    opens_at: datetime | None = None
    opens_at_source: Literal["camp", "family"] | None = Field(
        default=None, description="camp: from our verified data; family: entered by the parent.")
    closes_at: datetime | None = None
    registration_url: str | None = None
    confirmation_number: str | None = None
    notes: str | None = None
    remind: bool = True
    next_step: str = Field(description="One plain-language line: what to do next, and when.")
    created_at: datetime


# ---------------------------------------------------------------------------
# Registration forms and packages
# ---------------------------------------------------------------------------

class FormField(BaseModel):
    question: str = Field(max_length=200, description="As the camp's form words it.")
    kit_field: str | None = Field(
        default=None, description="'household.<field>', 'child.<field>' or 'child.name'; null if the kit can't answer it.")
    required: bool = True


class FormFieldStatus(FormField):
    label: str | None = Field(default=None, description="The kit's name for the field.")
    ready: bool | None = Field(
        default=None, description="True if the kit has an answer for every chosen kid; null when the kit is unavailable.")
    missing_for: list[str] = Field(default_factory=list, description="Kids whose kit lacks this answer.")


class RegistrationFormView(BaseModel):
    camp_id: UUID
    typical: bool = Field(description="True when we don't have this camp's form yet and show what most camp forms ask.")
    platform: str | None = None
    form_url: str | None = None
    verified_at: datetime | None = None
    fields: list[FormFieldStatus]


class PackageRequest(BaseModel):
    camp_id: UUID
    children: list[str] = Field(default_factory=list, max_length=10)
    registration_id: UUID | None = None


class PackagePreview(BaseModel):
    """Exactly what would be shared, before anything is shared."""
    recipient: str
    camp_id: UUID
    children: list[str]
    household_fields: list[str]
    child_fields: list[str]
    labels: dict[str, str]
    missing: list[str] = Field(description="Questions the form asks that the kit has no answer for yet.")
    not_in_kit: list[str] = Field(description="Questions the parent answers on the camp's form herself.")
    expires_in_days: int = 30
    typical: bool


class PackageConfirm(PackageRequest):
    household_fields: list[str] = Field(description="The fields the parent approved; may be fewer than proposed.")
    child_fields: list[str]
    expires_in_days: int = Field(default=30, ge=1, le=365)
    confirm: bool = Field(description="Must be true: the parent pressed Share on the preview.")


# ---------------------------------------------------------------------------
# Register-now checklist
# ---------------------------------------------------------------------------

class ChecklistStep(BaseModel):
    key: str
    text: str
    done: bool | None = None
    href: str | None = None


class RegisterChecklist(BaseModel):
    camp_id: UUID
    camp_name: str
    session_id: UUID | None = None
    session_name: str | None = None
    registration_url: str | None = Field(description="Deep link to the camp's own registration page.")
    opens_at: datetime | None = None
    opens_at_source: Literal["camp", "family"] | None = None
    closes_at: datetime | None = None
    price: float | None = None
    availability: str | None = None
    refund_policy: str | None = None
    form: RegistrationFormView
    kit_available: bool
    shares: list[dict] = Field(default_factory=list, description="Active info kit packages for this camp.")
    steps: list[ChecklistStep]
    registration: Registration | None = None


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------

class ReminderPrefs(BaseModel):
    email: str | None = Field(default=None, max_length=200)
    enabled: bool = True
    opens_days: list[int] = Field(default_factory=lambda: [7, 1, 0], max_length=6)
    deadline_days: list[int] = Field(default_factory=lambda: [3, 0], max_length=6)


class ReminderPreview(BaseModel):
    kind: Literal["opens", "payment_due", "forms_due"]
    registration_id: UUID
    due_on: date
    days_before: int
    subject: str
    text: str
