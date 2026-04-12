"""Pydantic v2 models for camp sessions."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


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
    created_at: datetime | None = None
    updated_at: datetime | None = None
