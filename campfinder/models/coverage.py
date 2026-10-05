"""Pydantic v2 models for the summer coverage planner."""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

WeekStatus = Literal["covered", "check_hours", "partial", "open", "away", "not_needed"]


class WorkBlock(BaseModel):
    """When one parent is at work. A parent with different hours on different days has one block per pattern."""

    parent: str = Field(description="First name or role, e.g. 'Mom', 'Dad'.")
    days: list[str] = Field(description="Weekdays worked, e.g. ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'].")
    start: str = Field(description="Leaves for work / starts, e.g. '8:30' or '8:30am'.")
    end: str = Field(description="Back / available again, e.g. '17:30' or '5:30pm'.")


class AwayRange(BaseModel):
    """Dates nobody needs camp: family vacation, travel, a week with relatives."""

    start_date: date
    end_date: date = Field(description="Inclusive last day.")
    label: str = Field(description="e.g. 'Cape Cod vacation', 'Week at Grandma's'.")
    child_name: str | None = Field(
        default=None, description="Only this kid is away (e.g. at Grandma's). Omit when the whole family is."
    )


class CoverageOption(BaseModel):
    camp_id: UUID
    name: str
    city: str
    distance_miles: float | None = None
    extended_care: bool | None = None
    transportation: bool | None = None
    price_per_week: float | None = None
    session_id: UUID
    session_name: str | None = None
    start_date: date
    end_date: date
    last_season: bool = Field(
        default=False, description="The camp ran this week last season; this season's dates are not posted yet."
    )


class CoverageGap(BaseModel):
    day: date
    uncovered: str = Field(description="'all day' or the uncovered hours, e.g. '7:30-9:00'.")


class CoverageWeek(BaseModel):
    week_of: date
    week_end: date
    status: WeekStatus
    days_needed: int
    days_covered: int
    covered_by: list[str] = []
    away: list[str] = []
    gaps: list[CoverageGap] = []
    check_hours: list[str] = Field(
        default=[], description="Camps whose daily hours we don't know; confirm they cover the workday."
    )
    options: list[CoverageOption] = []


class KidCoverage(BaseModel):
    name: str
    age: int | None = None
    weeks: list[CoverageWeek]
    weeks_open: int
    weeks_partial: int
    weeks_covered: int


class CoverageResponse(BaseModel):
    summer_start: date
    summer_end: date
    care_hours: dict[str, str] = Field(description="Weekday -> hours when every parent is at work, e.g. 'Mon': '8:30-17:00'.")
    kids: list[KidCoverage]
    notes: list[str] = []
