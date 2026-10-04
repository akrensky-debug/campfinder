"""
Recurring schedules: weekly patterns, time windows and conflicts.

Pure functions, no database. A class meets on an iCal RRULE ("FREQ=WEEKLY;BYDAY=TU")
between a first and last date, minus exception dates (holidays, breaks). Family
calendar entries use the same shape, so a new class can be checked against the camps,
practices and pickups already on the calendar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable

from dateutil.rrule import rrulestr

DAY_CODES = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
DAY_NAMES = {
    "MO": "Monday", "TU": "Tuesday", "WE": "Wednesday", "TH": "Thursday",
    "FR": "Friday", "SA": "Saturday", "SU": "Sunday",
}
_DAY_ALIASES = {
    "weekdays": ["MO", "TU", "WE", "TH", "FR"],
    "weekday": ["MO", "TU", "WE", "TH", "FR"],
    "weekends": ["SA", "SU"],
    "weekend": ["SA", "SU"],
}
# Named parts of the day, as parents use them. (earliest start, latest end)
TIME_OF_DAY: dict[str, tuple[time | None, time | None]] = {
    "morning": (None, time(12, 0)),
    "afternoon": (time(12, 0), time(17, 30)),
    "after_school": (time(14, 30), time(18, 30)),
    "evening": (time(17, 0), None),
}
# Recurring expansion is capped so a bad RRULE can never run away.
MAX_OCCURRENCES = 400


def normalize_days(days: Iterable[str] | None) -> list[str]:
    """'weekdays', 'Tue', 'tuesday', 'TU' -> ['TU', ...] in week order."""
    out: set[str] = set()
    for raw in days or []:
        d = raw.strip().lower()
        if d in _DAY_ALIASES:
            out.update(_DAY_ALIASES[d])
            continue
        code = d[:2].upper()
        if code in DAY_CODES:
            out.add(code)
        else:
            raise ValueError(f"Unknown day: {raw!r}")
    return [c for c in DAY_CODES if c in out]


def weekly_rrule(days: Iterable[str]) -> str:
    codes = normalize_days(days)
    if not codes:
        raise ValueError("A weekly schedule needs at least one day")
    return f"FREQ=WEEKLY;BYDAY={','.join(codes)}"


def rrule_days(rrule: str | None) -> list[str]:
    """Weekday codes an RRULE meets on (BYDAY), in week order."""
    if not rrule:
        return []
    m = re.search(r"BYDAY=([A-Z0-9,+-]+)", rrule.upper())
    if not m:
        return []
    codes = {re.sub(r"[^A-Z]", "", part) for part in m.group(1).split(",")}
    return [c for c in DAY_CODES if c in codes]


def parse_time(value: Any) -> time | None:
    """'16:00', '16:00:00', '4pm', '4:30 pm' -> time."""
    if value in (None, ""):
        return None
    if isinstance(value, time):
        return value
    s = str(value).strip().lower().replace(".", "")
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(?::\d{2})?\s*(am|pm)?", s)
    if not m:
        raise ValueError(f"Unrecognised time: {value!r}")
    hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    return time(hour, minute)


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def fmt_time(t: time | None) -> str:
    if t is None:
        return ""
    suffix = "am" if t.hour < 12 else "pm"
    hour = t.hour % 12 or 12
    return f"{hour}:{t.minute:02d}{suffix}" if t.minute else f"{hour}{suffix}"


def time_range(start: time | None, end: time | None) -> str:
    """16:00, 16:30 -> '4–4:30pm'; 11:00, 13:00 -> '11am–1pm'."""
    if not start:
        return ""
    if not end:
        return fmt_time(start)
    s, e = fmt_time(start), fmt_time(end)
    if s[-2:] == e[-2:]:
        s = s[:-2]
    return f"{s}–{e}"


def describe(days: list[str], start: time | None, end: time | None) -> str:
    """['TU','TH'], 16:00, 17:00 -> 'Tue & Thu 4–5pm'."""
    if days == list(DAY_CODES[:5]):
        day_text = "Weekdays"
    elif days:
        names = [DAY_NAMES[d][:3] for d in days]
        day_text = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " & " + names[-1]
        if len(days) == 1:
            day_text = DAY_NAMES[days[0]] + "s"
    else:
        day_text = ""
    times = time_range(start, end)
    return " ".join(p for p in (day_text, times) if p)


def occurrences(
    start: date | None,
    end: date | None,
    rrule: str | None,
    exdates: Iterable[Any] = (),
    *,
    window_start: date | None = None,
    window_end: date | None = None,
) -> list[date]:
    """Dates a schedule meets on, optionally clipped to a window.

    No RRULE means every day from start to end (an all-day camp week, a one-off event).
    """
    if start is None:
        return []
    end = end or start
    lo = max(start, window_start) if window_start else start
    hi = min(end, window_end) if window_end else end
    if hi < lo:
        return []
    skip = {parse_date(d) for d in exdates or []}
    if not rrule:
        days = [lo + timedelta(days=i) for i in range((hi - lo).days + 1)]
    else:
        rule = rrulestr(_strip_rrule_bounds(rrule), dtstart=datetime.combine(start, time()))
        days = [
            d.date() for d in rule.between(
                datetime.combine(lo, time()), datetime.combine(hi, time()), inc=True,
            )[:MAX_OCCURRENCES]
        ]
    return [d for d in days if d not in skip]


def _strip_rrule_bounds(rrule: str) -> str:
    """Drop UNTIL/COUNT: the stored start and end dates bound the series."""
    rrule = rrule.strip()
    if rrule.upper().startswith("RRULE:"):
        rrule = rrule[6:]
    parts = [p for p in rrule.split(";") if p and not p.upper().startswith(("UNTIL=", "COUNT="))]
    return ";".join(parts)


@dataclass
class TimeWindow:
    """When a family can do an activity: which days and between which times."""

    days: list[str] = field(default_factory=list)  # empty: any day
    earliest_start: time | None = None
    latest_end: time | None = None

    @classmethod
    def build(
        cls,
        days: Iterable[str] | None = None,
        earliest_start: Any = None,
        latest_end: Any = None,
        time_of_day: str | None = None,
    ) -> "TimeWindow":
        lo, hi = TIME_OF_DAY.get(time_of_day or "", (None, None))
        return cls(
            days=normalize_days(days),
            earliest_start=parse_time(earliest_start) or lo,
            latest_end=parse_time(latest_end) or hi,
        )

    @property
    def is_open(self) -> bool:
        return not self.days and self.earliest_start is None and self.latest_end is None

    def check(self, days: list[str], start: time | None, end: time | None) -> tuple[bool, str | None]:
        """Does a weekly slot fall inside the window? Returns (fits, reason it fails).

        Unknown days or times never fail a filter; the result just says they're unknown.
        """
        if self.days and days and not set(days) <= set(self.days):
            extra = [DAY_NAMES[d] for d in days if d not in self.days]
            return False, f"meets on {', '.join(extra)}"
        if self.earliest_start and start and start < self.earliest_start:
            return False, f"starts at {fmt_time(start)}, before {fmt_time(self.earliest_start)}"
        if self.latest_end and end and end > self.latest_end:
            return False, f"ends at {fmt_time(end)}, after {fmt_time(self.latest_end)}"
        return True, None

    def describe(self) -> str:
        parts = []
        if self.days:
            days = describe(self.days, None, None)
            parts.append("weekdays" if days == "Weekdays" else days)
        if self.earliest_start:
            parts.append(f"after {fmt_time(self.earliest_start)}")
        if self.latest_end:
            parts.append(f"done by {fmt_time(self.latest_end)}")
        return " ".join(parts)


@dataclass
class Slot:
    """Something that occupies a child's (or a driver's) time on given dates."""

    title: str
    dates: list[date]
    start_time: time | None = None  # None: all day
    end_time: time | None = None
    child: str | None = None
    event_id: str | None = None
    location: str | None = None

    @property
    def all_day(self) -> bool:
        return self.start_time is None

    @classmethod
    def from_event(cls, e: dict[str, Any], window_start: date | None = None, window_end: date | None = None) -> "Slot":
        """A family_events row (camp week, recurring class, pickup) as a Slot."""
        start_t, end_t = parse_time(e.get("start_time")), parse_time(e.get("end_time"))
        if start_t and not end_t:
            end_t = (datetime.combine(date.min, start_t) + timedelta(hours=1)).time()
        return cls(
            title=e.get("title") or "Calendar entry",
            dates=occurrences(
                parse_date(e.get("start_date")), parse_date(e.get("end_date")), e.get("rrule"),
                e.get("exdates") or [], window_start=window_start, window_end=window_end,
            ),
            start_time=start_t,
            end_time=end_t,
            child=e.get("child_name"),
            event_id=str(e["id"]) if e.get("id") else None,
            location=e.get("location"),
        )


@dataclass
class Conflict:
    severity: str  # 'clash' (same child, same time), 'logistics' (another child's drop-off/pickup), 'all_day'
    with_title: str
    with_child: str | None
    dates: list[date]
    detail: str
    event_id: str | None = None

    def as_dict(self, max_dates: int = 5) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "with": self.with_title,
            "with_child": self.with_child,
            "event_id": self.event_id,
            "dates": [d.isoformat() for d in self.dates[:max_dates]],
            "date_count": len(self.dates),
            "detail": self.detail,
        }


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _same_child(a: str | None, b: str | None) -> bool:
    return bool(a and b and a.strip().lower() == b.strip().lower())


def find_conflicts(new: Slot, existing: Iterable[Slot], buffer_minutes: int = 15) -> list[Conflict]:
    """Where a new commitment collides with what's already on the calendar.

    - clash: the same child (or an unnamed entry) is somewhere else at an overlapping time.
    - logistics: another child's timed commitment starts or ends within `buffer_minutes`
      of this one, so one parent can't do both drop-offs/pickups without help.
    - all_day: an all-day entry (usually a camp week) for this child on a meeting date.
    Entries for other children on all-day blocks are ignored; they don't need a driver mid-day.
    """
    new_dates = set(new.dates)
    out: list[Conflict] = []
    for other in existing:
        shared = sorted(new_dates & set(other.dates))
        if not shared:
            continue
        same = _same_child(new.child, other.child) or not new.child or not other.child
        if other.all_day or new.all_day:
            if same:
                out.append(Conflict(
                    "all_day", other.title, other.child, shared,
                    f"{other.title} is on the calendar all day on {len(shared)} of these dates",
                    other.event_id,
                ))
            continue
        a0, a1 = _minutes(new.start_time), _minutes(new.end_time or new.start_time)  # type: ignore[arg-type]
        b0, b1 = _minutes(other.start_time), _minutes(other.end_time or other.start_time)  # type: ignore[arg-type]
        if same and a0 < b1 and b0 < a1:
            out.append(Conflict(
                "clash", other.title, other.child, shared,
                f"overlaps {other.title} ({time_range(other.start_time, other.end_time)})",
                other.event_id,
            ))
        elif not same and a0 - buffer_minutes < b1 and b0 < a1 + buffer_minutes:
            out.append(Conflict(
                "logistics", other.title, other.child, shared,
                f"{other.child or 'Another child'} has {other.title} "
                f"{time_range(other.start_time, other.end_time)}; drop-off or pickup "
                f"lands within {buffer_minutes} minutes, so you may need a second driver",
                other.event_id,
            ))
    return out
