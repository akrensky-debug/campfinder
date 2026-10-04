"""
iCalendar output for recurring and timed entries: weekly classes, practices, pickups and
enrollment reminders. All-day camp weeks keep using the original builder in
routers/agent.py, which calls into here for entries that have times or alarms.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from campfinder.activity.schedule import occurrences, parse_date, parse_time

DEFAULT_TZ = "America/New_York"

# Eastern time, current US rules (since 2007). Google, Apple and Outlook accept a TZID
# without a VTIMEZONE, but RFC 5545 asks for one.
VTIMEZONE_NEW_YORK = [
    "BEGIN:VTIMEZONE",
    "TZID:America/New_York",
    "BEGIN:DAYLIGHT",
    "TZOFFSETFROM:-0500",
    "TZOFFSETTO:-0400",
    "TZNAME:EDT",
    "DTSTART:19700308T020000",
    "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU",
    "END:DAYLIGHT",
    "BEGIN:STANDARD",
    "TZOFFSETFROM:-0400",
    "TZOFFSETTO:-0500",
    "TZNAME:EST",
    "DTSTART:19701101T020000",
    "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU",
    "END:STANDARD",
    "END:VTIMEZONE",
]


def needs_extended_ics(e: dict[str, Any]) -> bool:
    """True for entries the original all-day builder can't express."""
    return bool(e.get("start_time") or e.get("rrule") or e.get("alarm_minutes_before") is not None)


def vtimezone_lines(events: list[dict[str, Any]]) -> list[str]:
    zones = {e.get("timezone") or DEFAULT_TZ for e in events if e.get("start_time")}
    return VTIMEZONE_NEW_YORK if DEFAULT_TZ in zones else []


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _rrule_with_until(rrule: str, last_day: date, tz: ZoneInfo, timed: bool) -> str:
    parts = [p for p in rrule.removeprefix("RRULE:").split(";") if p and not p.upper().startswith(("UNTIL=", "COUNT="))]
    if timed:
        # With a TZID start, UNTIL must be UTC (RFC 5545 3.3.10).
        until = datetime.combine(last_day, time(23, 59, 59), tz).astimezone(timezone.utc)
        parts.append(f"UNTIL={until:%Y%m%dT%H%M%SZ}")
    else:
        parts.append(f"UNTIL={last_day:%Y%m%d}")
    return "RRULE:" + ";".join(parts)


def vevent_lines(e: dict[str, Any], stamp: str) -> list[str]:
    """One VEVENT for a family_events row with times, a recurrence and/or an alarm."""
    tz_name = e.get("timezone") or DEFAULT_TZ
    tz = ZoneInfo(tz_name)
    first, last = parse_date(e["start_date"]), parse_date(e["end_date"])
    start_t, end_t = parse_time(e.get("start_time")), parse_time(e.get("end_time"))
    rrule = e.get("rrule")
    exdates = [parse_date(d) for d in e.get("exdates") or []]

    if rrule:
        # DTSTART must itself be an occurrence, so anchor it on the first meeting.
        meetings = occurrences(first, last, rrule, exdates)
        if meetings:
            first = meetings[0]

    lines = ["BEGIN:VEVENT", f"UID:{e['id']}@campfinder", f"DTSTAMP:{stamp}"]
    if start_t:
        end_t = end_t or (datetime.combine(first, start_t) + timedelta(hours=1)).time()
        lines.append(f"DTSTART;TZID={tz_name}:{datetime.combine(first, start_t):%Y%m%dT%H%M%S}")
        lines.append(f"DTEND;TZID={tz_name}:{datetime.combine(first, end_t):%Y%m%dT%H%M%S}")
    else:
        lines.append(f"DTSTART;VALUE=DATE:{first:%Y%m%d}")
        span = 1 if rrule else (last - first).days + 1
        lines.append(f"DTEND;VALUE=DATE:{first + timedelta(days=span):%Y%m%d}")
    if rrule:
        lines.append(_rrule_with_until(rrule, last, tz, timed=bool(start_t)))
        for d in exdates:
            if start_t:
                lines.append(f"EXDATE;TZID={tz_name}:{datetime.combine(d, start_t):%Y%m%dT%H%M%S}")
            else:
                lines.append(f"EXDATE;VALUE=DATE:{d:%Y%m%d}")
    lines.append(f"SUMMARY:{_escape(e['title'])}")
    if e.get("location"):
        lines.append(f"LOCATION:{_escape(e['location'])}")
    if e.get("notes"):
        lines.append(f"DESCRIPTION:{_escape(e['notes'])}")
    if e.get("alarm_minutes_before") is not None:
        lines += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_escape(e['title'])}",
            f"TRIGGER:-PT{int(e['alarm_minutes_before'])}M",
            "END:VALARM",
        ]
    lines.append("END:VEVENT")
    return lines
