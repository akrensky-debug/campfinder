"""Pydantic v2 models for the summer planner."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel


class PlanSessionInput(BaseModel):
    camp_id: UUID
    session_id: UUID


class PlanRequest(BaseModel):
    camp_sessions: list[PlanSessionInput]
    summer_start: date
    summer_end: date


class PlanWeekCamp(BaseModel):
    camp_id: UUID
    name: str
    session_id: UUID
    session_dates: str  # e.g. "Jun 9 - Jun 20"
    cost: float | None = None


class PlanWeek(BaseModel):
    week_of: date
    week_end: date
    status: str  # "covered", "gap", "overlap"
    camps: list[PlanWeekCamp] = []


class PlanResponse(BaseModel):
    weeks: list[PlanWeek]
    total_estimated_cost: float
    weeks_covered: int
    weeks_total: int
    gaps: list[date]
    overlaps: list[date]
