"""
Public registration alerts: a parent leaves an email on a camp's page, no account.
Not on the MCP server or the Activity API: this is a parent's address, used only to email them.
"""

from __future__ import annotations

import hmac
import os
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from campfinder.alerts import service

router = APIRouter()


class AlertSignup(BaseModel):
    email: str = Field(max_length=254)
    session_id: UUID | None = None


@router.post("/camps/{camp_id}/registration/alerts", status_code=202,
             summary="Email me when registration opens (sends a confirm link first)")
async def sign_up(camp_id: UUID, req: AlertSignup) -> dict:
    try:
        await service.sign_up(str(camp_id), str(req.session_id) if req.session_id else None, req.email)
    except service.AlertError as e:
        raise HTTPException(status_code=422, detail=str(e))
    # The same answer whether the address was new, pending or already signed up.
    return {"status": "check_email"}


@router.get("/registration-alerts/{token}", summary="An alert's camp and status (changes nothing)")
async def view(token: str) -> dict:
    return service.view(token)


@router.post("/registration-alerts/{token}/confirm", summary="Confirm the address and start alerts")
async def confirm(token: str) -> dict:
    return service.confirm(token)


@router.post("/registration-alerts/{token}/stop", summary="Stop alerts for this camp")
async def stop(token: str) -> dict:
    return service.stop(token)


@router.post("/internal/registration-alerts/run", summary="Cron (hourly): send due registration alerts")
async def run(dry_run: bool = False, at: datetime | None = None,
              x_cron_secret: str | None = Header(default=None)) -> dict:
    secret = os.environ.get("BOOKING_CRON_SECRET", "")
    if not secret or not x_cron_secret or not hmac.compare_digest(secret, x_cron_secret):
        raise HTTPException(status_code=404, detail="Not found")
    return await service.run(at, dry_run)
