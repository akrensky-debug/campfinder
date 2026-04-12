"""
Core search logic: fetch camps via Supabase REST API, apply geo + attribute
filters in Python, score, and return ranked results.

This approach is correct for the current data size (50–500 camps). When the
dataset grows, replace the full-table fetch with a PostGIS RPC function
(see services/geo.py for the SQL to add).
"""

from __future__ import annotations

from typing import Any

from supabase import Client

from campfinder.services.geo import geocode_location, haversine_miles
from campfinder.services.ranking import score_camp


async def search_camps(
    client: Client,
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
) -> list[dict[str, Any]]:
    """
    Search camps filtered by location radius and optional attributes.
    Geo filtering is performed in Python using the city coordinate lookup.
    """
    coords = geocode_location(location)
    if coords is None:
        return []
    ref_lat, ref_lng = coords

    # Fetch all active camps (REST API — no raw SQL needed)
    query = client.table("camps").select("*").eq("is_active", True)

    # Push simple equality filters to the server to reduce payload
    if camp_type:
        query = query.eq("camp_type", camp_type)
    if requires_transport:
        query = query.eq("transportation", True)
    if requires_extended_care:
        query = query.eq("extended_care", True)
    if requires_meals:
        query = query.eq("meals_included", True)
    if requires_financial_aid:
        query = query.eq("financial_aid", True)
    if requires_accreditation:
        query = query.eq("aca_accredited", True)

    response = query.execute()
    all_camps: list[dict[str, Any]] = response.data or []

    # Fetch sessions for all camps in one call
    session_response = client.table("sessions").select("*").execute()
    sessions_by_camp: dict[str, list[dict[str, Any]]] = {}
    for s in session_response.data or []:
        sessions_by_camp.setdefault(s["camp_id"], []).append(s)

    results: list[dict[str, Any]] = []

    for camp in all_camps:
        # --- Geo filter ---
        camp_coords = geocode_location(f"{camp['city']}, {camp['state']}")
        if camp_coords is None:
            continue
        distance = haversine_miles(ref_lat, ref_lng, camp_coords[0], camp_coords[1])
        if distance > radius_miles:
            continue

        # --- Age filter ---
        if age is not None:
            mn, mx = camp.get("age_min"), camp.get("age_max")
            if mn is not None and age < mn:
                continue
            if mx is not None and age > mx:
                continue

        # --- Price filter ---
        if max_price_per_week is not None:
            ppw = camp.get("price_per_week")
            if ppw is not None and float(ppw) > max_price_per_week:
                continue

        # --- Category filter ---
        if categories:
            camp_cats = [c.lower() for c in (camp.get("primary_categories") or [])]
            if not any(cat.lower() in camp_cats for cat in categories):
                continue

        camp_sessions = sessions_by_camp.get(camp["id"], [])

        score, reasons = score_camp(
            camp,
            camp_sessions,
            age=age,
            requested_weeks=weeks,
            categories=categories,
            distance_miles=distance,
            max_price_per_week=max_price_per_week,
        )

        camp["distance_miles"] = round(distance, 2)
        camp["match_score"] = round(score, 4)
        camp["match_reasons"] = reasons
        camp["sessions"] = camp_sessions
        camp["detail_url"] = f"https://campfinder.com/camps/{camp['id']}"
        results.append(camp)

    # Sort
    if sort == "best_match":
        results.sort(key=lambda c: c["match_score"], reverse=True)
    elif sort == "distance":
        results.sort(key=lambda c: c.get("distance_miles") or 9999)
    elif sort == "price":
        results.sort(key=lambda c: float(c.get("price_per_week") or 9999))

    return results[:limit]
