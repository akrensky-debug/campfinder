"""
/api/v1/me: the family profile.

Every route needs a signed-in parent. Export and delete are here from day
one: the parent can take everything we hold or remove it, without asking us.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Response, status

from campfinder.config import Settings, get_settings
from campfinder.database import get_conn
from campfinder.models.family import (
    ChildInput,
    ChildResponse,
    ChildUpdate,
    FamilyExport,
    FamilyResponse,
    FamilyUpdate,
    MedicalInput,
    MedicalResponse,
)
from campfinder.repositories import families as repo
from campfinder.security import Identity, current_identity

router = APIRouter(prefix="/me")


async def current_family(
    identity: Identity = Depends(current_identity),
    conn: asyncpg.Connection = Depends(get_conn),
) -> dict[str, Any]:
    """The signed-in parent's family row, created on first sight."""
    return await repo.get_or_create_family(conn, auth_subject=identity.subject, email=identity.email)


@router.get("", response_model=FamilyResponse, summary="My profile")
async def get_me(family: dict[str, Any] = Depends(current_family)) -> FamilyResponse:
    return FamilyResponse(**family)


@router.put("", response_model=FamilyResponse, summary="Update my profile")
async def update_me(
    body: FamilyUpdate,
    family: dict[str, Any] = Depends(current_family),
    conn: asyncpg.Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings),
) -> FamilyResponse:
    fields = body.model_dump(exclude={"accept_privacy_policy"}, exclude_none=True)
    if body.accept_privacy_policy:
        fields["privacy_policy_version"] = settings.privacy_policy_version
        fields["consented_at"] = datetime.now(timezone.utc)
    updated = await repo.update_family(conn, family["id"], fields)
    return FamilyResponse(**updated)


@router.get("/export", response_model=FamilyExport, summary="Download everything we hold")
async def export_me(
    family: dict[str, Any] = Depends(current_family),
    conn: asyncpg.Connection = Depends(get_conn),
) -> FamilyExport:
    data = await repo.export_family(conn, family["id"])
    return FamilyExport(exported_at=datetime.now(timezone.utc), **data)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, summary="Delete my family and all its data")
async def delete_me(
    family: dict[str, Any] = Depends(current_family),
    conn: asyncpg.Connection = Depends(get_conn),
) -> Response:
    await repo.delete_family(conn, family["id"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Children ───────────────────────────────────────────────────────────────

@router.get("/children", response_model=list[ChildResponse], summary="My children")
async def list_children(
    family: dict[str, Any] = Depends(current_family),
    conn: asyncpg.Connection = Depends(get_conn),
) -> list[ChildResponse]:
    return [ChildResponse.from_row(r) for r in await repo.list_children(conn, family["id"])]


@router.post("/children", response_model=ChildResponse, status_code=201, summary="Add a child")
async def add_child(
    body: ChildInput,
    family: dict[str, Any] = Depends(current_family),
    conn: asyncpg.Connection = Depends(get_conn),
) -> ChildResponse:
    if len(await repo.list_children(conn, family["id"])) >= 10:
        raise HTTPException(status_code=422, detail="Up to 10 children per family")
    return ChildResponse.from_row(await repo.create_child(conn, family["id"], body.model_dump()))


@router.put("/children/{child_id}", response_model=ChildResponse, summary="Update a child")
async def update_child(
    child_id: UUID,
    body: ChildUpdate,
    family: dict[str, Any] = Depends(current_family),
    conn: asyncpg.Connection = Depends(get_conn),
) -> ChildResponse:
    row = await repo.update_child(conn, family["id"], child_id, body.model_dump(exclude_none=True))
    if row is None:
        raise HTTPException(status_code=404, detail="Child not found")
    return ChildResponse.from_row(row)


@router.delete("/children/{child_id}", status_code=204, summary="Remove a child")
async def delete_child(
    child_id: UUID,
    family: dict[str, Any] = Depends(current_family),
    conn: asyncpg.Connection = Depends(get_conn),
) -> Response:
    if not await repo.delete_child(conn, family["id"], child_id):
        raise HTTPException(status_code=404, detail="Child not found")
    return Response(status_code=204)


@router.get("/children/{child_id}/medical", response_model=MedicalResponse, summary="A child's forms")
async def get_medical(
    child_id: UUID,
    family: dict[str, Any] = Depends(current_family),
    conn: asyncpg.Connection = Depends(get_conn),
) -> MedicalResponse:
    row = await repo.get_medical(conn, family["id"], child_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No forms on file for this child")
    return MedicalResponse(**row)


@router.put("/children/{child_id}/medical", response_model=MedicalResponse, summary="Fill in a child's forms once")
async def put_medical(
    child_id: UUID,
    body: MedicalInput,
    family: dict[str, Any] = Depends(current_family),
    conn: asyncpg.Connection = Depends(get_conn),
) -> MedicalResponse:
    row = await repo.upsert_medical(conn, family["id"], child_id, body.model_dump())
    if row is None:
        raise HTTPException(status_code=404, detail="Child not found")
    return MedicalResponse(**row)
