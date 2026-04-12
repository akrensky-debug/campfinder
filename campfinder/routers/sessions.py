"""GET /api/v1/camps/{camp_id}/sessions — Sessions for a camp."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from campfinder.database import get_supabase
from campfinder.models.session import SessionResponse

router = APIRouter()


@router.get(
    "/camps/{camp_id}/sessions",
    response_model=list[SessionResponse],
    summary="Get camp sessions",
)
async def get_sessions(
    camp_id: UUID,
    after: date | None = Query(default=None, description="Only sessions starting after this date"),
    before: date | None = Query(default=None, description="Only sessions starting before this date"),
) -> list[SessionResponse]:
    """Return all sessions for a camp, optionally filtered by date range."""
    client = get_supabase()
    cid = str(camp_id)

    # Verify camp exists
    camp_rows = client.table("camps").select("id").eq("id", cid).execute().data
    if not camp_rows:
        raise HTTPException(status_code=404, detail="Camp not found")

    query = client.table("sessions").select("*").eq("camp_id", cid).order("start_date")
    if after is not None:
        query = query.gt("start_date", after.isoformat())
    if before is not None:
        query = query.lt("start_date", before.isoformat())

    rows = query.execute().data or []

    return [
        SessionResponse(
            id=r["id"],
            camp_id=r["camp_id"],
            name=r.get("name"),
            start_date=r["start_date"],
            end_date=r["end_date"],
            length_days=r.get("length_days"),
            length_weeks=float(r["length_weeks"]) if r.get("length_weeks") else None,
            price=float(r["price"]) if r.get("price") else None,
            full_season=r.get("full_season") or False,
            availability=r.get("availability", "unknown"),
            created_at=r.get("created_at"),
            updated_at=r.get("updated_at"),
        )
        for r in rows
    ]
