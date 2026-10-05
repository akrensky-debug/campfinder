"""Pydantic v2 models for camp sessions."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SessionResponse(BaseModel):
    id: UUID
    camp_id: UUID
    name: str | None = None
    start_date: date
    end_date: date
    length_days: int | None = None
    length_weeks: float | None = None
    price: float | None = None
    full_season: bool = False
    availability: str = "unknown"
    spots_total: int | None = None
    spots_available: int | None = Field(
        default=None, description="Spots left. Null means unknown, which is not the same as 0 (full).")
    spots_updated_at: datetime | None = Field(default=None, description="When spots_available was last set.")
    spots_source: str | None = Field(default=None, description="Who set it: owner, team or import.")
    created_at: datetime | None = None
    updated_at: datetime | None = None
