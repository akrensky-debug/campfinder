"""iCalendar (.ics) feeds: the family calendar, single-session invites, member feeds."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from campfinder.activity import ics as ics_extended


def ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics_fold(line: str) -> str:
    """Fold lines longer than 75 octets, per RFC 5545."""
    out, current = [], b""
    for ch in line:
        enc = ch.encode()
        if len(current) + len(enc) > (75 if not out else 74):
            out.append(current.decode())
            current = b""
        current += enc
    out.append(current.decode())
    return "\r\n ".join(out)


def build_ics(events: list[dict[str, Any]]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CampFinder//Family Calendar//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Family plans (CampFinder)",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
    ]
    lines += ics_extended.vtimezone_lines(events)
    for e in events:
        if ics_extended.needs_extended_ics(e):  # recurring/timed classes and reminders
            lines += ics_extended.vevent_lines(e, stamp)
            continue
        start = date.fromisoformat(str(e["start_date"]))
        end = date.fromisoformat(str(e["end_date"])) + timedelta(days=1)  # DTEND is exclusive
        lines += [
            "BEGIN:VEVENT",
            f"UID:{e['id']}@campfinder",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
            f"DTEND;VALUE=DATE:{end:%Y%m%d}",
            f"SUMMARY:{ics_escape(e['title'])}",
        ]
        if e.get("notes"):
            lines.append(f"DESCRIPTION:{ics_escape(e['notes'])}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(ics_fold(line) for line in lines) + "\r\n"
