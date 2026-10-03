"""Household members, tasks and the audit log: request and response shapes."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

Role = Literal["owner", "co_parent", "caregiver", "viewer"]
InviteRole = Literal["co_parent", "caregiver", "viewer"]
TaskKind = Literal["dropoff", "pickup", "form", "payment", "packing", "deadline", "other"]
TaskStatus = Literal["open", "done", "skipped"]
ReminderPref = Literal["daily", "day_before", "off"]

ROLE_LABELS = {
    "owner": "Owner",
    "co_parent": "Co-parent",
    "caregiver": "Caregiver",
    "viewer": "Viewer",
}
ROLE_HELP = {
    "co_parent": "the full plan: chat, calendar and every task",
    "caregiver": "the jobs assigned to you, plus the family calendar",
    "viewer": "the family calendar only",
}


class Member(BaseModel):
    """A member as another member sees them. Email is only filled in for the owner and the member themselves."""
    id: UUID
    display_name: str
    role: Role
    status: Literal["invited", "active"]
    email: str | None = None
    kit_access: bool = False
    invite_expires_at: datetime | None = None
    reminder_pref: ReminderPref | None = None
    weekly_summary: bool | None = None
    is_you: bool = False


def _strip_name(v: str | None) -> str | None:
    if v is None:
        return v
    v = " ".join(v.split())
    if not v:
        raise ValueError("Name can't be blank")
    return v


class InviteCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=60, description="What the family calls them, e.g. 'Grandma'.")
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: InviteRole = "caregiver"
    send_email: bool = True

    _name = field_validator("display_name")(_strip_name)


class InviteCreated(BaseModel):
    member: Member
    url: str = Field(description="The invite link. Shown once; expires in 7 days.")
    emailed: bool


class InvitePreview(BaseModel):
    invited_by: str
    display_name: str
    role: Role
    role_help: str
    email_hint: str
    expires_at: datetime
    expired: bool


class MemberUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=60)
    role: InviteRole | None = None
    kit_access: bool | None = None

    _name = field_validator("display_name")(_strip_name)


class MyPrefs(BaseModel):
    reminder_pref: ReminderPref | None = None
    weekly_summary: bool | None = None


class ChecklistItem(BaseModel):
    item: str = Field(min_length=1, max_length=120)
    done: bool = False


class TaskCreate(BaseModel):
    kind: TaskKind = "other"
    title: str = Field(min_length=1, max_length=160)
    due_date: date
    due_time: time | None = None
    notes: str | None = Field(default=None, max_length=1000)
    child_name: str | None = Field(default=None, max_length=60)
    assignee_id: UUID | None = None
    event_id: UUID | None = None
    camp_id: UUID | None = None
    checklist: list[ChecklistItem] = Field(default_factory=list, max_length=60)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    due_date: date | None = None
    due_time: time | None = None
    notes: str | None = Field(default=None, max_length=1000)
    status: TaskStatus | None = None
    checklist: list[ChecklistItem] | None = Field(default=None, max_length=60)


class AssignRequest(BaseModel):
    task_ids: list[UUID] = Field(min_length=1, max_length=200)
    member_id: UUID | None = Field(description="Null to unassign.")


class GenerateRequest(BaseModel):
    event_ids: list[UUID] | None = Field(default=None, description="Calendar events to cover; all camp events if omitted.")
    dropoff_time: time | None = None
    pickup_time: time | None = None
    weekdays: list[int] = Field(default=[0, 1, 2, 3, 4], description="0 = Monday.")
    include_rides: bool = True
    include_packing: bool = True
    packing_items: list[str] | None = Field(default=None, max_length=40, description="Overrides the default packing list.")


class Task(BaseModel):
    id: UUID
    kind: TaskKind
    title: str
    due_date: date
    due_time: time | None = None
    status: TaskStatus
    notes: str | None = None
    child_name: str | None = None
    assignee_id: UUID | None = None
    assignee_name: str | None = None
    event_id: UUID | None = None
    camp_id: UUID | None = None
    checklist: list[ChecklistItem] = []
    completed_at: datetime | None = None
    completed_by_name: str | None = None


class AuditEntry(BaseModel):
    actor_name: str
    via: str
    action: str
    target_type: str | None = None
    detail: dict
    created_at: datetime


class Household(BaseModel):
    role: Role
    you: Member | None
    members: list[Member]
    can_manage: bool
    my_calendar_url: str | None = None
