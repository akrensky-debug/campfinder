"""A family's week at a glance: every kid's classes, practices, camps and pickups, day by day."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from campfinder.activity.schedule import Slot, parse_time, time_range

DAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def build_week(events: list[dict[str, Any]], week_of: date | None = None) -> dict[str, Any]:
    """Expand calendar entries (one-off, all-day ranges and recurring) into a Mon-Sun grid."""
    start = monday_of(week_of or date.today())
    end = start + timedelta(days=6)
    days: list[dict[str, Any]] = [
        {"date": (start + timedelta(days=i)).isoformat(), "label": DAY_LABELS[i], "items": []} for i in range(7)
    ]
    kids: list[str] = []
    for e in events:
        slot = Slot.from_event(e, window_start=start, window_end=end)
        for d in slot.dates:
            days[(d - start).days]["items"].append({
                "event_id": slot.event_id,
                "title": slot.title,
                "child_name": slot.child,
                "kind": e.get("kind") or ("camp" if e.get("camp_id") else None),
                "all_day": slot.all_day,
                "start_time": slot.start_time.strftime("%H:%M") if slot.start_time else None,
                "end_time": slot.end_time.strftime("%H:%M") if slot.end_time else None,
                "time_label": time_range(slot.start_time, slot.end_time) if slot.start_time else "All day",
                "location": slot.location,
            })
            if slot.child and slot.child not in kids:
                kids.append(slot.child)
    for day in days:
        day["items"].sort(key=lambda i: (not i["all_day"], i["start_time"] or ""))
    return {"week_of": start.isoformat(), "week_end": end.isoformat(), "kids": kids, "days": days}


def compact_event(e: dict[str, Any]) -> dict[str, Any]:
    """Calendar entry as the model sees it, including times and recurrence when present."""
    keys = ("id", "title", "kind", "start_date", "end_date", "start_time", "end_time", "rrule",
            "child_name", "location", "camp_id", "session_id", "program_id", "offering_id", "notes")
    out = {k: e[k] for k in keys if e.get(k) not in (None, "", [])}
    for k in ("start_time", "end_time"):
        if k in out:
            t = parse_time(out[k])
            out[k] = t.strftime("%H:%M") if t else out[k]
    return out
