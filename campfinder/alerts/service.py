"""
"Tell me when registration opens": public alerts, no account.

A parent leaves an email on a camp's page. We email a confirm link; nothing else is sent
until it is clicked. After that, the alert job emails three times at most per opening
date, and only for dates our team has checked against the camp (a verified
registration_windows row):

  announced   the date is known and more than a day away
  opens_soon  it opens today or tomorrow
  open_now    it has opened (within the last 36 hours) and hasn't closed

Run the job hourly so "open now" lands close to the opening:
    python -m campfinder.alerts [--dry-run] [--now 2027-01-12T14:05:00+00:00]
or POST /api/v1/internal/registration-alerts/run with the X-Cron-Secret header.
Announcements and "opens soon" wait until 7am local time; "open now" goes out at once.

What we keep: the email address, which camp (and session), and when it was confirmed or
stopped. The sign-up answer is the same whether or not the address was already signed up,
so the endpoint can't be used to learn who is.
"""

from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

from campfinder.alerts import emails
from campfinder.booking.service import _parse_ts, camp_window, get_camp_row, get_session_row, local_tz
from campfinder.database import get_supabase
from campfinder.mailer import get_mailer

log = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CONFIRM_FOR = timedelta(days=7)        # a confirm link works this long
RESEND_AFTER = timedelta(hours=1)      # a second sign-up within this sends no second email
MAX_PENDING_PER_DAY = 10               # unconfirmed sign-ups one address can collect in a day
OPEN_NOW_FOR = timedelta(hours=36)     # "open now" is news this long after opening
MORNING = 7                            # local hour before which only "open now" is sent

KINDS = ("announced", "opens_soon", "open_now")


class AlertError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat()


def _same_session(row: dict[str, Any], session_id: str | None) -> bool:
    return str(row.get("session_id") or "") == str(session_id or "")


def normalize_email(email: str) -> str:
    email = (email or "").strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise AlertError("That doesn't look like an email address.")
    return email


def _live_camp(camp_id: str) -> dict[str, Any]:
    camp = get_camp_row(camp_id)
    if camp.get("is_active") is False:
        raise HTTPException(status_code=404, detail="Camp not found")
    return camp


# ---------------------------------------------------------------------------
# Sign up, confirm, stop
# ---------------------------------------------------------------------------

async def sign_up(camp_id: str, session_id: str | None, email: str) -> None:
    """Start an alert and email the confirm link. Returns nothing either way: the caller
    answers the same whether this address was new, pending, already on, or rate limited."""
    email = normalize_email(email)
    camp = _live_camp(camp_id)
    session = get_session_row(camp_id, session_id)
    sb = get_supabase()
    now = _now()

    mine = sb.table("registration_alerts").select("*").eq("email", email).execute().data or []
    row = next((r for r in mine if str(r["camp_id"]) == str(camp_id) and _same_session(r, session_id)), None)
    if row and row.get("confirmed_at") and not row.get("unsubscribed_at"):
        return  # already on: say nothing new
    if row and not row.get("confirmed_at") and not row.get("unsubscribed_at") and row.get("confirm_sent_at") \
            and now - _parse_ts(row["confirm_sent_at"]) < RESEND_AFTER:
        return  # the first email is probably still on its way
    pending = [r for r in mine if not r.get("confirmed_at") and r.get("confirm_sent_at")
               and now - _parse_ts(r["confirm_sent_at"]) < timedelta(days=1)]
    if len(pending) >= MAX_PENDING_PER_DAY:
        log.warning("registration alert sign-ups for one address hit the daily limit")
        return

    token = secrets.token_urlsafe(24)
    values = {"token": token, "confirm_sent_at": _iso(now), "confirmed_at": None, "unsubscribed_at": None,
              "updated_at": _iso(now)}
    try:
        if row:
            sb.table("registration_alerts").update(values).eq("id", str(row["id"])).execute()
        else:
            sb.table("registration_alerts").insert(
                {"camp_id": str(camp_id), "session_id": str(session_id) if session_id else None, "email": email,
                 **values}).execute()
    except Exception:  # two sign-ups at once: the other one sent the email
        log.info("registration alert sign-up raced; skipping")
        return
    await get_mailer().send(emails.confirm(email, camp, session, token))


def _by_token(token: str) -> dict[str, Any]:
    rows = get_supabase().table("registration_alerts").select("*").eq("token", token).execute().data \
        if token and len(token) <= 64 else []
    if not rows:
        raise HTTPException(status_code=404, detail="This link isn't one of ours, or it was replaced by a newer one.")
    return rows[0]


def _status(row: dict[str, Any], now: datetime | None = None) -> str:
    if row.get("unsubscribed_at"):
        return "stopped"
    if row.get("confirmed_at"):
        return "on"
    sent = _parse_ts(row.get("confirm_sent_at")) or _parse_ts(row.get("created_at"))
    if sent and (now or _now()) - sent > CONFIRM_FOR:
        return "expired"
    return "pending"


def _hint(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:1]}{'•' * max(len(name) - 1, 2)}@{domain}"


def view(token: str) -> dict[str, Any]:
    """What the alert page shows. Looking changes nothing (mail scanners open links)."""
    row = _by_token(token)
    camp = get_camp_row(str(row["camp_id"]))
    session = get_session_row(str(row["camp_id"]), row.get("session_id")) if row.get("session_id") else None
    window = camp_window(str(row["camp_id"]), row.get("session_id"))
    verified = bool(window and window.get("verified"))
    return {
        "status": _status(row),
        "camp_id": str(row["camp_id"]),
        "camp_name": camp["name"],
        "session_name": session.get("name") if session else None,
        "email_hint": _hint(row["email"]),
        "opens_at": window["opens_at"] if verified else None,
        "closes_at": window.get("closes_at") if verified else None,
        "registration_url": camp.get("registration_url") or (window.get("source_url") if verified else None),
    }


def confirm(token: str) -> dict[str, Any]:
    row = _by_token(token)
    status = _status(row)
    if status == "expired":
        raise HTTPException(status_code=410, detail="This link has expired. Sign up again on the camp's page.")
    if status == "pending":
        now = _iso(_now())
        get_supabase().table("registration_alerts").update({"confirmed_at": now, "updated_at": now}) \
            .eq("id", str(row["id"])).execute()
    return view(token)  # a stopped alert stays stopped: confirming an old email doesn't undo a stop


def stop(token: str) -> dict[str, Any]:
    row = _by_token(token)
    if not row.get("unsubscribed_at"):
        now = _iso(_now())
        get_supabase().table("registration_alerts").update({"unsubscribed_at": now, "updated_at": now}) \
            .eq("id", str(row["id"])).execute()
    return view(token)


def waiting_count(camp_id: str) -> int:
    """Confirmed addresses waiting on this camp's registration (any session)."""
    rows = get_supabase().table("registration_alerts").select("email,confirmed_at,unsubscribed_at") \
        .eq("camp_id", str(camp_id)).execute().data or []
    return len({r["email"] for r in rows if r.get("confirmed_at") and not r.get("unsubscribed_at")})


# ---------------------------------------------------------------------------
# The alert job
# ---------------------------------------------------------------------------

@dataclass
class Item:
    alert: dict[str, Any]
    camp: dict[str, Any]
    session: dict[str, Any] | None
    kind: str
    opens_at: datetime
    closes_at: datetime | None
    source_url: str | None


def pick_kind(opens_at: datetime, closes_at: datetime | None, now: datetime) -> str | None:
    """Which alert this opening date calls for right now, if any."""
    if opens_at <= now:
        if now - opens_at <= OPEN_NOW_FOR and (closes_at is None or closes_at > now):
            return "open_now"
        return None
    local_now = now.astimezone(local_tz())
    if local_now.hour < MORNING:
        return None
    days = (opens_at.astimezone(local_tz()).date() - local_now.date()).days
    return "opens_soon" if days <= 1 else "announced"


def _already_sent(alert_id: str, kind: str, opens_at: datetime) -> bool:
    rows = get_supabase().table("registration_alert_sends").select("opens_at,kind") \
        .eq("alert_id", alert_id).eq("kind", kind).execute().data or []
    return any(_parse_ts(r["opens_at"]) == opens_at for r in rows)


def due(now: datetime) -> list[Item]:
    sb = get_supabase()
    alerts = [a for a in (sb.table("registration_alerts").select("*").execute().data or [])
              if a.get("confirmed_at") and not a.get("unsubscribed_at")]
    camps: dict[str, dict[str, Any] | None] = {}
    windows: dict[tuple[str, str], dict[str, Any] | None] = {}
    sessions: dict[str, dict[str, Any] | None] = {}
    out: list[Item] = []
    for a in alerts:
        cid, sid = str(a["camp_id"]), str(a.get("session_id") or "")
        if cid not in camps:
            rows = sb.table("camps").select("*").eq("id", cid).execute().data
            camps[cid] = rows[0] if rows and rows[0].get("is_active") is not False else None
        camp = camps[cid]
        if camp is None:
            continue
        if (cid, sid) not in windows:
            windows[(cid, sid)] = camp_window(cid, sid or None)
        w = windows[(cid, sid)]
        if not w or not w.get("verified"):
            continue  # only dates a person has checked against the camp
        opens, closes = _parse_ts(w["opens_at"]), _parse_ts(w.get("closes_at"))
        kind = pick_kind(opens, closes, now)
        if not kind or _already_sent(str(a["id"]), kind, opens):
            continue
        if sid and sid not in sessions:
            rows = sb.table("sessions").select("*").eq("id", sid).execute().data
            sessions[sid] = rows[0] if rows else None
        out.append(Item(a, camp, sessions.get(sid) if sid else None, kind, opens, closes, w.get("source_url")))
    return out


async def run(now: datetime | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Send what's due, one email per address. Returns counts and, for dry runs, the emails."""
    now = now or _now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    by_email: dict[str, list[Item]] = {}
    for item in due(now):
        by_email.setdefault(item.alert["email"], []).append(item)

    sent, not_sent, rendered = 0, 0, []
    sb = get_supabase()
    for to, items in by_email.items():
        email = emails.alert(to, items, now)
        if dry_run:
            rendered.append({"to": to, "subject": email.subject, "text": email.text})
            continue
        if not await get_mailer().send(email):
            not_sent += 1  # log mode, or Resend refused: try again next run
            continue
        sent += 1
        sb.table("registration_alert_sends").insert([
            {"alert_id": str(i.alert["id"]), "kind": i.kind, "opens_at": _iso(i.opens_at)} for i in items
        ]).execute()
    return {"at": _iso(now), "addresses_emailed": sent, "not_sent": not_sent, "dry_run": dry_run,
            "emails": rendered}
