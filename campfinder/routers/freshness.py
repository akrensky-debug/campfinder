"""GET /api/v1/camps/{camp_id}/freshness — Freshness and verification status."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from campfinder.database import get_supabase
from campfinder.services.freshness import (
    compute_days_since_update,
    compute_freshness_grade,
    find_stale_fields,
)

router = APIRouter()


class FreshnessResponse(BaseModel):
    camp_id: UUID
    name: str
    verification_status: str
    last_updated: str | None
    days_since_update: int | None
    stale_fields: list[str]
    freshness_grade: str


@router.get(
    "/camps/{camp_id}/freshness",
    response_model=FreshnessResponse,
    summary="Get camp freshness",
)
async def get_freshness(camp_id: UUID) -> FreshnessResponse:
    """
    Return freshness grade and stale-field list for a camp.
    Grades: current (≤30 days), aging (31–90 days), stale (>90 days).
    """
    client = get_supabase()
    cid = str(camp_id)

    rows = client.table("camps").select("*").eq("id", cid).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Camp not found")
    camp = rows[0]

    field_sources = client.table("field_sources").select("field_name,source_type,last_verified").eq("camp_id", cid).execute().data or []
    has_sessions = bool(client.table("sessions").select("id").eq("camp_id", cid).limit(1).execute().data)

    last_updated_str = camp.get("last_updated_date") or camp.get("updated_at")

    # Parse to datetime for grade computation
    from datetime import datetime, timezone
    last_updated = None
    if last_updated_str:
        try:
            last_updated = datetime.fromisoformat(str(last_updated_str).replace("Z", "+00:00"))
        except ValueError:
            pass

    grade = compute_freshness_grade(last_updated)
    days = compute_days_since_update(last_updated)
    stale = find_stale_fields(camp, field_sources, has_sessions)

    return FreshnessResponse(
        camp_id=camp["id"],
        name=camp["name"],
        verification_status=camp["verification_status"],
        last_updated=str(last_updated_str) if last_updated_str else None,
        days_since_update=days,
        stale_fields=stale,
        freshness_grade=grade,
    )
