"""
Reminder emails: each person's upcoming jobs, and a weekly summary for parents.

Run once a day (e.g. a Railway cron at 7am Eastern) with
    python -m campfinder.household.reminders [--dry-run] [--weekly] [--date YYYY-MM-DD]
or POST /api/v1/internal/reminders/run with the X-Cron-Secret header.

  daily       today's jobs, sent the morning of
  day_before  tomorrow's jobs, sent the day before (the default)
  weekly      Sundays (or --weekly): the owner and co-parents who want it get the week
              ahead by person, what's unassigned, and what's overdue

Each email holds only the recipient's own jobs (title, time, child's first name, notes)
or, for the weekly summary, counts and titles. Never the info kit. A reminder_sends row
makes a re-run on the same day a no-op. Dry runs render without sending or recording.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from campfinder.config import get_settings
from campfinder.database import get_supabase
from campfinder.household.mailer import Email, get_mailer
from campfinder.household.service import _esc, member_names, task_rows

log = logging.getLogger(__name__)

KIND_ICON = {"dropoff": "🚗", "pickup": "🚗", "form": "📝", "payment": "💳", "packing": "🎒", "deadline": "⏰", "other": "•"}


def local_today() -> date:
    return datetime.now(ZoneInfo(os.environ.get("REMINDER_TZ", "America/New_York"))).date()


@dataclass
class Outgoing:
    member_id: str
    kind: str          # digest | weekly
    period: date
    task_count: int
    email: Email


def _when(t: dict[str, Any]) -> str:
    if not t.get("due_time"):
        return ""
    return time.fromisoformat(str(t["due_time"])).strftime("%-I:%M %p").lower()


def _app_link(path: str = "/household") -> str:
    return f"{get_settings().frontend_url.rstrip('/')}{path}"


def render_digest(member: dict[str, Any], tasks: list[dict[str, Any]], day: date, overdue: list[dict[str, Any]]) -> Email:
    label = "today" if member.get("reminder_pref") == "daily" else "tomorrow"
    subject = f"For {label}: " + (
        tasks[0]["title"] if len(tasks) == 1 else f"{len(tasks)} family jobs"
    )
    lines, items = [], []
    for t in tasks:
        when = _when(t)
        lines.append(f"- {when + ' ' if when else ''}{t['title']}" + (f"\n  {t['notes']}" if t.get("notes") else ""))
        items.append(
            f"<li>{KIND_ICON.get(t['kind'], '•')} {'<strong>' + when + '</strong> ' if when else ''}{_esc(t['title'])}"
            + (f"<br><span style='color:#666'>{_esc(t['notes'])}</span>" if t.get("notes") else "")
            + (f"<br><span style='color:#666'>{len(t['checklist'])} things on the list</span>" if t.get("checklist") else "")
            + "</li>"
        )
    late = ""
    if overdue:
        lines.append(f"\nStill open from before: {', '.join(t['title'] for t in overdue[:5])}")
        late = f"<p style='color:#b45309'>Still open from before: {_esc(', '.join(t['title'] for t in overdue[:5]))}</p>"
    link = _app_link()
    text = (f"Hi {member['display_name']},\n\nYour family jobs for {label}, {day:%A %B %-d}:\n"
            + "\n".join(lines) + f"\n\nMark them done: {link}\n\nChange or stop these reminders on that page.")
    html = (f"<p>Hi {_esc(member['display_name'])},</p><p>Your family jobs for {label}, {day:%A %B %-d}:</p>"
            f"<ul>{''.join(items)}</ul>{late}<p><a href='{_esc(link)}'>Mark them done</a></p>"
            "<p style='color:#999;font-size:12px'>Change or stop these reminders on that page.</p>")
    return Email(to=member["email"], subject=subject, html=html, text=text)


def render_weekly(member: dict[str, Any], week_start: date, tasks: list[dict[str, Any]],
                  overdue: list[dict[str, Any]], names: dict[str, str]) -> Email:
    by_person: dict[str, list[dict[str, Any]]] = {}
    for t in tasks:
        by_person.setdefault(names.get(str(t.get("assignee_id")), "Unassigned"), []).append(t)
    unassigned = by_person.pop("Unassigned", [])
    week_end = week_start + timedelta(days=6)
    rows = [f"{name}: {len(ts)} job{'s' if len(ts) != 1 else ''}" for name, ts in sorted(by_person.items())]
    text = [f"Hi {member['display_name']},", "", f"The week of {week_start:%B %-d} – {week_end:%B %-d}:", *[f"- {r}" for r in rows]]
    html = [f"<p>Hi {_esc(member['display_name'])},</p><p>The week of {week_start:%B %-d} – {week_end:%B %-d}:</p>",
            "<ul>" + "".join(f"<li>{_esc(r)}</li>" for r in rows) + "</ul>" if rows else "<p>No jobs assigned yet.</p>"]
    if unassigned:
        titles = ", ".join(t["title"] for t in unassigned[:8])
        text += ["", f"Nobody has these yet ({len(unassigned)}): {titles}"]
        html.append(f"<p><strong>Nobody has these yet ({len(unassigned)}):</strong> {_esc(titles)}</p>")
    if overdue:
        titles = ", ".join(t["title"] for t in overdue[:8])
        text += ["", f"Overdue ({len(overdue)}): {titles}"]
        html.append(f"<p style='color:#b45309'><strong>Overdue ({len(overdue)}):</strong> {_esc(titles)}</p>")
    link = _app_link()
    text += ["", f"See the plan: {link}"]
    html.append(f"<p><a href='{_esc(link)}'>See the plan</a></p>")
    subject = f"Your week ahead: {len(tasks)} job{'s' if len(tasks) != 1 else ''}" + (
        f", {len(unassigned)} unassigned" if unassigned else "")
    return Email(to=member["email"], subject=subject, html="".join(html), text="\n".join(text))


def _already_sent(member_id: str, kind: str, period: date) -> bool:
    return bool(
        get_supabase().table("reminder_sends").select("id").eq("member_id", member_id)
        .eq("kind", kind).eq("period", period.isoformat()).execute().data
    )


def _active_members() -> list[dict[str, Any]]:
    return get_supabase().table("family_members").select("*").eq("status", "active").execute().data or []


def plan_reminders(today: date, weekly: bool | None = None) -> list[Outgoing]:
    """Everything that should go out for `today`, minus anything already sent."""
    weekly = today.weekday() == 6 if weekly is None else weekly
    out: list[Outgoing] = []
    members = [m for m in _active_members() if m.get("email")]
    for m in members:
        pref = m.get("reminder_pref") or "day_before"
        if pref != "off" and m["role"] != "viewer":
            day = today if pref == "daily" else today + timedelta(days=1)
            tasks = task_rows(m["family_id"], assignee_id=str(m["id"]), start=day, end=day, status="open")
            if tasks and not _already_sent(m["id"], "digest", today):
                overdue = task_rows(m["family_id"], assignee_id=str(m["id"]), end=today - timedelta(days=1), status="open")
                out.append(Outgoing(m["id"], "digest", today, len(tasks), render_digest(m, tasks, day, overdue)))
        if weekly and m["role"] in ("owner", "co_parent") and m.get("weekly_summary", True):
            start = today + timedelta(days=1)
            tasks = task_rows(m["family_id"], start=start, end=start + timedelta(days=6), status="open")
            overdue = task_rows(m["family_id"], end=today - timedelta(days=1), status="open")
            if (tasks or overdue) and not _already_sent(m["id"], "weekly", today):
                out.append(Outgoing(m["id"], "weekly", today, len(tasks),
                                    render_weekly(m, start, tasks, overdue, member_names(m["family_id"]))))
    return out


async def run_reminders(today: date | None = None, *, weekly: bool | None = None, dry_run: bool = False) -> list[Outgoing]:
    today = today or local_today()
    planned = plan_reminders(today, weekly)
    if dry_run:
        return planned
    mailer, sent = get_mailer(), []
    for o in planned:
        try:
            ok = await mailer.send(o.email)
        except Exception:
            log.exception("reminder to member %s failed", o.member_id)
            ok = False
        if ok:
            try:
                get_supabase().table("reminder_sends").insert({
                    "member_id": o.member_id, "kind": o.kind, "period": o.period.isoformat(), "task_count": o.task_count,
                }).execute()
            except Exception:
                log.warning("could not record reminder for %s (already sent?)", o.member_id)
            sent.append(o)
    return sent


def main() -> None:
    parser = argparse.ArgumentParser(description="Send household reminder emails")
    parser.add_argument("--dry-run", action="store_true", help="Print what would go out; send and record nothing")
    parser.add_argument("--weekly", action="store_true", help="Include weekly summaries regardless of the day")
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    result = asyncio.run(run_reminders(args.date, weekly=True if args.weekly else None, dry_run=args.dry_run))
    for o in result:
        print(f"--- {o.kind} to {o.email.to}: {o.email.subject}\n{o.email.text}\n")
    print(f"{len(result)} email(s) {'would be sent' if args.dry_run else 'handed to the mailer'}")


if __name__ == "__main__":
    main()
