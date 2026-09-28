"""
Search: geocode the parent's location, filter in Postgres, score in Python.

The database returns at most a few hundred nearby candidates already filtered
on the hard constraints. Scoring and match_reasons run on that set.
"""

from __future__ import annotations

from typing import Any

import asyncpg

from campfinder.repositories import camps as camps_repo
from campfinder.services.geo import geocode_location
from campfinder.services.ranking import score_camp


async def search_camps(
    conn: asyncpg.Connection,
    *,
    location: str,
    radius_miles: float = 30.0,
    age: int | None = None,
    camp_type: str | None = None,
    categories: list[str] | None = None,
    weeks: list[str] | None = None,
    max_price_per_week: float | None = None,
    requires_transport: bool = False,
    requires_extended_care: bool = False,
    requires_meals: bool = False,
    requires_financial_aid: bool = False,
    requires_accreditation: bool = False,
    limit: int = 10,
    sort: str = "best_match",
) -> list[dict[str, Any]] | None:
    """Return ranked camps, or None when the location cannot be geocoded."""
    coords = geocode_location(location)
    if coords is None:
        return None
    lat, lng = coords

    candidates = await camps_repo.search_camps(
        conn, lat=lat, lng=lng, radius_miles=radius_miles, age=age, camp_type=camp_type,
        categories=categories, max_price_per_week=max_price_per_week,
        requires_transport=requires_transport, requires_extended_care=requires_extended_care,
        requires_meals=requires_meals, requires_financial_aid=requires_financial_aid,
        requires_accreditation=requires_accreditation,
    )
    if not candidates:
        return []

    sessions_by_camp = await camps_repo.sessions_for_camps(conn, [c["id"] for c in candidates])

    for camp in candidates:
        camp_sessions = sessions_by_camp.get(camp["id"], [])
        score, reasons = score_camp(
            camp, camp_sessions, age=age, requested_weeks=weeks, categories=categories,
            distance_miles=camp["distance_miles"], max_price_per_week=max_price_per_week,
        )
        camp["match_score"] = round(score, 4)
        camp["match_reasons"] = reasons
        camp["sessions"] = camp_sessions

    if sort == "distance":
        candidates.sort(key=lambda c: c["distance_miles"])
    elif sort == "price":
        candidates.sort(key=lambda c: float(c["price_per_week"]) if c.get("price_per_week") is not None else 1e9)
    else:
        candidates.sort(key=lambda c: (-c["match_score"], c["distance_miles"]))

    return candidates[:limit]
