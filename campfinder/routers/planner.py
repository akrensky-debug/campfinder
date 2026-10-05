"""POST /api/v1/plan — Week-by-week summer camp plan builder."""

from __future__ import annotations

from fastapi import APIRouter

from campfinder.models.plan import PlanRequest, PlanResponse
from campfinder.services import plan

router = APIRouter()


@router.post("/plan", response_model=PlanResponse, summary="Build summer plan")
async def build_summer_plan(req: PlanRequest) -> PlanResponse:
    """
    Build a week-by-week summer plan from a list of (camp_id, session_id) pairs.
    Returns coverage status for each week, gaps, overlaps, and total cost.
    """
    return plan.build_summer_plan(req)
