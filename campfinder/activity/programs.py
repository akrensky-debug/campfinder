"""
Year-round programs: load classes, lessons and leagues with their offerings and prices,
and search them by age, interest, day and time window, distance, price and term.

Like camp search, this fetches the active catalogue and filters in Python, which is
right at pilot scale (hundreds of offerings). Each result carries a 0-1 match score
and plain-language reasons, so the agent can say why something fits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time, timedelta
from typing import Any

from campfinder.activity.schedule import (
    TimeWindow, describe, fmt_time, normalize_days, occurrences, parse_date, parse_time, rrule_days,
)
from campfinder.services.geo import geocode_location, haversine_miles

ACTIVITY_KINDS = ("class", "lesson", "league", "after_school", "event")

# Town centres for places outside the shared city table, used only to estimate distance
# when a program's own coordinates are unknown (geo_precision 'city').
EXTRA_TOWNS: dict[tuple[str, str], tuple[float, float]] = {
    ("east providence", "RI"): (41.8137, -71.3701),
    ("north providence", "RI"): (41.8501, -71.4662),
    ("johnston", "RI"): (41.8218, -71.5065),
    ("lincoln", "RI"): (41.9210, -71.4351),
    ("smithfield", "RI"): (41.9220, -71.5495),
    ("central falls", "RI"): (41.8907, -71.3923),
    ("seekonk", "MA"): (41.8084, -71.3370),
}

# What parents type -> words that appear in program names, categories and activities.
INTEREST_SYNONYMS: dict[str, list[str]] = {
    "swim": ["swim", "aquatic", "water safety", "pool"],
    "swimming": ["swim", "aquatic", "water safety", "pool"],
    "soccer": ["soccer", "futbol"],
    "art": ["art", "paint", "draw", "craft", "ceramic", "pottery"],
    "arts": ["art", "paint", "draw", "craft", "ceramic", "pottery"],
    "music": ["music", "piano", "guitar", "violin", "drum", "voice", "singing", "choir"],
    "dance": ["dance", "ballet", "hip hop", "tap", "jazz"],
    "martial arts": ["martial", "karate", "taekwondo", "tae kwon do", "judo", "jiu", "kung fu"],
    "stem": ["stem", "science", "coding", "robot", "engineering", "math", "lego"],
    "coding": ["coding", "programming", "computer", "robot"],
    "gymnastics": ["gymnastic", "tumbling", "acro"],
    "skating": ["skating", "skate"],
}


@dataclass
class ActivityQuery:
    location: str
    radius_miles: float = 15.0
    age: int | None = None
    kinds: list[str] | None = None
    interests: list[str] | None = None
    window: TimeWindow = field(default_factory=TimeWindow)
    max_price_per_class: float | None = None
    max_price_total: float | None = None
    starts_on_or_after: date | None = None
    starts_before: date | None = None
    term: str | None = None
    skill_level: str | None = None
    include_full: bool = False
    today: date = field(default_factory=date.today)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_catalog(client: Any, program_ids: list[str] | None = None, kinds: list[str] | None = None) -> list[dict[str, Any]]:
    """Active programs with `offerings` (each with `prices`) and program-level `prices` attached."""
    query = client.table("programs").select("*").eq("is_active", True)
    if program_ids:
        query = query.in_("id", program_ids)
    if kinds:
        query = query.in_("kind", kinds)
    programs = query.execute().data or []
    if not programs:
        return []
    ids = [p["id"] for p in programs]
    offerings = client.table("program_offerings").select("*").in_("program_id", ids).execute().data or []
    prices = client.table("program_prices").select("*").in_("program_id", ids).execute().data or []

    by_offering: dict[str, list[dict[str, Any]]] = {}
    program_prices: dict[str, list[dict[str, Any]]] = {}
    for pr in prices:
        if pr.get("offering_id"):
            by_offering.setdefault(pr["offering_id"], []).append(pr)
        else:
            program_prices.setdefault(pr["program_id"], []).append(pr)
    by_program: dict[str, list[dict[str, Any]]] = {}
    for o in offerings:
        by_program.setdefault(o["program_id"], []).append({**o, "prices": by_offering.get(o["id"], [])})
    for p in programs:
        p["offerings"] = by_program.get(p["id"], [])
        p["prices"] = program_prices.get(p["id"], [])
    return programs


def load_field_sources(client: Any, program_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not program_ids:
        return {}
    rows = client.table("program_field_sources").select("*").in_("program_id", program_ids).execute().data or []
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["program_id"], []).append(r)
    return out


# ---------------------------------------------------------------------------
# Derived facts about an offering
# ---------------------------------------------------------------------------

def town_coords(city: str | None, state: str | None) -> tuple[float, float] | None:
    if not city or not state:
        return None
    return geocode_location(f"{city}, {state}") or EXTRA_TOWNS.get((city.strip().lower(), state.strip().upper()))


def coords_for(program: dict[str, Any], offering: dict[str, Any] | None = None) -> tuple[float, float] | None:
    for rec in (offering or {}, program):
        if rec.get("latitude") is not None and rec.get("longitude") is not None:
            return float(rec["latitude"]), float(rec["longitude"])
        if rec.get("city"):
            c = town_coords(rec.get("city"), rec.get("state") or program.get("state"))
            if c:
                return c
    return None


def ages_for(program: dict[str, Any], offering: dict[str, Any] | None = None) -> tuple[int | None, int | None]:
    o = offering or {}
    lo = o.get("age_min") if o.get("age_min") is not None else program.get("age_min")
    hi = o.get("age_max") if o.get("age_max") is not None else program.get("age_max")
    return lo, hi


def offering_days(o: dict[str, Any]) -> list[str]:
    return rrule_days(o.get("rrule"))


def offering_times(o: dict[str, Any]) -> tuple[time | None, time | None]:
    return parse_time(o.get("start_time")), parse_time(o.get("end_time"))


def schedule_summary(o: dict[str, Any]) -> str | None:
    start, end = offering_times(o)
    text = describe(offering_days(o), start, end)
    return text or None


def meeting_dates(o: dict[str, Any], *, after: date | None = None) -> list[date]:
    if not o.get("rrule"):
        return []
    return occurrences(
        parse_date(o.get("start_date")), parse_date(o.get("end_date")), o.get("rrule"),
        o.get("exdates") or [], window_start=after,
    )


ONGOING_HORIZON_WEEKS = 12


def upcoming_meetings(o: dict[str, Any], today: date, horizon_weeks: int = ONGOING_HORIZON_WEEKS) -> tuple[list[date], bool]:
    """Meetings from today on, and whether the class is ongoing (weekly, no published term).

    An ongoing class ("Ongoing - no end date") is expanded over the next `horizon_weeks`."""
    if not o.get("rrule"):
        return [], False
    start, end = parse_date(o.get("start_date")), parse_date(o.get("end_date"))
    if start is None:
        horizon = today + timedelta(weeks=horizon_weeks)
        return occurrences(today, horizon, o["rrule"], o.get("exdates") or []), True
    return occurrences(start, end or start, o["rrule"], o.get("exdates") or [], window_start=today), False


def all_prices(program: dict[str, Any], offering: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return list((offering or {}).get("prices") or []) + list(program.get("prices") or [])


def per_class_price(program: dict[str, Any], offering: dict[str, Any] | None = None) -> float | None:
    """Lowest price of one class: a stated per-class/drop-in price, or full term divided by a
    published class count. Never estimated from the calendar: holidays may not be published."""
    candidates = []
    for pr in all_prices(program, offering):
        amount = float(pr["amount"])
        if pr["price_type"] in ("per_class", "drop_in"):
            candidates.append(amount)
        elif pr["price_type"] == "full_term" and (offering or {}).get("class_count"):
            candidates.append(round(amount / offering["class_count"], 2))  # type: ignore[index]
    return min(candidates) if candidates else None


def term_price(program: dict[str, Any], offering: dict[str, Any] | None = None) -> float | None:
    full = [float(p["amount"]) for p in all_prices(program, offering) if p["price_type"] == "full_term"]
    return min(full) if full else None


def enrollment_status(o: dict[str, Any], today: date) -> str:
    opens, closes = parse_date(o.get("enrollment_opens")), parse_date(o.get("enrollment_closes"))
    if opens is None and closes is None:
        return "unknown"
    if opens and today < opens:
        return "upcoming"
    if closes and today > closes:
        return "closed"
    return "open"


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def _interest_terms(interests: list[str] | None) -> list[list[str]]:
    """Each requested interest becomes a group of words; a program matches a group if any word appears."""
    groups = []
    for raw in interests or []:
        key = raw.strip().lower()
        if key:
            groups.append(INTEREST_SYNONYMS.get(key, [key.rstrip("s") if len(key) > 4 else key]))
    return groups


def _interest_match(program: dict[str, Any], groups: list[list[str]]) -> list[str]:
    """Which requested interests the program matches (by their first word)."""
    haystack = " ".join([
        program.get("name") or "", program.get("description") or "",
        " ".join(program.get("categories") or []), " ".join(program.get("activities") or []),
    ]).lower()
    return [g[0] for g in groups if any(word in haystack for word in g)]


def _offering_filter(program: dict[str, Any], o: dict[str, Any], q: ActivityQuery) -> tuple[bool, str | None]:
    lo, hi = ages_for(program, o)
    if q.age is not None and ((lo is not None and q.age < lo) or (hi is not None and q.age > hi)):
        return False, "age"
    end = parse_date(o.get("end_date"))
    if end and end < q.today:
        return False, "ended"
    start = parse_date(o.get("start_date"))
    if q.starts_on_or_after and start and start < q.starts_on_or_after:
        return False, "starts too early"
    if q.starts_before and start and start >= q.starts_before:
        return False, "starts too late"
    if q.term and q.term.lower() not in (o.get("term_name") or "").lower():
        return False, "term"
    if q.skill_level and q.skill_level.lower() not in (o.get("skill_level") or o.get("name") or "").lower():
        return False, "level"
    if not q.include_full and o.get("availability") == "full":
        return False, "full"
    start_t, end_t = offering_times(o)
    fits, _ = q.window.check(offering_days(o), start_t, end_t)
    if not fits:
        return False, "schedule"
    if q.max_price_per_class is not None:
        pc = per_class_price(program, o)
        if pc is not None and pc > q.max_price_per_class:
            return False, "price"
    if q.max_price_total is not None:
        tp = term_price(program, o)
        if tp is not None and tp > q.max_price_total:
            return False, "price"
    return True, None


def _needs_offering(q: ActivityQuery) -> bool:
    """Filters that can only be answered by a published schedule."""
    return bool(not q.window.is_open or q.starts_on_or_after or q.starts_before or q.term or q.skill_level)


def search_activities(client: Any, q: ActivityQuery, limit: int = 10) -> list[dict[str, Any]]:
    origin = geocode_location(q.location) or town_coords(*(q.location.split(",") + [""])[:2])
    if origin is None:
        return []
    kinds = [k for k in (q.kinds or []) if k in ACTIVITY_KINDS] or None
    groups = _interest_terms(q.interests)
    results = []
    for p in load_catalog(client, kinds=kinds):
        matched_interests = _interest_match(p, groups)
        if groups and not matched_interests:
            continue
        lo, hi = ages_for(p)
        offerings = []
        for o in p["offerings"]:
            ok, _ = _offering_filter(p, o, q)
            if ok:
                offerings.append(o)
        if p["offerings"] and not offerings:
            continue  # a published schedule exists and none of it fits
        if not p["offerings"]:
            if _needs_offering(q):
                continue
            if q.age is not None and ((lo is not None and q.age < lo) or (hi is not None and q.age > hi)):
                continue
        # Distance: the nearest fitting location.
        distances = [
            haversine_miles(*origin, *c) for c in
            ([coords_for(p, o) for o in offerings] if offerings else [coords_for(p)]) if c
        ]
        distance = min(distances) if distances else None
        if distance is not None and distance > q.radius_miles:
            continue
        offerings.sort(key=lambda o: (str(o.get("start_date") or "9999"), str(o.get("start_time") or "")))
        score, reasons = score_activity(p, offerings, q, distance, matched_interests)
        results.append({
            **p,
            "offerings": offerings,
            "distance_miles": round(distance, 1) if distance is not None else None,
            "match_score": round(score, 4),
            "match_reasons": reasons,
        })
    results.sort(key=lambda r: (-r["match_score"], r["distance_miles"] if r["distance_miles"] is not None else 999))
    return results[:limit]


def score_activity(
    p: dict[str, Any],
    offerings: list[dict[str, Any]],
    q: ActivityQuery,
    distance: float | None,
    matched_interests: list[str],
) -> tuple[float, list[str]]:
    """0-1 score and the reasons a parent would care about, most important first."""
    score, reasons = 0.0, []

    lo, hi = ages_for(p, offerings[0] if offerings else None)
    if q.age is not None:
        if lo is not None or hi is not None:
            score += 0.2
            reasons.append(f"Ages {lo if lo is not None else '?'}–{hi if hi is not None else '?'} fits a {q.age}-year-old")
        else:
            score += 0.1
            reasons.append("Ages not published; check with the provider")
    else:
        score += 0.1

    if matched_interests:
        score += 0.25
        reasons.append(f"Matches {', '.join(matched_interests)}")
    elif not q.interests:
        score += 0.15

    if offerings:
        score += 0.2
        first = offerings[0]
        summary = schedule_summary(first)
        if summary:
            extra = f" (+{len(offerings) - 1} more times)" if len(offerings) > 1 else ""
            fit = f" (fits {q.window.describe()})" if not q.window.is_open else ""
            reasons.append(f"{summary}{fit}{extra}")
    elif p["offerings"] == []:
        score += 0.05
        reasons.append("Schedule not published yet")

    if distance is not None:
        score += 0.15 * max(0.0, 1 - distance / max(q.radius_miles, 1))
        reasons.append(distance_reason(p, distance, q.location))

    pc = min((x for x in (per_class_price(p, o) for o in offerings or [None]) if x is not None), default=None)
    tp = min((x for x in (term_price(p, o) for o in offerings or [None]) if x is not None), default=None)
    if pc is not None:
        if q.max_price_per_class is None or pc <= q.max_price_per_class:
            score += 0.1
        reasons.append(f"From ${pc:,.0f} a class")
    elif tp is not None:
        if q.max_price_total is None or tp <= q.max_price_total:
            score += 0.1
        reasons.append(f"From ${tp:,.0f} a term")

    statuses = {enrollment_status(o, q.today) for o in offerings}
    if "open" in statuses:
        score += 0.05
        closes = min((parse_date(o.get("enrollment_closes")) for o in offerings
                      if enrollment_status(o, q.today) == "open" and o.get("enrollment_closes")), default=None)
        reasons.append(f"Enrollment open{f' until {closes:%b} {closes.day}' if closes else ''}")
    elif "upcoming" in statuses:
        opens = min(parse_date(o["enrollment_opens"]) for o in offerings if enrollment_status(o, q.today) == "upcoming")
        reasons.append(f"Enrollment opens {opens:%b} {opens.day}")

    if p.get("trial_available"):
        score += 0.03
        reasons.append("Trial class available")
    if p.get("verification_status") in ("team_verified", "provider_verified"):
        score += 0.02
    else:
        reasons.append("Not yet verified")
    return min(score, 1.0), reasons


def distance_reason(p: dict[str, Any], distance: float, origin: str) -> str:
    """Honest distance wording: town-level locations only support 'in town' or 'about N mi'."""
    origin_town = origin.split(",")[0].strip()
    if p.get("geo_precision") == "address" or p.get("latitude") is not None:
        return f"{distance:.1f} mi from {origin_town}"
    if distance < 1:
        return f"In {p.get('city') or origin_town}"
    return f"About {distance:.0f} mi from {origin_town} ({p.get('city')})"


def describe_window(days: list[str] | None, earliest: Any, latest: Any) -> str:
    return TimeWindow(normalize_days(days), parse_time(earliest), parse_time(latest)).describe()


__all__ = [
    "ACTIVITY_KINDS", "ActivityQuery", "load_catalog", "load_field_sources", "search_activities",
    "coords_for", "ages_for", "offering_days", "offering_times", "schedule_summary", "meeting_dates",
    "per_class_price", "term_price", "enrollment_status", "fmt_time", "describe_window",
]
