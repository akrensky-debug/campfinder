"""GET /api/v1/camps/{camp_id} — Full camp detail with trust summary."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from campfinder.models.camp import CampDetail
from campfinder.services.camps import get_camp_detail

router = APIRouter()


@router.get("/camps/{camp_id}", response_model=CampDetail, summary="Get camp detail")
async def get_camp(camp_id: UUID) -> CampDetail:
    """Return the full camp record with sessions and trust summary."""
    return get_camp_detail(camp_id)
