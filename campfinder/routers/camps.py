"""Camp detail, sessions and freshness."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from campfinder.config import Settings, get_settings
from campfinder.database import get_conn
from campfinder.models.camp import AccreditationSummary, CampDetail, TrustSummary
from campfinder.models.session import SessionResponse
from campfinder.repositories import camps as repo
from campfinder.services.freshness import (
    compute_days_since_update,
    compute_freshness_grade,
    find_stale_fields,
)

router = APIRouter()

TRUST_IMPORTANT_FIELDS = [
    "price_min", "price_per_week", "sessions", "description_short", "transportation",
    "extended_care", "meals_included", "refund_policy_summary", "special_needs_notes",
]


async def _load_camp(conn: asyncpg.Connection, camp_ref: str) -> dict[str, Any]:
    """Accept a UUID or a slug."""
    camp = None
    try:
        camp = await repo.get_camp(conn, UUID(camp_ref))
    except ValueError:
        camp = await repo.get_camp_by_slug(conn, camp_ref)
    if camp is None:
        raise HTTPException(status_code=404, detail="Camp not found")
    return camp


def _build_trust_summary(camp: dict[str, Any], field_sources: list[dict[str, Any]], has_sessions: bool) -> TrustSummary:
    verified = [fs["field_name"] for fs in field_sources
                if fs["source_type"] in ("camp_verified", "team_verified", "camp_submitted")]
    unverified = [fs["field_name"] for fs in field_sources
                  if fs["source_type"] in ("public_web", "parent_reported")]
    missing = []
    for field in TRUST_IMPORTANT_FIELDS:
        if field == "sessions":
            if not has_sessions:
                missing.append(field)
        elif camp.get(field) in (None, "", []):
            missing.append(field)
    return TrustSummary(
        verification_status=camp["verification_status"],
        last_updated=camp.get("updated_at"),
        fields_verified=verified, fields_unverified=unverified, fields_missing=missing,
        accreditation=AccreditationSummary(
            status="confirmed" if camp.get("aca_accredited") else "not_confirmed",
            source=camp.get("aca_source_url"),
        ),
    )


@router.get("/camps/{camp_ref}", response_model=CampDetail, summary="Get camp detail")
async def get_camp(
    camp_ref: str,
    conn: asyncpg.Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings),
) -> CampDetail:
    """Full public record with sessions and trust summary. camp_ref is an id or a slug."""
    camp = await _load_camp(conn, camp_ref)
    sessions = await repo.sessions_for_camp(conn, camp["id"])
    field_sources = await repo.field_sources_for_camp(conn, camp["id"])
    trust = _build_trust_summary(camp, field_sources, bool(sessions))
    return CampDetail.from_row(camp, sessions=sessions, trust=trust, site_url=settings.site_url)


@router.get("/camps/{camp_ref}/sessions", response_model=list[SessionResponse], summary="Get camp sessions")
async def get_sessions(
    camp_ref: str,
    after: date | None = Query(default=None),
    before: date | None = Query(default=None),
    conn: asyncpg.Connection = Depends(get_conn),
) -> list[SessionResponse]:
    camp = await _load_camp(conn, camp_ref)
    rows = await repo.sessions_for_camp(conn, camp["id"], after=after, before=before)
    return [SessionResponse.from_row(r) for r in rows]


class FreshnessResponse(BaseModel):
    camp_id: UUID
    name: str
    verification_status: str
    last_updated: str | None
    days_since_update: int | None
    stale_fields: list[str]
    freshness_grade: str


@router.get("/camps/{camp_ref}/freshness", response_model=FreshnessResponse, summary="Get camp freshness")
async def get_freshness(camp_ref: str, conn: asyncpg.Connection = Depends(get_conn)) -> FreshnessResponse:
    """current (30 days or less), aging (31 to 90), stale (older or unknown)."""
    camp = await _load_camp(conn, camp_ref)
    field_sources = await repo.field_sources_for_camp(conn, camp["id"])
    has_sessions = bool(await repo.sessions_for_camp(conn, camp["id"]))
    last_updated = camp.get("updated_at")
    return FreshnessResponse(
        camp_id=camp["id"], name=camp["name"], verification_status=camp["verification_status"],
        last_updated=last_updated.isoformat() if last_updated else None,
        days_since_update=compute_days_since_update(last_updated),
        stale_fields=find_stale_fields(camp, field_sources, has_sessions),
        freshness_grade=compute_freshness_grade(last_updated),
    )
