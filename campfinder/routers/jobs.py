"""POST /api/v1/internal/cron/tick: the one endpoint the hourly scheduler calls."""

from __future__ import annotations

import hmac
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from campfinder.jobs.tick import tick

router = APIRouter()


@router.post("/internal/cron/tick", include_in_schema=False)
async def cron_tick(dry_run: bool = False, at: datetime | None = None,
                    x_cron_secret: str | None = Header(default=None)) -> dict[str, Any]:
    secret = os.environ.get("BOOKING_CRON_SECRET", "")
    if not secret or not x_cron_secret or not hmac.compare_digest(secret, x_cron_secret):
        raise HTTPException(status_code=404, detail="Not found")
    return await tick(at, dry_run)
