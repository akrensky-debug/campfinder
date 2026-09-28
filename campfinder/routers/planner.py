"""POST /api/v1/plan: week-by-week summer plan from chosen sessions."""

from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from campfinder.database import get_conn
from campfinder.models.plan import PlanRequest, PlanResponse, PlanWeek, PlanWeekCamp
from campfinder.repositories import camps as repo
from campfinder.services.planning import build_plan

router = APIRouter()


@router.post("/plan", response_model=PlanResponse, summary="Build summer plan")
async def build_summer_plan(req: PlanRequest, conn: asyncpg.Connection = Depends(get_conn)) -> PlanResponse:
    """Coverage for each week of the summer, plus gaps, overlaps and total cost."""
    if req.summer_end < req.summer_start:
        raise HTTPException(status_code=422, detail="summer_end must be after summer_start")
    session_ids = list(dict.fromkeys(s.session_id for s in req.camp_sessions))
    rows = await repo.get_sessions(conn, session_ids)
    found = {r["id"] for r in rows}
    missing = [str(s) for s in session_ids if s not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"Sessions not found: {missing}")

    camps = await repo.get_camps(conn, list({r["camp_id"] for r in rows}))
    names = {c["id"]: c["name"] for c in camps}
    session_dicts: list[dict[str, Any]] = [{**r, "camp_name": names.get(r["camp_id"], "Unknown camp")} for r in rows]

    plan = build_plan(session_dicts, req.summer_start, req.summer_end)
    return PlanResponse(
        weeks=[PlanWeek(week_of=w["week_of"], week_end=w["week_end"], status=w["status"],
                        camps=[PlanWeekCamp(**c) for c in w["camps"]]) for w in plan["weeks"]],
        total_estimated_cost=plan["total_estimated_cost"],
        weeks_covered=plan["weeks_covered"], weeks_total=plan["weeks_total"],
        gaps=plan["gaps"], overlaps=plan["overlaps"],
    )
