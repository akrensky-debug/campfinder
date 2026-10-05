"""GET /api/v1/camps/{camp id or slug} — Full camp detail with trust summary."""

from __future__ import annotations

from fastapi import APIRouter

from campfinder.models.camp import CampDetail
from campfinder.services.camps import get_camp_detail

router = APIRouter()


@router.get("/camps/{camp_ref}", response_model=CampDetail, summary="Get camp detail")
async def get_camp(camp_ref: str) -> CampDetail:
    """Return the full camp record with sessions and trust summary. camp_ref is the camp's id or slug."""
    return get_camp_detail(camp_ref)
