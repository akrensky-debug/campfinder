"""Family info kit: read and update it, share packages from it, and open a shared package."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from campfinder.auth import authorize_kit, required_user
from campfinder.config import get_settings
from campfinder.kit.models import (
    CHILD_FIELDS, HOUSEHOLD_FIELDS, InfoKit, ShareCreate, ShareCreated, SharedPackage, ShareSummary,
)
from campfinder.kit import service
from campfinder.household.service import actor_for, audit

router = APIRouter()


def _log(access, action: str, detail: dict | None = None) -> None:
    """Kit activity goes in the household audit log (field names only, never values)."""
    audit(actor_for(access), action, "kit", None, detail)


@router.get("/families/{family_id}/kit", response_model=InfoKit, summary="Get the info kit")
async def get_kit(family_id: UUID, user_id: str = Depends(required_user)) -> InfoKit:
    access = authorize_kit(family_id, user_id)
    if not access.is_owner:
        _log(access, "kit_viewed")
    return service.load_kit(str(family_id))


@router.put("/families/{family_id}/kit", response_model=InfoKit, summary="Replace the info kit")
async def put_kit(family_id: UUID, kit: InfoKit, user_id: str = Depends(required_user)) -> InfoKit:
    access = authorize_kit(family_id, user_id)
    service.save_kit(str(family_id), kit)
    _log(access, "kit_saved")
    return kit


@router.get("/kit/fields", summary="Fields that can be shared")
async def kit_fields() -> dict[str, list[str]]:
    return {"household": HOUSEHOLD_FIELDS, "child": CHILD_FIELDS}


@router.get("/families/{family_id}/kit/shares", response_model=list[ShareSummary], summary="List shares")
async def list_shares(family_id: UUID, user_id: str = Depends(required_user)) -> list[ShareSummary]:
    authorize_kit(family_id, user_id)
    return service.list_shares(str(family_id))


@router.post("/families/{family_id}/kit/shares", response_model=ShareCreated, status_code=201, summary="Share a package")
async def create_share(family_id: UUID, req: ShareCreate, user_id: str = Depends(required_user)) -> ShareCreated:
    access = authorize_kit(family_id, user_id)
    share, token = service.create_share(str(family_id), req)
    # Field names and counts only: the audit log is visible to every co-parent.
    _log(access, "kit_shared", {"share_id": str(share.id), "children": len(req.children),
                                "fields": req.household_fields + req.child_fields})
    return ShareCreated(share=share, url=f"{get_settings().frontend_url.rstrip('/')}/share/{token}")


@router.post("/families/{family_id}/kit/shares/{share_id}/revoke", response_model=ShareSummary, summary="Withdraw a share")
async def revoke_share(family_id: UUID, share_id: UUID, user_id: str = Depends(required_user)) -> ShareSummary:
    access = authorize_kit(family_id, user_id)
    share = service.revoke_share(str(family_id), str(share_id))
    _log(access, "kit_share_withdrawn", {"share_id": str(share_id)})
    return share


@router.get("/shares/{token}", response_model=SharedPackage, summary="Open a shared package (recipient view)")
async def open_share(token: str) -> SharedPackage:
    return service.open_share(token)
