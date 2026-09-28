"""Small helpers to put realistic rows in the test database."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import asyncpg

from campfinder.repositories import bookings as bookings_repo
from campfinder.repositories import camps as camps_repo

PROVIDENCE = (41.8240, -71.4128)
CRANSTON = (41.7798, -71.4373)
BOSTON = (42.3601, -71.0589)


async def make_camp(conn: asyncpg.Connection, **overrides: Any) -> UUID:
    camp: dict[str, Any] = {
        "name": "Riverbend Day Camp",
        "city": "Providence",
        "state": "RI",
        "zip": "02903",
        "lat": PROVIDENCE[0],
        "lng": PROVIDENCE[1],
        "camp_type": "day",
        "primary_categories": ["Nature", "Sports"],
        "age_min": 6,
        "age_max": 12,
        "price_per_week": 350,
        "price_min": 350,
        "price_max": 350,
        "description_short": "A week outdoors on the river.",
        "email": "director@riverbend.example",
        "transportation": False,
        "extended_care": True,
        "meals_included": False,
        "financial_aid": False,
        "aca_accredited": True,
        "verification_status": "unverified",
        "season_year": 2027,
    }
    camp.update(overrides)
    camp.setdefault("slug", camps_repo.slugify(camp["name"], camp["city"]))
    return await camps_repo.insert_camp(conn, camp)


async def make_session(conn: asyncpg.Connection, camp_id: UUID, **overrides: Any) -> UUID:
    start = overrides.pop("start_date", date(2027, 7, 5))
    session: dict[str, Any] = {
        "camp_id": camp_id,
        "name": "Week 1",
        "start_date": start,
        "end_date": overrides.pop("end_date", start + timedelta(days=4)),
        "price": 350,
        "availability": "open",
        "spots_total": 40,
        "spots_available": 12,
    }
    session.update(overrides)
    return await camps_repo.insert_session(conn, session)


async def make_contact(conn: asyncpg.Connection, camp_id: UUID, email: str = "owner@riverbend.example") -> dict[str, Any]:
    return await bookings_repo.upsert_contact(conn, camp_id=camp_id, email=email, verified=True, is_primary=True)


def soon(days: int = 3) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)
