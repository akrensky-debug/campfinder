"""Family agent endpoints: create a family, chat with the agent, subscribe to the calendar."""

from __future__ import annotations

import json
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any, AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from campfinder.activity import ics as ics_extended
from campfinder.agent.runner import run_agent
from campfinder.agent.tools import list_family_events
from campfinder.household.context import acting_as
from campfinder.household.service import actor_for
from campfinder.auth import ALL_ROLES, FamilyAccess, active_membership, authorize_family, family_access, optional_user, required_user
from campfinder.kit.service import delete_family_data
from campfinder.database import get_supabase

router = APIRouter()


class FamilyResponse(BaseModel):
    id: UUID
    profile: dict[str, Any]
    events: list[dict[str, Any]] = []
    calendar_url: str | None = None
    signed_in: bool = Field(default=False, description="True when the family belongs to an account.")
    role: str = Field(default="owner", description="The caller's role: owner, co_parent, caregiver or viewer.")
    my_calendar_url: str | None = Field(default=None, description="The caller's own feed: the plan plus their jobs.")
    can_open_kit: bool = Field(default=False, description="Owner, or a co-parent the owner gave the info kit to.")


class ChatRequest(BaseModel):
    family_id: UUID
    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=4000)


def _calendar_url(request: Request, family: dict[str, Any]) -> str | None:
    token = family.get("calendar_token")
    return f"{str(request.base_url).rstrip('/')}/api/v1/calendar/{token}.ics" if token else None


def _scoped_profile(profile: dict[str, Any], role: str) -> dict[str, Any]:
    """Least data per role: caregivers see the kids' first names, viewers nothing."""
    if role in ("owner", "co_parent"):
        return profile
    if role == "caregiver":
        return {"kids": [{"name": k.get("name")} for k in profile.get("kids") or [] if k.get("name")]}
    return {}


def _family_response(request: Request, family: dict[str, Any], access: FamilyAccess | None = None) -> FamilyResponse:
    from campfinder.routers.household import member_calendar_url

    role = access.role if access else "owner"
    member = access.member if access else None
    return FamilyResponse(
        id=family["id"],
        profile=_scoped_profile(family.get("profile") or {}, role),
        events=list_family_events(family["id"]),
        calendar_url=_calendar_url(request, family) if role in ("owner", "co_parent") else None,
        signed_in=family.get("owner_user_id") is not None,
        role=role,
        my_calendar_url=member_calendar_url(request, member),
        can_open_kit=access.kit_allowed if access else family.get("owner_user_id") is not None,
    )


@router.post("/families", response_model=FamilyResponse, summary="Create a guest family")
async def create_family(request: Request) -> FamilyResponse:
    row = get_supabase().table("families").insert({}).execute().data[0]
    return _family_response(request, row)


@router.get("/families/{family_id}", response_model=FamilyResponse, summary="Get a family")
async def get_family(request: Request, family_id: UUID, user_id: str | None = Depends(optional_user)) -> FamilyResponse:
    access = family_access(family_id, user_id, roles=ALL_ROLES)
    return _family_response(request, access.family, access)


@router.get("/me/family", response_model=FamilyResponse, summary="The signed-in parent's family")
async def my_family(request: Request, user_id: str = Depends(required_user), family_id: UUID | None = None) -> FamilyResponse:
    """The family this account owns or belongs to. `family_id` picks one when there are several
    (e.g. your own family and your sister's, where you are a caregiver)."""
    if family_id is not None:
        try:
            access = family_access(family_id, user_id, roles=ALL_ROLES, require_account=True)
            return _family_response(request, access.family, access)
        except HTTPException:
            pass
    rows = get_supabase().table("families").select("*").eq("owner_user_id", user_id).execute().data
    if rows:
        return _family_response(request, rows[0], FamilyAccess(rows[0], "owner", active_membership(rows[0]["id"], user_id)))
    memberships = get_supabase().table("family_members").select("family_id").eq("user_id", user_id).eq("status", "active").execute().data
    if memberships:
        access = family_access(memberships[0]["family_id"], user_id, roles=ALL_ROLES, require_account=True)
        return _family_response(request, access.family, access)
    raise HTTPException(status_code=404, detail="No family saved to this account yet")


@router.post("/families/{family_id}/claim", response_model=FamilyResponse, summary="Save a guest family to your account")
async def claim_family(request: Request, family_id: UUID, user_id: str = Depends(required_user)) -> FamilyResponse:
    """Attach a guest family to the signed-in account. If the account already has a
    family, that one is returned and the guest family is left as it was."""
    sb = get_supabase()
    existing = sb.table("families").select("*").eq("owner_user_id", user_id).execute().data
    if existing:
        return _family_response(request, existing[0])
    if sb.table("family_members").select("id").eq("user_id", user_id).eq("status", "active").execute().data:
        return await my_family(request, user_id)  # already in someone's family: don't claim a stray guest one
    family = authorize_family(family_id, user_id)
    if family.get("owner_user_id") is None:
        sb.table("families").update({"owner_user_id": user_id}).eq("id", str(family_id)).execute()
        family["owner_user_id"] = user_id
    return _family_response(request, family)


@router.post("/families/{family_id}/calendar/reset", response_model=FamilyResponse, summary="Reset the calendar link")
async def reset_calendar_link(request: Request, family_id: UUID, user_id: str | None = Depends(optional_user)) -> FamilyResponse:
    """Issue a new private calendar link; the old one stops working at once."""
    family = authorize_family(family_id, user_id)
    token = secrets.token_hex(16)
    get_supabase().table("families").update({"calendar_token": token}).eq("id", str(family_id)).execute()
    family["calendar_token"] = token
    return _family_response(request, family)


@router.delete("/families/{family_id}", status_code=204, summary="Delete everything about this family")
async def delete_family(family_id: UUID, user_id: str | None = Depends(optional_user)) -> Response:
    authorize_family(family_id, user_id, roles=("owner",))
    delete_family_data(str(family_id))
    return Response(status_code=204)


@router.post("/agent/chat", summary="Chat with the family agent (server-sent events)")
async def chat(req: ChatRequest, user_id: str | None = Depends(optional_user)) -> StreamingResponse:
    access = family_access(req.family_id, user_id)  # owner and co-parents
    actor_for(access)  # make sure the speaker has a member row, so the conversation is theirs

    async def events() -> AsyncIterator[str]:
        acting_as(access)
        async for event in run_agent(
            str(req.family_id),
            str(req.conversation_id) if req.conversation_id else None,
            req.message,
        ):
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/calendar/{token}.ics", summary="Family calendar feed")
async def family_calendar(token: str) -> Response:
    """Private iCalendar feed for Google, Apple and Outlook Calendar. The link is the key;
    resetting it cuts off anyone holding the old one."""
    if len(token) < 32:
        raise HTTPException(status_code=404, detail="Calendar not found")
    rows = get_supabase().table("families").select("id").eq("calendar_token", token).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Calendar not found")
    return Response(
        content=build_ics(list_family_events(rows[0]["id"])),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="campfinder.ics"', "Cache-Control": "private, no-store"},
    )


def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_fold(line: str) -> str:
    """Fold lines longer than 75 octets, per RFC 5545."""
    out, current = [], b""
    for ch in line:
        enc = ch.encode()
        if len(current) + len(enc) > (75 if not out else 74):
            out.append(current.decode())
            current = b""
        current += enc
    out.append(current.decode())
    return "\r\n ".join(out)


def build_ics(events: list[dict[str, Any]]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CampFinder//Family Calendar//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Family plans (CampFinder)",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
    ]
    lines += ics_extended.vtimezone_lines(events)
    for e in events:
        if ics_extended.needs_extended_ics(e):  # recurring/timed classes and reminders
            lines += ics_extended.vevent_lines(e, stamp)
            continue
        start = date.fromisoformat(str(e["start_date"]))
        end = date.fromisoformat(str(e["end_date"])) + timedelta(days=1)  # DTEND is exclusive
        lines += [
            "BEGIN:VEVENT",
            f"UID:{e['id']}@campfinder",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
            f"DTEND;VALUE=DATE:{end:%Y%m%d}",
            f"SUMMARY:{_ics_escape(e['title'])}",
        ]
        if e.get("notes"):
            lines.append(f"DESCRIPTION:{_ics_escape(e['notes'])}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_ics_fold(line) for line in lines) + "\r\n"
