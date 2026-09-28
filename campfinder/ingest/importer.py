"""Turn a reviewed ProposedListing into rows: an unverified camp, its sessions, and its sources."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg

from campfinder.ingest.schema import ProposedListing
from campfinder.repositories import camps as repo
from campfinder.services.geo import geocode_location

CAMP_FIELDS = [
    "name", "operator_name", "website_url", "registration_url", "email", "phone", "street_address",
    "city", "state", "zip", "camp_type", "primary_categories", "age_min", "age_max", "grade_min",
    "grade_max", "description_short", "activities", "price_per_week", "price_min", "price_max",
    "deposit_required", "financial_aid", "extended_care", "transportation", "meals_included",
    "refund_policy_summary", "special_needs_notes", "swim_waterfront_notes", "aca_accredited", "season_year",
]
BOOL_DEFAULT_FALSE = {"financial_aid", "extended_care", "transportation", "meals_included"}


class ImportError_(ValueError):
    pass


def listing_to_rows(listing: ProposedListing, *, source_url: str, lat: float | None = None, lng: float | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    missing = [f for f in ("name", "city", "state", "camp_type") if getattr(listing, f) in (None, "")]
    if missing:
        raise ImportError_(f"Cannot import without: {', '.join(missing)}")
    if lat is None or lng is None:
        coords = geocode_location(f"{listing.city}, {listing.state}")
        if coords is None:
            raise ImportError_(f"Unknown location {listing.city}, {listing.state}: pass --lat and --lng")
        lat, lng = coords
    camp: dict[str, Any] = {"lat": lat, "lng": lng, "sources": [source_url], "verification_status": "unverified"}
    for f in CAMP_FIELDS:
        value = getattr(listing, f)
        if value is None and f in BOOL_DEFAULT_FALSE:
            value = False
        if value is not None:
            camp[f] = value
    camp["zip"] = camp.get("zip") or "00000"
    camp["state"] = camp["state"].upper()[:2]
    sessions = []
    for s in listing.sessions:
        if s.start_date is None or s.end_date is None:
            continue
        sessions.append({
            "name": s.name, "start_date": s.start_date, "end_date": s.end_date, "age_min": s.age_min,
            "age_max": s.age_max, "price": s.price, "availability": s.availability,
            "registration_opens_at": datetime.combine(s.registration_opens_at, datetime.min.time(), tzinfo=timezone.utc)
            if s.registration_opens_at else None,
        })
    return camp, sessions


async def import_listing(conn: asyncpg.Connection, listing: ProposedListing, *, source_url: str,
                         lat: float | None = None, lng: float | None = None) -> UUID:
    camp, sessions = listing_to_rows(listing, source_url=source_url, lat=lat, lng=lng)
    async with conn.transaction():
        camp_id = await repo.insert_camp(conn, camp)
        for s in sessions:
            await repo.insert_session(conn, {**s, "camp_id": camp_id})
        now = datetime.now(timezone.utc)
        for f in CAMP_FIELDS:
            if f in camp:
                conf = listing.confidence_for(f)
                await repo.upsert_field_source(conn, {
                    "camp_id": camp_id, "field_name": f, "source_type": "public_web", "source_url": source_url,
                    "last_verified": now, "notes": f"ingest confidence {conf:.2f}" if conf is not None else "ingest",
                })
        await repo.record_listing_change(conn, camp_id=camp_id, field_name="*", changed_by="ingest",
                                         new_value={"source": source_url, "sessions": len(sessions)})
    return camp_id
