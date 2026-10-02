"""
Map CampFinder's stored records onto the Family Activity schema.

Camps are the only source today. New program types (classes, leagues, ...) get their
own mapper here and are merged into the same results, so the public API doesn't change.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from campfinder.activity.schema import (
    AgeRange, Location, Logistics, Policies, Price, Program, Provider, Session, Verification,
)
from campfinder.config import get_settings
from campfinder.database import get_supabase
from campfinder.routers.camps import _build_trust_summary
from campfinder.services.geo import geocode_location
from campfinder.services.search import search_camps

CAMP_FORMAT = {"day": "day", "sleepaway": "overnight", "specialty": "specialty"}
AVAILABILITY = {"open", "limited", "waitlist", "full"}


def _num(v: Any) -> float | None:
    return float(v) if v not in (None, "") else None


def session_from_row(s: dict[str, Any], api_base: str) -> Session:
    availability = s.get("availability") or "unknown"
    return Session(
        id=s["id"],
        program_id=s["camp_id"],
        name=s.get("name"),
        start_date=s["start_date"],
        end_date=s["end_date"],
        length_weeks=_num(s.get("length_weeks")),
        price=_num(s.get("price")),
        availability=availability if availability in AVAILABILITY else "unknown",
        full_season=bool(s.get("full_season")),
        calendar_url=f"{api_base}/sessions/{s['id']}.ics",
    )


def program_from_camp(
    camp: dict[str, Any],
    *,
    api_base: str,
    sessions: list[dict[str, Any]] | None = None,
    field_sources: list[dict[str, Any]] | None = None,
    include_policies: bool = False,
) -> Program:
    trust = _build_trust_summary(camp, field_sources or [], bool(sessions))
    coords = geocode_location(f"{camp['city']}, {camp['state']}")
    frontend = get_settings().frontend_url.rstrip("/")
    return Program(
        id=camp["id"],
        kind="camp",
        format=CAMP_FORMAT.get(camp.get("camp_type", ""), camp.get("camp_type")),
        name=camp["name"],
        description=camp.get("description_short"),
        categories=list(camp.get("primary_categories") or []) + list(camp.get("secondary_categories") or []),
        activities=list(camp.get("activities") or []),
        ages=AgeRange(
            min=camp.get("age_min"), max=camp.get("age_max"),
            grade_min=camp.get("grade_min"), grade_max=camp.get("grade_max"),
        ),
        location=Location(
            address=camp.get("street_address"), city=camp["city"], state=camp["state"],
            postal_code=camp.get("zip"), region=camp.get("region"),
            latitude=coords[0] if coords else None, longitude=coords[1] if coords else None,
        ),
        distance_miles=camp.get("distance_miles"),
        provider=Provider(
            name=camp.get("operator_name"), website=camp.get("website_url"),
            email=camp.get("email"), phone=camp.get("phone"),
        ),
        price=Price(
            per_week=_num(camp.get("price_per_week")), min=_num(camp.get("price_min")),
            max=_num(camp.get("price_max")), unit=camp.get("price_per"),
            deposit_required=camp.get("deposit_required"), financial_aid=bool(camp.get("financial_aid")),
        ),
        logistics=Logistics(
            extended_care=bool(camp.get("extended_care")), transportation=bool(camp.get("transportation")),
            meals_included=bool(camp.get("meals_included")), indoor_outdoor=camp.get("indoor_outdoor"),
            gender_policy=camp.get("gender_policy"),
        ),
        policies=Policies(
            refunds=camp.get("refund_policy_summary"), special_needs=camp.get("special_needs_notes"),
            medical=camp.get("medical_support_notes"), swimming=camp.get("swim_waterfront_notes"),
        ) if include_policies else None,
        verification=Verification(
            status=trust.verification_status if trust.verification_status in
            ("team_verified", "camp_verified", "claimed") else "unverified",
            last_updated=trust.last_updated,
            accredited_by=["ACA"] if camp.get("aca_accredited") else [],
            fields_verified=trust.fields_verified,
            fields_unverified=trust.fields_unverified,
            fields_missing=trust.fields_missing,
        ),
        registration_url=camp.get("registration_url"),
        url=f"{frontend}/camps/{camp['id']}",
        sessions=[session_from_row(s, api_base) for s in sorted(sessions, key=lambda s: str(s["start_date"]))]
        if sessions is not None else None,
        match_reasons=list(camp.get("match_reasons") or []),
    )


def _field_sources_by_camp(camp_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not camp_ids:
        return {}
    rows = get_supabase().table("field_sources").select("*").in_("camp_id", camp_ids).execute().data or []
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["camp_id"], []).append(r)
    return out


async def find_programs(
    *,
    near: str,
    api_base: str,
    radius_miles: float,
    age: int | None,
    kind: str | None,
    format: str | None,
    categories: list[str] | None,
    max_price_per_week: float | None,
    needs_extended_care: bool,
    needs_transportation: bool,
    needs_meals: bool,
    needs_financial_aid: bool,
    accredited_only: bool,
    sort: str,
    limit: int,
    offset: int,
    include_sessions: bool,
) -> tuple[list[Program], int]:
    """Search programs. Returns (page, total matched up to the search cap)."""
    if kind not in (None, "camp"):
        return [], 0  # other kinds have no data yet
    camp_type = {"day": "day", "overnight": "sleepaway", "specialty": "specialty"}.get(format or "")
    camps = await search_camps(
        get_supabase(),
        location=near, radius_miles=radius_miles, age=age, camp_type=camp_type, categories=categories,
        max_price_per_week=max_price_per_week, requires_transport=needs_transportation,
        requires_extended_care=needs_extended_care, requires_meals=needs_meals,
        requires_financial_aid=needs_financial_aid, requires_accreditation=accredited_only,
        limit=500, sort=sort,
    )
    page = camps[offset:offset + limit]
    sources = _field_sources_by_camp([c["id"] for c in page])
    return [
        program_from_camp(
            c, api_base=api_base, field_sources=sources.get(c["id"]),
            sessions=c.get("sessions") if include_sessions else None,
        )
        for c in page
    ], len(camps)


def get_program(program_id: str, api_base: str) -> Program | None:
    client = get_supabase()
    rows = client.table("camps").select("*").eq("id", program_id).execute().data
    if not rows:
        return None
    sessions = client.table("sessions").select("*").eq("camp_id", program_id).execute().data or []
    return program_from_camp(
        rows[0], api_base=api_base, sessions=sessions,
        field_sources=_field_sources_by_camp([program_id]).get(program_id), include_policies=True,
    )


async def find_sessions(
    *,
    near: str,
    api_base: str,
    radius_miles: float,
    age: int | None,
    categories: list[str] | None,
    max_price_per_week: float | None,
    starts_on_or_after: date | None,
    ends_on_or_before: date | None,
    open_only: bool,
    limit: int,
) -> list[tuple[Session, Program]]:
    """Dated sessions that fit a window: the 'what can my kid do the week of July 6?' query."""
    camps = await search_camps(
        get_supabase(), location=near, radius_miles=radius_miles, age=age, categories=categories,
        max_price_per_week=max_price_per_week, limit=500, sort="best_match",
    )
    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for camp in camps:
        for s in camp.get("sessions") or []:
            start, end = date.fromisoformat(str(s["start_date"])), date.fromisoformat(str(s["end_date"]))
            if starts_on_or_after and start < starts_on_or_after:
                continue
            if ends_on_or_before and end > ends_on_or_before:
                continue
            if open_only and (s.get("availability") or "unknown") == "full":
                continue
            matches.append((s, camp))
    matches.sort(key=lambda m: (str(m[0]["start_date"]), -(m[1].get("match_score") or 0)))
    matches = matches[:limit]
    sources = _field_sources_by_camp(list({c["id"] for _, c in matches}))
    programs: dict[str, Program] = {}
    out = []
    for s, camp in matches:
        if camp["id"] not in programs:
            programs[camp["id"]] = program_from_camp(camp, api_base=api_base, field_sources=sources.get(camp["id"]))
        out.append((session_from_row(s, api_base), programs[camp["id"]]))
    return out


def get_session_with_program(session_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    client = get_supabase()
    rows = client.table("sessions").select("*").eq("id", session_id).execute().data
    if not rows:
        return None
    camp = client.table("camps").select("*").eq("id", rows[0]["camp_id"]).execute().data
    return (rows[0], camp[0]) if camp else None
