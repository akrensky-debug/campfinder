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

from campfinder.database import get_supabase
from campfinder.models.camp import CampSearchResult
from campfinder.models.search import SearchRequest, SearchResponse
from campfinder.services.camps import camp_url
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
        camp["detail_url"] = camp_url(camp)
        results.append(camp)

    # Sort
    if sort == "best_match":
        results.sort(key=lambda c: c["match_score"], reverse=True)
    elif sort == "distance":
        results.sort(key=lambda c: c.get("distance_miles") or 9999)
    elif sort == "price":
        results.sort(key=lambda c: float(c.get("price_per_week") or 9999))

    return results[:limit]


async def run_search(req: SearchRequest) -> SearchResponse:
    """Search, rank and shape the results. What the API, the agent and the MCP server call."""
    camps = await search_camps(
        get_supabase(),
        location=req.location,
        radius_miles=req.radius_miles,
        age=req.age,
        camp_type=req.camp_type,
        categories=req.categories,
        weeks=req.weeks,
        max_price_per_week=req.max_price_per_week,
        requires_transport=req.requires_transport,
        requires_extended_care=req.requires_extended_care,
        requires_meals=req.requires_meals,
        requires_financial_aid=req.requires_financial_aid,
        requires_accreditation=req.requires_accreditation,
        limit=req.limit,
        sort=req.sort,
    )
    results = [to_search_result(c) for c in camps]
    return SearchResponse(results=results, total=len(results), location=req.location, radius_miles=req.radius_miles)


def to_search_result(camp: dict[str, Any]) -> CampSearchResult:
    return CampSearchResult(
        id=camp["id"],
        slug=camp.get("slug"),
        name=camp["name"],
        city=camp["city"],
        state=camp["state"],
        camp_type=camp["camp_type"],
        is_day_camp=camp.get("is_day_camp") or False,
        is_sleepaway=camp.get("is_sleepaway") or False,
        is_specialty=camp.get("is_specialty") or False,
        primary_categories=list(camp.get("primary_categories") or []),
        age_min=camp.get("age_min"),
        age_max=camp.get("age_max"),
        price_per_week=float(camp["price_per_week"]) if camp.get("price_per_week") else None,
        price_min=float(camp["price_min"]) if camp.get("price_min") else None,
        price_max=float(camp["price_max"]) if camp.get("price_max") else None,
        transportation=camp.get("transportation") or False,
        extended_care=camp.get("extended_care") or False,
        meals_included=camp.get("meals_included") or False,
        financial_aid=camp.get("financial_aid") or False,
        aca_accredited=camp.get("aca_accredited"),
        verification_status=camp.get("verification_status", "unverified"),
        last_updated_date=camp.get("last_updated_date"),
        description_short=camp.get("description_short"),
        hero_image_url=camp.get("hero_image_url"),
        distance_miles=camp.get("distance_miles"),
        match_score=camp.get("match_score"),
        match_reasons=camp.get("match_reasons", []),
        detail_url=camp.get("detail_url"),
    )
