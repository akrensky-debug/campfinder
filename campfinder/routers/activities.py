"""Site endpoints for year-round activities: an activity's public page and a family's week."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from campfinder.activity.family_week import build_week
from campfinder.activity.programs import load_field_sources
from campfinder.activity.schema import Program
from campfinder.activity.sources import get_program
from campfinder.agent.tools import list_family_events
from campfinder.auth import authorize_family, optional_user
from campfinder.database import get_supabase

router = APIRouter()


@router.get("/activities/{program_id}", response_model=Program, summary="One class, lesson or league")
async def activity_detail(program_id: UUID) -> Program:
    """Public record for a year-round program, with every offering, price and enrollment window."""
    program = get_program(str(program_id), api_base="/api/activity/v1")
    if program is None or program.kind == "camp":
        raise HTTPException(status_code=404, detail="Activity not found")
    return program


@router.get("/activities/{program_id}/sources", summary="Where each fact came from")
async def activity_sources(program_id: UUID) -> list[dict[str, Any]]:
    rows = load_field_sources(get_supabase(), [str(program_id)]).get(str(program_id), [])
    keys = ("field_name", "offering_id", "source_type", "source_url", "retrieved_on", "notes")
    return [{k: r.get(k) for k in keys} for r in sorted(rows, key=lambda r: (r.get("offering_id") or "", r["field_name"]))]


@router.get("/families/{family_id}/week", summary="The family's week at a glance")
async def family_week(
    family_id: UUID, week_of: date | None = None, user_id: str | None = Depends(optional_user),
) -> dict[str, Any]:
    """Every kid's classes, practices, camps, pickups and reminders, Monday to Sunday."""
    authorize_family(family_id, user_id)
    return build_week(list_family_events(str(family_id)), week_of)
