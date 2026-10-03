"""
Registration-day reminders: registration opening soon, payment due, forms due.

Run once or twice a day (e.g. a Railway cron at 7am Eastern) with
    python -m campfinder.booking.reminders [--dry-run] [--date YYYY-MM-DD]
or POST /api/v1/internal/registration-reminders/run with the X-Cron-Secret header.

BOOKING_EMAIL_MODE picks the transport:
  log     (default) render and log, send nothing
  resend  send through Resend (needs RESEND_API_KEY)
  off     drop silently
Tests use MemoryMailer via set_mailer(). Real email goes out only when the mode is
explicitly resend. Each family gets at most one email per run, listing what's due; a
registration_reminder_sends row per item makes re-runs no-ops. Emails carry camp
names, dates and a link back, never info kit contents.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import logging
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from campfinder.booking.models import ReminderPrefs, ReminderPreview
from campfinder.booking.service import (
    ACTIVE, _fmt_day, _now, _fmt_when, _parse_date, get_camp_row, local_today, local_tz, resolve_opens,
)
from campfinder.config import get_settings
from campfinder.database import get_supabase

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mail transport
# ---------------------------------------------------------------------------

@dataclass
class Email:
    to: str
    subject: str
    html: str
    text: str


class Mailer(Protocol):
    async def send(self, email: Email) -> bool: ...


class LogMailer:
    async def send(self, email: Email) -> bool:
        log.info("email (not sent, BOOKING_EMAIL_MODE=log) to=%s subject=%r\n%s", email.to, email.subject, email.text)
        return True


class OffMailer:
    async def send(self, email: Email) -> bool:
        return False


@dataclass
class MemoryMailer:
    outbox: list[Email] = field(default_factory=list)

    async def send(self, email: Email) -> bool:
        self.outbox.append(email)
        return True


class ResendMailer:
    def __init__(self, api_key: str, sender: str):
        self.api_key, self.sender = api_key, sender

    async def send(self, email: Email) -> bool:
        import httpx

        async with httpx.AsyncClient() as client:
            res = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"from": self.sender, "to": [email.to], "subject": email.subject,
                      "html": email.html, "text": email.text},
                timeout=10,
            )
        if res.status_code >= 300:
            log.warning("resend rejected reminder: %s", res.text[:200])
            return False
        return True


_mailer: Mailer | None = None


def get_mailer() -> Mailer:
    global _mailer
    if _mailer is None:
        mode = os.environ.get("BOOKING_EMAIL_MODE", "log").lower()
        key = os.environ.get("RESEND_API_KEY", "")
        if mode == "resend" and key:
            _mailer = ResendMailer(key, os.environ.get("EMAIL_FROM", "CampFinder <hello@campfinder.com>"))
        elif mode == "off":
            _mailer = OffMailer()
        else:
            _mailer = LogMailer()
    return _mailer


def set_mailer(mailer: Mailer | None) -> None:
    global _mailer
    _mailer = mailer


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------

def load_prefs(family_id: str) -> ReminderPrefs:
    rows = get_supabase().table("registration_reminder_prefs").select("*").eq("family_id", family_id).execute().data
    return ReminderPrefs.model_validate(rows[0]) if rows else ReminderPrefs()


def save_prefs(family_id: str, prefs: ReminderPrefs) -> ReminderPrefs:
    prefs.opens_days = sorted({d for d in prefs.opens_days if 0 <= d <= 60}, reverse=True)
    prefs.deadline_days = sorted({d for d in prefs.deadline_days if 0 <= d <= 60}, reverse=True)
    sb = get_supabase()
    values = {**prefs.model_dump(), "updated_at": _now()}
    if sb.table("registration_reminder_prefs").select("family_id").eq("family_id", family_id).execute().data:
        sb.table("registration_reminder_prefs").update(values).eq("family_id", family_id).execute()
    else:
        sb.table("registration_reminder_prefs").insert({"family_id": family_id, **values}).execute()
    return prefs


def account_email(family: dict[str, Any]) -> str | None:
    owner = family.get("owner_user_id")
    if not owner:
        return None
    try:
        return get_supabase().auth.admin.get_user_by_id(str(owner)).user.email
    except Exception:
        return None


# ---------------------------------------------------------------------------
# What's due
# ---------------------------------------------------------------------------

@dataclass
class Due:
    kind: str           # opens | payment_due | forms_due
    registration: dict[str, Any]
    camp: dict[str, Any]
    due_on: date
    days_before: int
    line: str


def _in(days: int) -> str:
    return "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"


def due_items(rows: list[dict[str, Any]], prefs: ReminderPrefs, today: date) -> list[Due]:
    out: list[Due] = []
    camps: dict[str, dict[str, Any]] = {}
    for r in rows:
        if not r.get("remind", True) or r["status"] not in ACTIVE:
            continue
        cid = str(r["camp_id"])
        camp = camps.get(cid) or camps.setdefault(cid, get_camp_row(cid))
        who = f" for {r['child_name']}" if r.get("child_name") else ""
        if r["status"] == "watching":
            opens_at, _, _ = resolve_opens(r)
            if opens_at:
                day = opens_at.astimezone(local_tz()).date()
                n = (day - today).days
                if n in prefs.opens_days:
                    out.append(Due("opens", r, camp, day, n,
                                   f"{camp['name']}{who}: registration opens {_in(n)}, {_fmt_when(opens_at)}."))
            continue
        pay_due = _parse_date(r.get("payment_due_date"))
        if pay_due and (r.get("payment_status") or "unpaid") in ("unpaid", "deposit"):
            n = (pay_due - today).days
            if n in prefs.deadline_days:
                amount = f"${float(r['balance_due']):,.0f} " if r.get("balance_due") else ""
                out.append(Due("payment_due", r, camp, pay_due, n,
                               f"{camp['name']}{who}: {amount}payment due {_in(n)}, {_fmt_day(pay_due)}."))
        forms_due = _parse_date(r.get("forms_due_date"))
        if forms_due:
            n = (forms_due - today).days
            if n in prefs.deadline_days:
                out.append(Due("forms_due", r, camp, forms_due, n,
                               f"{camp['name']}{who}: forms due {_in(n)}, {_fmt_day(forms_due)}."))
    return out


def _already_sent(item: Due) -> bool:
    return bool(
        get_supabase().table("registration_reminder_sends").select("id")
        .eq("registration_id", str(item.registration["id"])).eq("kind", item.kind)
        .eq("due_on", item.due_on.isoformat()).eq("days_before", item.days_before).execute().data
    )


def render(items: list[Due]) -> Email:
    base = get_settings().frontend_url.rstrip("/")
    first = items[0]
    if len(items) == 1:
        subject = {"opens": f"Registration opens {_in(first.days_before)}: {first.camp['name']}",
                   "payment_due": f"Payment due {_in(first.days_before)}: {first.camp['name']}",
                   "forms_due": f"Forms due {_in(first.days_before)}: {first.camp['name']}"}[first.kind]
    else:
        subject = f"{len(items)} camp registration reminders"
    text_lines, html_items = [], []
    for it in items:
        link = f"{base}/register/{it.camp['id']}?registration={it.registration['id']}"
        action = "Get ready" if it.kind == "opens" else "Open checklist"
        text_lines.append(f"- {it.line}\n  {action}: {link}")
        html_items.append(f"<li>{html.escape(it.line)}<br><a href='{html.escape(link)}'>{action}</a></li>")
    manage = f"{base}/registrations"
    text = ("Hi,\n\nHere's what's coming up:\n\n" + "\n".join(text_lines)
            + f"\n\nChange or stop these reminders: {manage}\n")
    body = (f"<p>Hi,</p><p>Here's what's coming up:</p><ul>{''.join(html_items)}</ul>"
            f"<p style='color:#999;font-size:12px'><a href='{html.escape(manage)}'>Change or stop these reminders</a></p>")
    return Email(to="", subject=subject, html=body, text=text)


def preview_for_family(family_id: str, today: date | None = None) -> list[ReminderPreview]:
    """What reminders would go out for this family on a given day. Sends nothing."""
    today = today or local_today()
    rows = get_supabase().table("family_registrations").select("*").eq("family_id", family_id).execute().data or []
    items = due_items(rows, load_prefs(family_id), today)
    return [
        ReminderPreview(kind=i.kind, registration_id=i.registration["id"], due_on=i.due_on, days_before=i.days_before,
                        subject=render([i]).subject, text=i.line)
        for i in items
    ]


async def run(today: date | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Send today's reminders. Returns counts and, for dry runs, the rendered emails."""
    today = today or local_today()
    sb = get_supabase()
    rows = sb.table("family_registrations").select("*").in_("status", list(ACTIVE)).execute().data or []
    by_family: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_family.setdefault(str(r["family_id"]), []).append(r)

    sent, skipped, rendered = 0, 0, []
    for family_id, regs in by_family.items():
        fam = sb.table("families").select("*").eq("id", family_id).execute().data
        if not fam or fam[0].get("owner_user_id") is None:
            continue  # reminders need an account
        prefs = load_prefs(family_id)
        if not prefs.enabled:
            continue
        to = prefs.email or account_email(fam[0])
        if not to:
            continue
        items = [i for i in due_items(regs, prefs, today) if not _already_sent(i)]
        if not items:
            continue
        email = render(items)
        email.to = to
        if dry_run:
            rendered.append({"to": to, "subject": email.subject, "text": email.text})
            continue
        if await get_mailer().send(email):
            sent += 1
            sb.table("registration_reminder_sends").insert([
                {"registration_id": str(i.registration["id"]), "kind": i.kind,
                 "due_on": i.due_on.isoformat(), "days_before": i.days_before} for i in items
            ]).execute()
        else:
            skipped += 1
    return {"date": today.isoformat(), "families_emailed": sent, "failed": skipped,
            "dry_run": dry_run, "emails": rendered}


def main() -> None:
    p = argparse.ArgumentParser(description="Send registration-day reminders.")
    p.add_argument("--dry-run", action="store_true", help="Render without sending or recording.")
    p.add_argument("--date", type=date.fromisoformat, help="Pretend today is this date (YYYY-MM-DD).")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO)
    result = asyncio.run(run(args.date, args.dry_run))
    for e in result["emails"]:
        print(f"To: {e['to']}\nSubject: {e['subject']}\n\n{e['text']}\n{'-' * 40}")
    print({k: v for k, v in result.items() if k != "emails"})


if __name__ == "__main__":
    main()
