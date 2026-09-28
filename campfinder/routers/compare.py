"""POST /api/v1/compare: side-by-side comparison of 2 to 5 camps."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from campfinder.database import get_conn
from campfinder.repositories import camps as repo
from campfinder.services.differences import generate_differences
from campfinder.services.geo import geocode_location, haversine_miles

router = APIRouter()


class CompareRequest(BaseModel):
    camp_ids: list[UUID] = Field(min_length=2, max_length=5)
    reference_location: str | None = Field(default=None, max_length=120)


class SessionRange(BaseModel):
    session_id: UUID
    name: str | None
    start_date: date
    end_date: date
    price: float | None
    availability: str


class CampComparison(BaseModel):
    camp_id: UUID
    slug: str
    name: str
    city: str
    state: str
    camp_type: str
    age_min: int | None
    age_max: int | None
    price_min: float | None
    price_max: float | None
    price_per_week: float | None
    session_count: int
    sessions: list[SessionRange]
    transportation: bool
    extended_care: bool
    meals_included: bool
    aca_accredited: bool | None
    verification_status: str
    refund_policy_summary: str | None
    primary_categories: list[str]
    distance_miles: float | None = None


class CompareResponse(BaseModel):
    camps: list[CampComparison]
    differences: list[str]


def _money(v: Any) -> float | None:
    return float(v) if v is not None else None


@router.post("/compare", response_model=CompareResponse, summary="Compare camps")
async def compare_camps(req: CompareRequest, conn: asyncpg.Connection = Depends(get_conn)) -> CompareResponse:
    ids = list(dict.fromkeys(req.camp_ids))
    rows = await repo.get_camps(conn, ids)
    by_id = {r["id"]: r for r in rows}
    missing = [str(i) for i in ids if i not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Camps not found: {missing}")

    sessions_by_camp = await repo.sessions_for_camps(conn, ids)
    ref = geocode_location(req.reference_location) if req.reference_location else None

    comparisons: list[CampComparison] = []
    diff_input: list[dict[str, Any]] = []
    for cid in ids:
        camp = by_id[cid]
        camp_sessions = sessions_by_camp.get(cid, [])
        distance = round(haversine_miles(ref[0], ref[1], camp["lat"], camp["lng"]), 1) if ref else None
        comparisons.append(CampComparison(
            camp_id=cid, slug=camp["slug"], name=camp["name"], city=camp["city"], state=camp["state"],
            camp_type=camp["camp_type"], age_min=camp.get("age_min"), age_max=camp.get("age_max"),
            price_min=_money(camp.get("price_min")), price_max=_money(camp.get("price_max")),
            price_per_week=_money(camp.get("price_per_week")),
            session_count=len(camp_sessions),
            sessions=[SessionRange(session_id=s["id"], name=s.get("name"), start_date=s["start_date"],
                                   end_date=s["end_date"], price=_money(s.get("price")),
                                   availability=s["availability"]) for s in camp_sessions],
            transportation=camp["transportation"], extended_care=camp["extended_care"],
            meals_included=camp["meals_included"], aca_accredited=camp.get("aca_accredited"),
            verification_status=camp["verification_status"],
            refund_policy_summary=camp.get("refund_policy_summary"),
            primary_categories=list(camp.get("primary_categories") or []),
            distance_miles=distance,
        ))
        diff_input.append({**camp, "sessions": camp_sessions, "distance_miles": distance})

    return CompareResponse(camps=comparisons, differences=generate_differences(diff_input))
