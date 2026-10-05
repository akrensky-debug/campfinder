"""Compare 2–5 camps side by side."""

from __future__ import annotations

from typing import Any

from campfinder.database import get_supabase
from campfinder.models.compare import CampComparison, CompareRequest, CompareResponse, SessionRange
from campfinder.services.differences import generate_differences
from campfinder.services.errors import NotFound
from campfinder.services.geo import geocode_location, haversine_miles


def compare_camps(req: CompareRequest) -> CompareResponse:
    """2–5 camps side by side, with plain-language differences. NotFound names any camp that
    doesn't exist or was taken off the site."""
    client = get_supabase()
    camp_ids = [str(cid) for cid in req.camp_ids]

    ref_coords = geocode_location(req.reference_location) if req.reference_location else None

    rows = client.table("camps").select("*").in_("id", camp_ids).execute().data or []
    rows = [r for r in rows if r.get("is_active") is not False]  # taken down: as if it didn't exist
    if len(rows) != len(camp_ids):
        found = {r["id"] for r in rows}
        missing = [cid for cid in camp_ids if cid not in found]
        raise NotFound(f"Camps not found: {missing}")

    session_rows = client.table("sessions").select("*").in_("camp_id", camp_ids).order("start_date").execute().data or []
    sessions_by_camp: dict[str, list[dict[str, Any]]] = {}
    for s in session_rows:
        sessions_by_camp.setdefault(s["camp_id"], []).append(s)

    row_map = {r["id"]: r for r in rows}
    comparisons: list[CampComparison] = []
    diff_input: list[dict[str, Any]] = []

    for cid in camp_ids:
        camp = row_map[cid]
        camp_sessions = sessions_by_camp.get(cid, [])

        distance = None
        if ref_coords:
            coords = geocode_location(f"{camp['city']}, {camp['state']}")
            if coords:
                distance = round(haversine_miles(ref_coords[0], ref_coords[1], coords[0], coords[1]), 2)

        comparisons.append(CampComparison(
            camp_id=camp["id"],
            name=camp["name"],
            city=camp["city"],
            state=camp["state"],
            camp_type=camp["camp_type"],
            age_min=camp.get("age_min"),
            age_max=camp.get("age_max"),
            price_min=float(camp["price_min"]) if camp.get("price_min") else None,
            price_max=float(camp["price_max"]) if camp.get("price_max") else None,
            price_per_week=float(camp["price_per_week"]) if camp.get("price_per_week") else None,
            session_count=len(camp_sessions),
            sessions=[
                SessionRange(
                    session_id=s["id"], name=s.get("name"),
                    start_date=str(s["start_date"]), end_date=str(s["end_date"]),
                    price=float(s["price"]) if s.get("price") else None,
                )
                for s in camp_sessions
            ],
            transportation=camp.get("transportation") or False,
            extended_care=camp.get("extended_care") or False,
            meals_included=camp.get("meals_included") or False,
            aca_accredited=camp.get("aca_accredited"),
            verification_status=camp.get("verification_status", "unverified"),
            refund_policy_summary=camp.get("refund_policy_summary"),
            primary_categories=list(camp.get("primary_categories") or []),
            distance_miles=distance,
        ))

        diff_camp = dict(camp)
        diff_camp["sessions"] = camp_sessions
        diff_camp["distance_miles"] = distance
        diff_input.append(diff_camp)

    return CompareResponse(
        camps=comparisons,
        differences=generate_differences(diff_input),
    )
