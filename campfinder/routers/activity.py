"""
Activity API v1: verified kids' program data for family assistants and partners.

Mounted at /api/activity/v1. Every data endpoint needs an API key; session calendar
files are public so families can add them to their own calendars.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from campfinder.activity.auth import ApiClient, require_api_client
from campfinder.activity.schema import (
    SCHEMA_VERSION, DemandAck, DemandSignal, Program, ProgramList, ProgramResponse, Session,
    SessionList, SessionMatch,
)
from campfinder.activity.sources import (
    find_programs, find_sessions, get_program, get_session_with_program,
)
from campfinder.database import get_supabase
from campfinder.routers.agent import build_ics

PREFIX = "/api/activity/v1"
router = APIRouter(prefix=PREFIX, tags=["Activity API v1"])

NEAR_HELP = "Location as 'City, ST'. Coverage today: CT, MA, ME, NH, NJ, NY, PA, RI, VT."
_PII = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\+?\d[\d\s().-]{7,}\d")


def _api_base(request: Request) -> str:
    return str(request.base_url).rstrip("/") + PREFIX


@router.get("/programs", response_model=ProgramList, summary="Search programs")
async def search_programs(
    request: Request,
    near: str = Query(description=NEAR_HELP),
    radius_miles: float = Query(default=25, ge=1, le=150),
    age: int | None = Query(default=None, ge=2, le=19),
    kind: Literal["camp", "class", "lesson", "league", "after_school", "event"] | None = None,
    format: Literal["day", "overnight", "specialty"] | None = None,
    category: list[str] | None = Query(default=None, description="Repeatable, e.g. category=STEM&category=arts"),
    max_price_per_week: float | None = Query(default=None, ge=0),
    extended_care: bool = False,
    transportation: bool = False,
    meals: bool = False,
    financial_aid: bool = False,
    accredited: bool = False,
    include_sessions: bool = False,
    sort: Literal["best_match", "distance", "price"] = "best_match",
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    _client: ApiClient = Depends(require_api_client),
) -> ProgramList:
    """Programs near a location that fit a child, ranked, with reasons for each match."""
    programs, total = await find_programs(
        near=near, api_base=_api_base(request), radius_miles=radius_miles, age=age, kind=kind,
        format=format, categories=category, max_price_per_week=max_price_per_week,
        needs_extended_care=extended_care, needs_transportation=transportation, needs_meals=meals,
        needs_financial_aid=financial_aid, accredited_only=accredited, sort=sort, limit=limit,
        offset=offset, include_sessions=include_sessions,
    )
    next_offset = offset + limit if offset + limit < total else None
    return ProgramList(data=programs, total=total, next_offset=next_offset)


@router.get("/programs/{program_id}", response_model=ProgramResponse, summary="Get a program")
async def program_detail(
    request: Request, program_id: UUID, _client: ApiClient = Depends(require_api_client),
) -> ProgramResponse:
    """One program with every session, its policies, and field-level verification."""
    program = get_program(str(program_id), _api_base(request))
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return ProgramResponse(data=program)


@router.get("/programs/{program_id}/sessions", response_model=list[Session], summary="List a program's sessions")
async def program_sessions(
    request: Request, program_id: UUID, _client: ApiClient = Depends(require_api_client),
) -> list[Session]:
    program = get_program(str(program_id), _api_base(request))
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return program.sessions or []


@router.get("/sessions", response_model=SessionList, summary="Find sessions in a date window")
async def search_sessions(
    request: Request,
    near: str = Query(description=NEAR_HELP),
    radius_miles: float = Query(default=25, ge=1, le=150),
    age: int | None = Query(default=None, ge=2, le=19),
    category: list[str] | None = Query(default=None),
    max_price_per_week: float | None = Query(default=None, ge=0),
    starts_on_or_after: date | None = None,
    ends_on_or_before: date | None = None,
    open_only: bool = True,
    limit: int = Query(default=30, ge=1, le=100),
    _client: ApiClient = Depends(require_api_client),
) -> SessionList:
    """Dated sessions that fit a child and a window, e.g. 'the week of July 6 for an 8-year-old'."""
    if starts_on_or_after and ends_on_or_before and ends_on_or_before < starts_on_or_after:
        raise HTTPException(status_code=422, detail="ends_on_or_before is before starts_on_or_after")
    matches = await find_sessions(
        near=near, api_base=_api_base(request), radius_miles=radius_miles, age=age, categories=category,
        max_price_per_week=max_price_per_week, starts_on_or_after=starts_on_or_after,
        ends_on_or_before=ends_on_or_before, open_only=open_only, limit=limit,
    )
    return SessionList(data=[SessionMatch(session=s, program=p) for s, p in matches], total=len(matches))


@router.get("/sessions/{session_id}.ics", summary="Calendar file for one session (no key needed)")
async def session_calendar(session_id: UUID) -> Response:
    found = get_session_with_program(str(session_id))
    if found is None:
        raise HTTPException(status_code=404, detail="Session not found")
    session, camp = found
    event = {
        "id": session["id"],
        "title": f"{camp['name']}{' – ' + session['name'] if session.get('name') else ''}",
        "start_date": session["start_date"],
        "end_date": session["end_date"],
        "notes": f"{camp['city']}, {camp['state']}" + (f"\nRegister: {camp['registration_url']}" if camp.get("registration_url") else ""),
    }
    return Response(
        content=build_ics([event]),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="session-{session_id}.ics"'},
    )


@router.post("/demand", response_model=DemandAck, status_code=202, summary="Report what a family asked for")
async def report_demand(signal: DemandSignal, client: ApiClient = Depends(require_api_client)) -> DemandAck:
    """
    Tell us what a family looked for, especially when nothing fit. Anonymous by design:
    no names, contact details or free text. Aggregated demand is shared back with
    partners and providers so the supply of programs grows where families need it.
    """
    for need in signal.needs + signal.categories + [signal.location]:
        if _PII.search(need):
            raise HTTPException(status_code=422, detail="Demand signals must not contain contact details")
    get_supabase().table("activity_demand").insert({
        "client_id": client.id, **signal.model_dump(mode="json"),
    }).execute()
    return DemandAck()


@router.get("/schema", summary="JSON Schema for programs and sessions")
async def json_schema() -> dict:
    """The Family Activity schema, for partners building against it. No key needed."""
    return {
        "schema_version": SCHEMA_VERSION,
        "program": Program.model_json_schema(),
        "session": Session.model_json_schema(),
        "demand_signal": DemandSignal.model_json_schema(),
    }
