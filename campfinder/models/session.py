"""Pydantic models for camp sessions."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class SessionResponse(BaseModel):
    id: UUID
    camp_id: UUID
    name: str | None = None
    start_date: date
    end_date: date
    age_min: int | None = None
    age_max: int | None = None
    price: float | None = None
    full_season: bool = False
    availability: str = "unknown"
    spots_total: int | None = None
    spots_available: int | None = None
    registration_opens_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_row(cls, r: dict[str, Any]) -> "SessionResponse":
        data = {k: v for k, v in r.items() if k in cls.model_fields}
        data["price"] = float(r["price"]) if r.get("price") is not None else None
        return cls(**data)
