"""POST /api/v1/plan — Week-by-week summer camp plan builder."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException

from campfinder.database import get_supabase
from campfinder.models.plan import PlanRequest, PlanResponse, PlanWeek, PlanWeekCamp
from campfinder.services.planning import build_plan

router = APIRouter()


@router.post("/plan", response_model=PlanResponse, summary="Build summer plan")
async def build_summer_plan(req: PlanRequest) -> PlanResponse:
    """
    Build a week-by-week summer plan from a list of (camp_id, session_id) pairs.
    Returns coverage status for each week, gaps, overlaps, and total cost.
    """
    client = get_supabase()
    session_ids = [str(s.session_id) for s in req.camp_sessions]

    rows = client.table("sessions").select("*").in_("id", session_ids).execute().data or []

    if not rows:
        raise HTTPException(status_code=404, detail="No sessions found for the given IDs")

    found_ids = {r["id"] for r in rows}
    missing = [sid for sid in session_ids if sid not in found_ids]
    if missing:
        raise HTTPException(status_code=404, detail=f"Sessions not found: {missing}")

    # Fetch camp names in one call
    all_camp_ids = list({r["camp_id"] for r in rows})
    camp_rows = client.table("camps").select("id,name").in_("id", all_camp_ids).execute().data or []
    camp_name_map = {c["id"]: c["name"] for c in camp_rows}

    session_dicts: list[dict[str, Any]] = []
    for r in rows:
        session_dicts.append({**r, "camp_name": camp_name_map.get(r["camp_id"], "Unknown Camp")})

    plan = build_plan(session_dicts, req.summer_start, req.summer_end)

    weeks = [
        PlanWeek(
            week_of=w["week_of"],
            week_end=w["week_end"],
            status=w["status"],
            camps=[
                PlanWeekCamp(
                    camp_id=c["camp_id"],
                    name=c["name"],
                    session_id=c["session_id"],
                    session_dates=c["session_dates"],
                    cost=c.get("cost"),
                )
                for c in w["camps"]
            ],
        )
        for w in plan["weeks"]
    ]

    return PlanResponse(
        weeks=weeks,
        total_estimated_cost=plan["total_estimated_cost"],
        weeks_covered=plan["weeks_covered"],
        weeks_total=plan["weeks_total"],
        gaps=plan["gaps"],
        overlaps=plan["overlaps"],
    )
