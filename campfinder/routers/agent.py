"""Family agent endpoints: create a family, chat with the agent, subscribe to the calendar."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, AsyncIterator
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from campfinder.agent.runner import run_agent
from campfinder.agent.tools import list_family_events
from campfinder.database import get_supabase

router = APIRouter()


class FamilyResponse(BaseModel):
    id: UUID
    profile: dict[str, Any]
    events: list[dict[str, Any]] = []


class ChatRequest(BaseModel):
    family_id: UUID
    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=4000)


def _get_family(family_id: UUID) -> dict[str, Any]:
    rows = get_supabase().table("families").select("*").eq("id", str(family_id)).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Family not found")
    return rows[0]


@router.post("/families", response_model=FamilyResponse, summary="Create a family")
async def create_family() -> FamilyResponse:
    row = get_supabase().table("families").insert({}).execute().data[0]
    return FamilyResponse(id=row["id"], profile=row["profile"] or {})


@router.get("/families/{family_id}", response_model=FamilyResponse, summary="Get a family")
async def get_family(family_id: UUID) -> FamilyResponse:
    row = _get_family(family_id)
    return FamilyResponse(id=row["id"], profile=row["profile"] or {}, events=list_family_events(row["id"]))


@router.post("/agent/chat", summary="Chat with the family agent (server-sent events)")
async def chat(req: ChatRequest) -> StreamingResponse:
    _get_family(req.family_id)

    async def events() -> AsyncIterator[str]:
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


@router.get("/families/{family_id}/calendar.ics", summary="Family calendar feed")
async def family_calendar(family_id: UUID) -> Response:
    """iCalendar feed that Google, Apple and Outlook Calendar can subscribe to."""
    _get_family(family_id)
    return Response(
        content=build_ics(list_family_events(str(family_id))),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="campfinder.ics"'},
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
    for e in events:
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
