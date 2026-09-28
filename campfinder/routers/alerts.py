"""Registration alerts: "tell me when registration opens". Email only, no account needed."""

from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from campfinder.database import get_conn
from campfinder.models.booking import AlertCreate, AlertResponse
from campfinder.repositories import bookings as repo
from campfinder.repositories import camps as camps_repo
from campfinder.security import rate_limited

router = APIRouter()


@router.post("/alerts", response_model=AlertResponse, status_code=201, summary="Create a registration alert",
             dependencies=[Depends(rate_limited)])
async def create_alert(body: AlertCreate, request: Request, conn: asyncpg.Connection = Depends(get_conn)) -> AlertResponse:
    camp = await camps_repo.get_camp(conn, body.camp_id)
    if camp is None or not camp["is_active"]:
        raise HTTPException(status_code=404, detail="Camp not found")
    family_id = None
    family_row = await conn.fetchrow("SELECT id FROM families WHERE email = $1", body.email.lower())
    if family_row:
        family_id = family_row["id"]
    row: dict[str, Any] = await repo.create_alert(conn, email=body.email.lower(), camp_id=camp["id"], family_id=family_id)
    return AlertResponse(**row)


@router.get("/alerts/unsubscribe", summary="Stop an alert")
async def unsubscribe(token: str = Query(min_length=20, max_length=200), conn: asyncpg.Connection = Depends(get_conn)) -> dict[str, str]:
    if not await repo.unsubscribe_alert(conn, token):
        raise HTTPException(status_code=404, detail="Unknown alert")
    return {"status": "unsubscribed"}
