"""
Emails to camp owners. Signed as CampFinder, never as a person (docs/decisions/agents.md,
rule 1), and every one says how to reach a person: reply to it. Plain text and HTML.

Copy is a starting point for Andrew to edit; the facts table is what matters.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

from campfinder.config import get_settings
from campfinder.mailer import Email

LABELS = {
    "name": "Name", "city": "Town", "state": "State", "camp_type": "Type", "age_min": "Youngest age",
    "age_max": "Oldest age", "grade_min": "Lowest grade", "grade_max": "Highest grade",
    "price_per_week": "Price per week", "website_url": "Website", "registration_url": "Registration page",
}


def _e(v: Any) -> str:
    return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _signature() -> str:
    return os.environ.get("OWNER_EMAIL_SIGNATURE", "CampFinder")


def _reply_to() -> str | None:
    return os.environ.get("OWNER_REPLY_TO") or None


def _site() -> str:
    return get_settings().frontend_url.rstrip("/")


def upcoming_season(today: date | None = None) -> int:
    today = today or date.today()
    return today.year + 1 if today.month >= 9 else today.year


def _fmt(field: str, value: Any) -> str:
    if field == "price_per_week" and value is not None:
        return f"${value}"
    if field == "camp_type" and value:
        return {"day": "Day camp", "sleepaway": "Sleepaway camp", "specialty": "Specialty program"}.get(value, value)
    return str(value)


def _rows(snapshot: dict[str, Any]) -> list[tuple[str, str]]:
    return [(LABELS[f], _fmt(f, v)) for f, v in snapshot["camp"].items() if v is not None and f in LABELS]


def _session_line(s: dict[str, Any]) -> str:
    when = f"{s['start_date']} to {s['end_date']}"
    bits = [b for b in (s.get("name"), when, f"${s['price']}" if s.get("price") is not None else None) if b]
    return " · ".join(bits)


def listing_confirmation(to: str, first_name: str | None, camp: dict[str, Any], snapshot: dict[str, Any],
                         token: str, waiting: int = 0) -> Email:
    page = f"{_site()}/owners/confirm/{token}"
    camp_url = f"{_site()}/camps/{camp['id']}"
    season = upcoming_season()
    rows, sessions = _rows(snapshot), snapshot["sessions"]
    old = camp.get("season_year") and int(camp["season_year"]) < season
    asked = (f" {waiting} {'family has' if waiting == 1 else 'families have'} asked us to tell them."
             if waiting else "")
    old_note = (f"The dates below are from your {camp['season_year']} season, which is what your website "
                f"shows now. Send {season} dates whenever you have them.") if old else ""

    text = "\n".join([
        f"Hi {first_name or 'there'},", "",
        f"CampFinder helps families plan the whole summer. We built a listing for {camp['name']} from "
        f"your website so parents near {camp.get('city') or 'you'} can find you. Here is what it says:", "",
        *[f"  {k}: {v}" for k, v in rows],
        *(["", "  Sessions:", *[f"    {_session_line(s)}" for s in sessions]] if sessions else []),
        *(["", old_note] if old_note else []), "",
        f"See the page: {camp_url}", "",
        "Is anything wrong? Reply to this email with the fix and a person will change it.",
        f"If it's all right, tell us here: {page}",
        f"When does {season} registration open? Reply and we'll let interested parents know.{asked}", "",
        "No login, no fee to be listed, nothing to install. If you'd rather not be listed, "
        f"take it down here: {page}", "",
        f"Thanks,\n{_signature()}",
    ])
    table = "".join(f"<tr><td style='padding:2px 12px 2px 0;color:#666'>{_e(k)}</td><td>{_e(v)}</td></tr>"
                    for k, v in rows)
    sess = ("<p><strong>Sessions</strong></p><ul>" + "".join(f"<li>{_e(_session_line(s))}</li>" for s in sessions)
            + "</ul>") if sessions else ""
    html = (
        f"<p>Hi {_e(first_name or 'there')},</p>"
        f"<p>CampFinder helps families plan the whole summer. We built a listing for "
        f"<strong>{_e(camp['name'])}</strong> from your website so parents near {_e(camp.get('city') or 'you')} "
        f"can find you. Here is what it says:</p>"
        f"<table>{table}</table>{sess}"
        + (f"<p>{_e(old_note)}</p>" if old_note else "")
        + f"<p><a href='{_e(camp_url)}'>See the page</a></p>"
        f"<p><strong>Is anything wrong?</strong> Reply to this email with the fix and a person will change it.<br>"
        f"<strong>All right?</strong> <a href='{_e(page)}'>Tell us it looks right</a>.<br>"
        f"<strong>When does {season} registration open?</strong> Reply and we'll let interested parents "
        f"know.{_e(asked)}</p>"
        f"<p style='color:#666'>No login, no fee to be listed, nothing to install. If you'd rather not be "
        f"listed, <a href='{_e(page)}'>take it down here</a>.</p>"
        f"<p>Thanks,<br>{_e(_signature())}</p>"
    )
    return Email(to=to, subject=f"Your camp's {season} listing on CampFinder: is it right?",
                 html=html, text=text, reply_to=_reply_to())


def listing_confirmed(to: str, camp_name: str) -> Email:
    text = (f"Thank you. {camp_name}'s page now shows \"confirmed by the camp\" with today's date.\n\n"
            "If anything changes (a week fills up, a new session, a new price), reply to any email from us "
            f"and a person will update it.\n\nThanks,\n{_signature()}")
    html = (f"<p>Thank you. <strong>{_e(camp_name)}</strong>'s page now shows \"confirmed by the camp\" with "
            f"today's date.</p><p>If anything changes (a week fills up, a new session, a new price), reply to "
            f"any email from us and a person will update it.</p><p>Thanks,<br>{_e(_signature())}</p>")
    return Email(to=to, subject=f"Confirmed: {camp_name}", html=html, text=text, reply_to=_reply_to())


def listing_removed(to: str, camp_name: str) -> Email:
    text = (f"{camp_name} is off CampFinder. Parents won't see it in search or on our pages.\n\n"
            "If that was a mistake, reply to this email and a person will put it back.\n\n"
            f"Thanks,\n{_signature()}")
    html = (f"<p><strong>{_e(camp_name)}</strong> is off CampFinder. Parents won't see it in search or on our "
            f"pages.</p><p>If that was a mistake, reply to this email and a person will put it back.</p>"
            f"<p>Thanks,<br>{_e(_signature())}</p>")
    return Email(to=to, subject=f"Removed: {camp_name}", html=html, text=text, reply_to=_reply_to())
