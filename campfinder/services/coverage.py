"""
Summer coverage: for every kid and every summer week, do the camps on the family calendar
cover the hours when every parent is at work, given vacations and travel?

`compute_coverage` is pure (profile, calendar, camp facts in; weeks out). `check_coverage`
loads a family and adds camp options for the weeks that are still open.
"""

from __future__ import annotations

from datetime import date, time, timedelta
from typing import Any

from campfinder.activity.schedule import parse_time
from campfinder.database import get_supabase
from campfinder.models.coverage import (
    AwayRange, CoverageGap, CoverageOption, CoverageResponse, CoverageWeek, KidCoverage, WorkBlock,
)
from campfinder.services.errors import NotFound
from campfinder.services.search import search_camps

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DEFAULT_WORKDAYS = DAYS[:5]
# Typical core camp day. Wider care hours mean the family needs extended care or a bus.
CORE_START, CORE_END = time(9, 0), time(15, 0)
OPTIONS_PER_WEEK = 3


def _day_key(value: str) -> str:
    v = value.strip()[:3].capitalize()
    if v not in DAYS:
        raise ValueError(f"Unrecognised weekday: {value!r}")
    return v


def _fmt(t: time) -> str:
    return t.strftime("%-H:%M")


def _span(a: time, b: time) -> str:
    return f"{_fmt(a)}-{_fmt(b)}"


def care_windows(work: list[WorkBlock]) -> dict[str, tuple[time, time] | None]:
    """
    Weekday -> (start, end) when every parent is at work, or None when someone is home.
    With no work schedule we assume weekdays need care, hours unknown: (None-marked) all-day.
    """
    if not work:
        return {d: (time(0, 0), time(23, 59)) if d in DEFAULT_WORKDAYS else None for d in DAYS}
    parents: dict[str, dict[str, tuple[time, time]]] = {}
    for b in work:
        start, end = parse_time(b.start), parse_time(b.end)
        if start is None or end is None or end <= start:
            raise ValueError(f"{b.parent}: work hours {b.start}-{b.end} don't make sense")
        for d in b.days:
            parents.setdefault(b.parent.strip().lower(), {})[_day_key(d)] = (start, end)
    out: dict[str, tuple[time, time] | None] = {}
    for d in DAYS:
        spans = [p.get(d) for p in parents.values()]
        if any(s is None for s in spans):
            out[d] = None  # at least one parent is free that day
            continue
        start = max(s[0] for s in spans)  # type: ignore[index]
        end = min(s[1] for s in spans)  # type: ignore[index]
        out[d] = (start, end) if start < end else None
    return out


def _weeks(start: date, end: date) -> list[tuple[date, date]]:
    cur = start - timedelta(days=start.weekday())
    out = []
    while cur <= end:
        out.append((cur, cur + timedelta(days=6)))
        cur += timedelta(weeks=1)
    return out


def _as_date(v: Any) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def _covering_events(events: list[dict[str, Any]], kid: str) -> list[dict[str, Any]]:
    """Calendar entries that look after this kid for whole days: camps and commitments, not weekly classes."""
    out = []
    for e in events:
        if e.get("rrule") or e.get("kind") in ("activity", "reminder"):
            continue
        if not (e.get("camp_id") or e.get("kind") in ("camp", "commitment")):
            continue
        who = (e.get("child_name") or "").strip().lower()
        if who and who != kid.lower():
            continue
        out.append(e)
    return out


def _day_cover(
    day: date, window: tuple[time, time], events: list[dict[str, Any]], camps: dict[str, dict[str, Any]],
    hours_known: bool,
) -> tuple[str, str | None, str | None]:
    """
    One needed day -> (outcome, event title, detail).
    outcome: 'covered' | 'check_hours' | 'partial' | 'gap'.
    """
    todays = [e for e in events if _as_date(e["start_date"]) <= day <= _as_date(e["end_date"])]
    if not todays:
        return "gap", None, "all day"
    best: tuple[str, str | None, str | None] | None = None
    for e in todays:
        camp = camps.get(str(e.get("camp_id"))) if e.get("camp_id") else None
        s, en = parse_time(e.get("start_time")), parse_time(e.get("end_time"))
        if camp and camp.get("camp_type") == "sleepaway":
            return "covered", e["title"], None
        if s and en and hours_known:
            if s <= window[0] and en >= window[1]:
                return "covered", e["title"], None
            spans = []
            if s > window[0]:
                spans.append(_span(window[0], s))
            if en < window[1]:
                spans.append(_span(en, window[1]))
            best = best or ("partial", e["title"], ", ".join(spans))
            continue
        if camp is not None or e.get("kind") == "camp":
            if not hours_known:
                return "covered", e["title"], None
            needs_extra = window[0] < CORE_START or window[1] > CORE_END
            if not needs_extra:
                return "covered", e["title"], None
            if camp and camp.get("extended_care") is False:
                best = best or ("partial", e["title"], f"outside camp hours ({_span(window[0], window[1])} needed; no extended care)")
                continue
            note = "offers extended care" if camp and camp.get("extended_care") else "extended care not listed"
            best = ("check_hours", e["title"], f"{e['title']}: confirm it covers {_span(window[0], window[1])} ({note})")
            continue
        # A commitment without times (e.g. "Maya at Grandma's") covers the day.
        return "covered", e["title"], None
    return best or ("gap", None, "all day")


def compute_coverage(
    profile: dict[str, Any], events: list[dict[str, Any]], camps: dict[str, dict[str, Any]],
) -> CoverageResponse:
    """Week-by-week coverage for every kid. `camps` maps camp_id -> camp row (camp_type, extended_care)."""
    if not profile.get("summer_start") or not profile.get("summer_end"):
        raise ValueError("Set the summer start and end dates first.")
    start, end = _as_date(profile["summer_start"]), _as_date(profile["summer_end"])
    work = [WorkBlock.model_validate(w) for w in profile.get("work_schedule") or []]
    away = [AwayRange.model_validate(a) for a in profile.get("away") or []]
    windows = care_windows(work)
    hours_known = bool(work)
    kids = [k for k in profile.get("kids") or [] if k.get("name")]
    notes: list[str] = []
    if not hours_known:
        notes.append("No work schedule saved, so every weekday counts as needing care and hours aren't checked.")
    if not kids:
        raise ValueError("Add the kids to the family profile first.")

    result = []
    for kid in kids:
        name = kid["name"]
        cover_events = _covering_events(events, name)
        weeks = []
        for ws, we in _weeks(start, end):
            needed = covered = 0
            covered_by: list[str] = []
            away_labels: list[str] = []
            gaps: list[CoverageGap] = []
            check: list[str] = []
            partial = False
            for i in range(7):
                day = ws + timedelta(days=i)
                if day < start or day > end:
                    continue
                window = windows[DAYS[day.weekday()]]
                if window is None:
                    continue
                trip = next((a for a in away if a.start_date <= day <= a.end_date
                             and (not a.child_name or a.child_name.lower() == name.lower())), None)
                if trip:
                    if trip.label not in away_labels:
                        away_labels.append(trip.label)
                    continue
                needed += 1
                outcome, title, detail = _day_cover(day, window, cover_events, camps, hours_known)
                if title and title not in covered_by:
                    covered_by.append(title)
                if outcome == "covered":
                    covered += 1
                elif outcome == "check_hours":
                    covered += 1
                    if detail and detail not in check:
                        check.append(detail)
                elif outcome == "partial":
                    partial = True
                    gaps.append(CoverageGap(day=day, uncovered=detail or ""))
                else:
                    gaps.append(CoverageGap(day=day, uncovered="all day"))
            if needed == 0:
                status = "away" if away_labels else "not_needed"
            elif covered == needed and not check:
                status = "covered"
            elif covered == needed:
                status = "check_hours"
            elif covered == 0 and not partial:
                status = "open"
            else:
                status = "partial"
            weeks.append(CoverageWeek(
                week_of=ws, week_end=we, status=status, days_needed=needed, days_covered=covered,
                covered_by=covered_by, away=away_labels, gaps=gaps, check_hours=check,
            ))
        result.append(KidCoverage(
            name=name, age=kid.get("age"), weeks=weeks,
            weeks_open=sum(w.status == "open" for w in weeks),
            weeks_partial=sum(w.status == "partial" for w in weeks),
            weeks_covered=sum(w.status in ("covered", "check_hours") for w in weeks),
        ))
    return CoverageResponse(
        summer_start=start, summer_end=end, notes=notes,
        care_hours={d: _span(*w) for d, w in windows.items() if w and hours_known},
        kids=result,
    )


def week_options(
    camps: list[dict[str, Any]], week_of: date, care: tuple[time, time] | None, limit: int = OPTIONS_PER_WEEK,
) -> list[CoverageOption]:
    """
    Camps (from search, nearest/best first) with a session in this week. When this season's
    dates aren't posted, a session in the same week last season is offered and marked as such.
    Extended care is preferred when the care hours run past a typical camp day.
    """
    week_end = week_of + timedelta(days=4)
    last_year = (week_of - timedelta(weeks=52), week_end - timedelta(weeks=52))
    wants_extra = bool(care) and (care[0] < CORE_START or care[1] > CORE_END)  # type: ignore[index]
    found: list[tuple[int, int, CoverageOption]] = []
    for rank, c in enumerate(camps):
        if c.get("camp_type") == "sleepaway":
            continue  # options fill day-care gaps; sleepaway weeks are chosen as anchors, not fillers
        hit, old = None, None
        for s in c.get("sessions") or []:
            s0, s1 = _as_date(s["start_date"]), _as_date(s["end_date"])
            if s0 <= week_end and s1 >= week_of and (s1 - s0).days <= 13:
                hit = s
                break
            if old is None and s0 <= last_year[1] and s1 >= last_year[0] and (s1 - s0).days <= 13:
                old = s
        s = hit or old
        if not s:
            continue
        opt = CoverageOption(
            camp_id=c["id"], name=c["name"], city=c["city"], distance_miles=c.get("distance_miles"),
            extended_care=c.get("extended_care"), transportation=c.get("transportation"),
            price_per_week=c.get("price_per_week"), session_id=s["id"], session_name=s.get("name"),
            start_date=_as_date(s["start_date"]), end_date=_as_date(s["end_date"]), last_season=hit is None,
        )
        found.append((0 if (not wants_extra or c.get("extended_care")) else 1, rank, opt))
    found.sort(key=lambda t: (t[0], t[2].last_season, t[1]))
    return [o for _, _, o in found[:limit]]


async def check_coverage(family_id: str, with_options: bool = True) -> CoverageResponse:
    """Load a family's profile and calendar, compute coverage, and add options for open weeks."""
    client = get_supabase()
    rows = client.table("families").select("profile").eq("id", family_id).execute().data
    if not rows:
        raise NotFound("Family not found")
    profile = rows[0].get("profile") or {}
    events = client.table("family_events").select("*").eq("family_id", family_id).execute().data or []
    camp_ids = list({str(e["camp_id"]) for e in events if e.get("camp_id")})
    camps = {
        str(c["id"]): c for c in (
            client.table("camps").select("id,camp_type,extended_care").in_("id", camp_ids).execute().data or []
        )
    } if camp_ids else {}
    result = compute_coverage(profile, events, camps)

    home = profile.get("home_location")
    if not with_options:
        return result
    if not home:
        result.notes.append("Add a home town to get camp suggestions for open weeks.")
        return result
    windows = care_windows([WorkBlock.model_validate(w) for w in profile.get("work_schedule") or []])
    hours_known = bool(profile.get("work_schedule"))
    for kid in result.kids:
        open_weeks = [w for w in kid.weeks if w.status in ("open", "partial")]
        if not open_weeks:
            continue
        nearby = await search_camps(client, location=home, age=kid.age, limit=200, sort="best_match")
        for w in open_weeks:
            care = None
            if hours_known:
                spans = [windows[DAYS[g.day.weekday()]] for g in w.gaps]
                spans = [s for s in spans if s]
                if spans:
                    care = (min(s[0] for s in spans), max(s[1] for s in spans))
            w.options = week_options(nearby, w.week_of, care)
    if any(o.last_season for k in result.kids for w in k.weeks for o in w.options):
        result.notes.append("Some suggestions show last season's dates; this season's aren't posted yet.")
    return result
