"""Household members, invites, tasks, reminders and per-member calendar feeds."""

from __future__ import annotations

import hmac
import os
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

from campfinder.agent.tools import list_family_events
from campfinder.auth import ALL_ROLES, FULL_PLAN, family_access, optional_user, required_user
from campfinder.config import get_settings
from campfinder.database import get_supabase
from campfinder.household import service
from campfinder.mailer import Email, get_mailer
from campfinder.household.models import (
    AssignRequest, AuditEntry, GenerateRequest, Household, InviteCreate, InviteCreated, InvitePreview, Member,
    MemberUpdate, MyPrefs, Task, TaskCreate, TaskUpdate,
)
from campfinder.household.reminders import run_reminders

router = APIRouter()


def _actor(family_id: UUID, user_id: str | None, *, roles: tuple[str, ...] = FULL_PLAN,
           require_account: bool = False) -> service.Actor:
    return service.actor_for(family_access(family_id, user_id, roles=roles, require_account=require_account))


def member_calendar_url(request: Request, member: dict[str, Any] | None) -> str | None:
    if not member or not member.get("calendar_token"):
        return None
    return f"{str(request.base_url).rstrip('/')}/api/v1/calendar/member/{member['calendar_token']}.ics"


def _tasks(actor: service.Actor, rows: list[dict[str, Any]]) -> list[Task]:
    names = service.member_names(actor.family_id)
    return [service.to_task(r, names) for r in rows]


# ---------------------------------------------------------------------------
# Household
# ---------------------------------------------------------------------------

@router.get("/families/{family_id}/household", response_model=Household, summary="Members and your role")
async def get_household(request: Request, family_id: UUID, user_id: str | None = Depends(optional_user)) -> Household:
    access = family_access(family_id, user_id, roles=ALL_ROLES)
    actor = service.actor_for(access)
    if actor.member_id is None:  # guest family: nobody to share with until it's saved to an account
        return Household(role="owner", you=None, members=[], can_manage=False)
    you = service.get_member_row(actor.family_id, actor.member_id)
    return Household(
        role=actor.role, you=service.member_view(you, actor), members=service.visible_members(actor),
        can_manage=actor.role == "owner", my_calendar_url=member_calendar_url(request, you),
    )


@router.post("/families/{family_id}/members/invite", response_model=InviteCreated, status_code=201, summary="Invite someone")
async def invite_member(family_id: UUID, req: InviteCreate, user_id: str = Depends(required_user)) -> InviteCreated:
    actor = _actor(family_id, user_id, roles=("owner",), require_account=True)
    row, token = service.create_invite(actor, req)
    url = f"{get_settings().frontend_url.rstrip('/')}/join/{token}"
    emailed = False
    if req.send_email:
        subject, html, text = service.invite_email(actor.name, row, url)
        emailed = await get_mailer().send(Email(to=row["email"], subject=subject, html=html, text=text))
    return InviteCreated(member=service.member_view(row, actor), url=url, emailed=emailed)


@router.patch("/families/{family_id}/members/{member_id}", response_model=Member, summary="Change a member's role or access")
async def update_member(family_id: UUID, member_id: UUID, req: MemberUpdate, user_id: str = Depends(required_user)) -> Member:
    actor = _actor(family_id, user_id, roles=("owner",), require_account=True)
    return service.member_view(service.update_member(actor, str(member_id), req), actor)


@router.delete("/families/{family_id}/members/{member_id}", status_code=204, summary="Remove someone from the household")
async def remove_member(family_id: UUID, member_id: UUID, user_id: str = Depends(required_user)) -> Response:
    service.remove_member(_actor(family_id, user_id, roles=("owner",), require_account=True), str(member_id))
    return Response(status_code=204)


@router.post("/families/{family_id}/leave", status_code=204, summary="Leave a family you were invited to")
async def leave(family_id: UUID, user_id: str = Depends(required_user)) -> Response:
    service.leave_family(_actor(family_id, user_id, roles=ALL_ROLES, require_account=True))
    return Response(status_code=204)


@router.patch("/families/{family_id}/me", response_model=Member, summary="Your reminder settings")
async def update_prefs(family_id: UUID, req: MyPrefs, user_id: str = Depends(required_user)) -> Member:
    actor = _actor(family_id, user_id, roles=ALL_ROLES, require_account=True)
    return service.member_view(service.update_my_prefs(actor, req), actor)


@router.post("/families/{family_id}/me/calendar/reset", response_model=Household, summary="New link for your own calendar")
async def reset_my_calendar(request: Request, family_id: UUID, user_id: str = Depends(required_user)) -> Household:
    actor = _actor(family_id, user_id, roles=ALL_ROLES, require_account=True)
    service.reset_member_calendar(actor)
    return await get_household(request, family_id, user_id)


class MyFamily(BaseModel):
    family_id: UUID
    role: str
    display_name: str | None = None


@router.get("/me/families", response_model=list[MyFamily], summary="Families you own or belong to")
async def my_families(user_id: str = Depends(required_user)) -> list[MyFamily]:
    sb = get_supabase()
    owned = sb.table("families").select("id").eq("owner_user_id", user_id).execute().data or []
    member = sb.table("family_members").select("family_id, role, display_name").eq("user_id", user_id) \
        .eq("status", "active").execute().data or []
    out = [MyFamily(family_id=f["id"], role="owner") for f in owned]
    seen = {str(f.family_id) for f in out}
    out += [MyFamily(family_id=m["family_id"], role=m["role"], display_name=m["display_name"])
            for m in member if str(m["family_id"]) not in seen]
    return out


# ---------------------------------------------------------------------------
# Invites (recipient side)
# ---------------------------------------------------------------------------

@router.get("/invites/{token}", response_model=InvitePreview, summary="What an invite is for")
async def preview_invite(token: str) -> InvitePreview:
    return service.preview_invite(token)


class Accepted(BaseModel):
    family_id: UUID
    role: str


@router.post("/invites/{token}/accept", response_model=Accepted, summary="Accept an invite")
async def accept_invite(token: str, user_id: str = Depends(required_user)) -> Accepted:
    row = service.accept_invite(token, user_id)
    return Accepted(family_id=row["family_id"], role=row["role"])


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@router.get("/families/{family_id}/tasks", response_model=list[Task], summary="Tasks you can see")
async def list_tasks(
    family_id: UUID, user_id: str | None = Depends(optional_user),
    start: date | None = None, end: date | None = None, status: str | None = None,
    assignee_id: UUID | None = None,
) -> list[Task]:
    actor = _actor(family_id, user_id, roles=ALL_ROLES)
    return service.visible_tasks(actor, start=start, end=end, status=status,
                                 assignee_id=str(assignee_id) if assignee_id else None)


@router.post("/families/{family_id}/tasks", response_model=list[Task], status_code=201, summary="Add tasks")
async def create_tasks(family_id: UUID, tasks: list[TaskCreate], user_id: str | None = Depends(optional_user)) -> list[Task]:
    actor = _actor(family_id, user_id)
    return _tasks(actor, service.create_tasks(actor, tasks[:200]))


@router.patch("/families/{family_id}/tasks/{task_id}", response_model=Task, summary="Update or complete a task")
async def update_task(family_id: UUID, task_id: UUID, req: TaskUpdate, user_id: str | None = Depends(optional_user)) -> Task:
    actor = _actor(family_id, user_id, roles=("co_parent", "caregiver"))
    return _tasks(actor, [service.update_task(actor, str(task_id), req)])[0]


@router.delete("/families/{family_id}/tasks/{task_id}", status_code=204, summary="Delete a task")
async def delete_task(family_id: UUID, task_id: UUID, user_id: str | None = Depends(optional_user)) -> Response:
    if not service.delete_tasks(_actor(family_id, user_id), [task_id]):
        raise HTTPException(status_code=404, detail="Task not found")
    return Response(status_code=204)


@router.post("/families/{family_id}/tasks/assign", response_model=list[Task], summary="Assign or unassign tasks")
async def assign_tasks(family_id: UUID, req: AssignRequest, user_id: str | None = Depends(optional_user)) -> list[Task]:
    actor = _actor(family_id, user_id)
    return _tasks(actor, service.assign_tasks(actor, req.task_ids, req.member_id))


@router.post("/families/{family_id}/tasks/generate", response_model=list[Task], summary="Rides and packing lists from the calendar")
async def generate_tasks(family_id: UUID, req: GenerateRequest, user_id: str | None = Depends(optional_user)) -> list[Task]:
    actor = _actor(family_id, user_id)
    return _tasks(actor, service.generate_plan_tasks(actor, req))


@router.get("/families/{family_id}/audit", response_model=list[AuditEntry], summary="Who changed what")
async def audit_log(family_id: UUID, user_id: str | None = Depends(optional_user), limit: int = Query(100, le=500)) -> list[AuditEntry]:
    family_access(family_id, user_id)  # owner and co-parents
    return service.list_audit(str(family_id), limit)


# ---------------------------------------------------------------------------
# Feeds and the reminder job
# ---------------------------------------------------------------------------

@router.get("/calendar/member/{token}.ics", summary="One person's calendar: the family plan plus their own jobs")
async def member_calendar(token: str) -> Response:
    member = service.member_by_calendar_token(token) if len(token) >= 32 else None
    if not member or member["status"] != "active":
        raise HTTPException(status_code=404, detail="Calendar not found")
    tasks = [] if member["role"] == "viewer" else service.task_rows(member["family_id"], assignee_id=str(member["id"]))
    return Response(
        content=service.build_member_ics(member, list_family_events(member["family_id"]), tasks),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="campfinder-mine.ics"', "Cache-Control": "private, no-store"},
    )


@router.post("/internal/reminders/run", summary="Send due reminders (cron)", include_in_schema=False)
async def run_reminder_job(
    x_cron_secret: str | None = Header(default=None), dry_run: bool = False, weekly: bool | None = None,
    on: date | None = None, slot: str | None = Query(default=None, pattern="^(morning|evening)$"),
) -> dict[str, Any]:
    secret = os.environ.get("REMINDER_CRON_SECRET", "")
    if not secret or not x_cron_secret or not hmac.compare_digest(secret, x_cron_secret):
        raise HTTPException(status_code=404, detail="Not found")
    out = await run_reminders(on, weekly=weekly, dry_run=dry_run, slot=slot)
    return {
        "dry_run": dry_run,
        "count": len(out),
        "emails": [{"kind": o.kind, "member_id": str(o.member_id), "subject": o.email.subject,
                    **({"text": o.email.text} if dry_run else {})} for o in out],
    }
