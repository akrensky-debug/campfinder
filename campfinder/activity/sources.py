"""
Map CampFinder's stored records onto the Family Activity schema.

Two sources feed the same results: camps (with dated week-long sessions) and year-round
programs (classes, lessons, leagues, after-school, with recurring offerings). Each has a
mapper here; searches merge them so the public API and MCP see one list of programs.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from campfinder.activity import programs as activities
from campfinder.activity.schedule import TimeWindow, parse_date
from campfinder.activity.schema import (
    AgeRange, EnrollmentWindow, Location, Logistics, Policies, Price, PriceOption, Program, Provider,
    Schedule, Session, Verification,
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
    days_of_week: list[str] | None = None,
    earliest_start: str | None = None,
    latest_end: str | None = None,
    max_price_per_class: float | None = None,
) -> tuple[list[Program], int]:
    """Search camps and year-round programs together. Returns (page, total matched up to the cap)."""
    camp_only_filters = (format or needs_extended_care or needs_transportation or needs_meals
                         or needs_financial_aid or accredited_only or max_price_per_week is not None)
    schedule_filters = bool(days_of_week or earliest_start or latest_end or max_price_per_class is not None)
    want_camps = kind in (None, "camp") and not schedule_filters
    want_activities = kind != "camp" and not camp_only_filters

    activity_rows: list[dict[str, Any]] = []
    if want_activities:
        activity_rows = activities.search_activities(get_supabase(), activities.ActivityQuery(
            location=near, radius_miles=radius_miles, age=age,
            kinds=[kind] if kind else None, interests=categories,
            window=TimeWindow.build(days_of_week, earliest_start, latest_end),
            max_price_per_class=max_price_per_class,
        ), limit=500)
    if not want_camps:
        page_rows = activity_rows[offset:offset + limit]
        sources = activities.load_field_sources(get_supabase(), [p["id"] for p in page_rows])
        return [
            program_from_activity(p, api_base=api_base, field_sources=sources.get(p["id"]),
                                  include_sessions=include_sessions)
            for p in page_rows
        ], len(activity_rows)

    camp_type = {"day": "day", "overnight": "sleepaway", "specialty": "specialty"}.get(format or "")
    camps = await search_camps(
        get_supabase(),
        location=near, radius_miles=radius_miles, age=age, camp_type=camp_type, categories=categories,
        max_price_per_week=max_price_per_week, requires_transport=needs_transportation,
        requires_extended_care=needs_extended_care, requires_meals=needs_meals,
        requires_financial_aid=needs_financial_aid, requires_accreditation=accredited_only,
        limit=500, sort=sort,
    )
    merged: list[tuple[str, dict[str, Any]]] = [("camp", c) for c in camps] + [("activity", a) for a in activity_rows]
    if sort == "distance":
        merged.sort(key=lambda m: m[1].get("distance_miles") if m[1].get("distance_miles") is not None else 9999)
    elif sort == "best_match" and activity_rows:
        # Camp scores start at 1.0 (services/ranking.py); activity scores are 0-1.
        merged.sort(key=lambda m: -((m[1].get("match_score") or 0) + (1.0 if m[0] == "activity" else 0.0)))
    page = merged[offset:offset + limit]
    camp_sources = _field_sources_by_camp([r["id"] for k, r in page if k == "camp"])
    act_sources = activities.load_field_sources(get_supabase(), [r["id"] for k, r in page if k == "activity"])
    return [
        program_from_camp(
            r, api_base=api_base, field_sources=camp_sources.get(r["id"]),
            sessions=r.get("sessions") if include_sessions else None,
        ) if k == "camp" else program_from_activity(
            r, api_base=api_base, field_sources=act_sources.get(r["id"]), include_sessions=include_sessions,
        )
        for k, r in page
    ], len(merged)


def get_program(program_id: str, api_base: str) -> Program | None:
    client = get_supabase()
    rows = client.table("camps").select("*").eq("id", program_id).execute().data
    if not rows:
        found = activities.load_catalog(client, program_ids=[program_id])
        if not found:
            return None
        return program_from_activity(
            found[0], api_base=api_base, include_sessions=True, include_policies=True,
            field_sources=activities.load_field_sources(client, [program_id]).get(program_id),
        )
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
    include_camps: bool = True,
    include_activities: bool = False,
) -> list[tuple[Session, Program]]:
    """Dated sessions that fit a window: the 'what can my kid do the week of July 6?' query.

    With include_activities, recurring offerings (a fall swim term, a spring league season)
    that start and end inside the window are included too."""
    activity_matches = _find_activity_sessions(
        near=near, api_base=api_base, radius_miles=radius_miles, age=age, categories=categories,
        starts_on_or_after=starts_on_or_after, ends_on_or_before=ends_on_or_before, open_only=open_only,
    ) if include_activities else []
    if not include_camps:
        return activity_matches[:limit]
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
    if activity_matches:
        out = sorted(out + activity_matches, key=lambda m: str(m[0].start_date or "9999"))[:limit]
    return out


def get_session_with_program(session_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    client = get_supabase()
    rows = client.table("sessions").select("*").eq("id", session_id).execute().data
    if not rows:
        return None
    camp = client.table("camps").select("*").eq("id", rows[0]["camp_id"]).execute().data
    return (rows[0], camp[0]) if camp else None


def get_offering_with_program(offering_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """A recurring offering and its program, for calendar files."""
    client = get_supabase()
    rows = client.table("program_offerings").select("*").eq("id", offering_id).execute().data
    if not rows:
        return None
    program = client.table("programs").select("*").eq("id", rows[0]["program_id"]).execute().data
    return (rows[0], program[0]) if program else None


# ---------------------------------------------------------------------------
# Year-round programs (classes, lessons, leagues, after-school, events)
# ---------------------------------------------------------------------------

# Facts a parent needs before enrolling; reported in verification.fields_missing when unknown.
ACTIVITY_KEY_FIELDS = ("age_min", "age_max", "provider_phone", "registration_url", "street_address")
OFFERING_KEY_FIELDS = ("start_date", "end_date", "start_time", "end_time", "rrule", "prices")
VERIFIED_SOURCES = {"provider_verified", "team_verified"}
ACTIVITY_VERIFICATION = {"team_verified": "team_verified", "provider_verified": "provider_verified", "claimed": "claimed"}


def _hhmm(v: Any) -> str | None:
    return str(v)[:5] if v not in (None, "") else None


def _price_options(rows: list[dict[str, Any]]) -> list[PriceOption]:
    return [
        PriceOption(
            type=r["price_type"], amount=float(r["amount"]), audience=r.get("audience"),
            covers=r.get("covers"), notes=r.get("notes"),
        )
        for r in sorted(rows, key=lambda r: (r["price_type"], float(r["amount"])))
    ]


def _location(rec: dict[str, Any], coords: tuple[float, float] | None, fallback_state: str | None = None) -> Location:
    address = ", ".join(x for x in (rec.get("location_name"), rec.get("street_address")) if x) or None
    return Location(
        address=address, city=rec.get("city") or "", state=rec.get("state") or fallback_state or "",
        postal_code=rec.get("zip"),
        latitude=coords[0] if coords else None, longitude=coords[1] if coords else None,
    )


def session_from_offering(o: dict[str, Any], program: dict[str, Any], api_base: str, today: date | None = None) -> Session:
    today = today or date.today()
    start_t, end_t = activities.offering_times(o)
    upcoming = activities.meeting_dates(o, after=today)
    full_term = activities.term_price(program, o)
    differs_location = bool(o.get("city") or o.get("street_address") or o.get("location_name"))
    differs_ages = o.get("age_min") is not None or o.get("age_max") is not None
    availability = o.get("availability") or "unknown"
    return Session(
        id=o["id"],
        program_id=program["id"],
        name=o.get("name"),
        start_date=parse_date(o.get("start_date")),
        end_date=parse_date(o.get("end_date")),
        price=full_term,
        availability=availability if availability in AVAILABILITY else "unknown",
        calendar_url=f"{api_base}/sessions/{o['id']}.ics",
        term=o.get("term_name"),
        skill_level=o.get("skill_level"),
        ages=AgeRange(min=o.get("age_min"), max=o.get("age_max")) if differs_ages else None,
        location=_location(o, activities.coords_for(program, o), program.get("state")) if differs_location else None,
        schedule=Schedule(
            days_of_week=activities.offering_days(o),
            start_time=_hhmm(o.get("start_time")), end_time=_hhmm(o.get("end_time")),
            timezone=o.get("timezone") or "America/New_York",
            rrule=o.get("rrule"),
            exdates=[parse_date(d) for d in o.get("exdates") or []],
            meeting_count=o.get("class_count"),  # only when the provider states it
            next_meeting=upcoming[0] if upcoming else None,
            summary=activities.schedule_summary(o),
        ) if (o.get("rrule") or start_t or end_t) else None,
        prices=_price_options(o.get("prices") or []),
        enrollment=EnrollmentWindow(
            opens=parse_date(o.get("enrollment_opens")), closes=parse_date(o.get("enrollment_closes")),
            status=activities.enrollment_status(o, today),
        ),
        drop_in_allowed=o.get("drop_in_allowed"),
    )


def program_from_activity(
    p: dict[str, Any],
    *,
    api_base: str,
    field_sources: list[dict[str, Any]] | None = None,
    include_sessions: bool = False,
    include_policies: bool = False,
) -> Program:
    offerings = p.get("offerings") or []
    sources = field_sources or []
    program_level = [s for s in sources if not s.get("offering_id")]
    verified = sorted({s["field_name"] for s in program_level if s["source_type"] in VERIFIED_SOURCES})
    unverified = sorted({s["field_name"] for s in program_level if s["source_type"] not in VERIFIED_SOURCES} - set(verified))
    missing = [f for f in ACTIVITY_KEY_FIELDS if p.get(f) in (None, "", [])]
    if not offerings:
        missing.append("schedule")
    elif any(all(o.get(f) in (None, "", []) for o in offerings) for f in OFFERING_KEY_FIELDS):
        missing += [f"schedule.{f}" for f in OFFERING_KEY_FIELDS if all(o.get(f) in (None, "", []) for o in offerings)]
    per_class = [x for x in (activities.per_class_price(p, o) for o in offerings or [None]) if x is not None]
    terms = [x for x in (activities.term_price(p, o) for o in offerings or [None]) if x is not None]
    frontend = get_settings().frontend_url.rstrip("/")
    return Program(
        id=p["id"],
        kind=p["kind"],
        name=p["name"],
        description=p.get("description"),
        categories=list(p.get("categories") or []),
        activities=list(p.get("activities") or []),
        ages=AgeRange(min=p.get("age_min"), max=p.get("age_max"), grade_min=p.get("grade_min"), grade_max=p.get("grade_max")),
        location=_location(p, activities.coords_for(p)),
        distance_miles=p.get("distance_miles"),
        provider=Provider(
            name=p.get("provider_name"), website=p.get("provider_website"),
            email=p.get("provider_email"), phone=p.get("provider_phone"),
        ),
        price=Price(
            min=min(terms) if terms else None, max=max(terms) if terms else None,
            unit="term" if terms else None, per_class=min(per_class) if per_class else None,
            financial_aid=bool(p.get("financial_aid")), options=_price_options(p.get("prices") or []),
        ),
        logistics=Logistics(),
        policies=Policies() if include_policies else None,
        verification=Verification(
            status=ACTIVITY_VERIFICATION.get(p.get("verification_status") or "", "unverified"),
            last_updated=p.get("last_updated_date") or p.get("updated_at"),
            fields_verified=verified, fields_unverified=unverified, fields_missing=missing,
        ),
        registration_url=p.get("registration_url"),
        url=f"{frontend}/activities/{p['id']}",
        sessions=[session_from_offering(o, p, api_base) for o in offerings] if include_sessions else None,
        match_reasons=list(p.get("match_reasons") or []),
        skill_levels=list(p.get("skill_levels") or []),
        trial_available=p.get("trial_available"),
        trial_notes=p.get("trial_notes"),
        membership_required=p.get("membership_required"),
    )


def _find_activity_sessions(
    *,
    near: str,
    api_base: str,
    radius_miles: float,
    age: int | None,
    categories: list[str] | None,
    starts_on_or_after: date | None,
    ends_on_or_before: date | None,
    open_only: bool,
) -> list[tuple[Session, Program]]:
    rows = activities.search_activities(get_supabase(), activities.ActivityQuery(
        location=near, radius_miles=radius_miles, age=age, interests=categories,
        starts_on_or_after=starts_on_or_after, include_full=not open_only,
    ), limit=500)
    out = []
    for p in rows:
        program = program_from_activity(p, api_base=api_base)
        for o in p["offerings"]:
            end = parse_date(o.get("end_date"))
            if ends_on_or_before and (end is None or end > ends_on_or_before):
                continue
            if starts_on_or_after and not o.get("start_date"):
                continue
            out.append((session_from_offering(o, p, api_base), program))
    return out
