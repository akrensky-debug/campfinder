"""
Outbound email.

With RESEND_API_KEY set, messages go through Resend. Without it, they are
appended to OUTBOX and logged, which is what tests and local development use.
Every template lives here so the wording is in one place.
"""

from __future__ import annotations

import html
import logging
from datetime import date
from dataclasses import dataclass, field

import httpx

from campfinder.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class Email:
    to: str
    subject: str
    html: str
    headers: dict[str, str] = field(default_factory=dict)


OUTBOX: list[Email] = []


def reset_outbox() -> None:
    OUTBOX.clear()


async def send(email: Email) -> None:
    settings = get_settings()
    if not settings.resend_api_key:
        OUTBOX.append(email)
        logger.info("email (not sent, no RESEND_API_KEY): to=%s subject=%s", email.to, email.subject)
        return
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from,
                "to": [email.to],
                "subject": email.subject,
                "html": email.html,
                "headers": email.headers,
            },
        )
        response.raise_for_status()


def _e(value: object) -> str:
    return html.escape(str(value)) if value is not None else ""


# ── Templates ──────────────────────────────────────────────────────────────

def claim_verification(to: str, camp_name: str, token: str) -> Email:
    url = f"{get_settings().site_url}/operators/claim/verify?token={token}"
    return Email(
        to=to,
        subject=f"Confirm you run {camp_name}",
        html=(
            f"<p>You asked to take over the listing for <strong>{_e(camp_name)}</strong>.</p>"
            f"<p><a href=\"{_e(url)}\">Confirm it's you</a></p>"
            f"<p>The link works once and expires in 24 hours. If this wasn't you, ignore this email.</p>"
        ),
    )


def spot_request_to_camp(
    to: str, camp_name: str, session_name: str, session_dates: str,
    child_first_name: str, child_age: int, parent_note: str | None, token: str,
) -> Email:
    base = f"{get_settings().site_url}/spot-requests/respond?token={token}"
    note = f"<p>Message from the parent: {_e(parent_note)}</p>" if parent_note else ""
    return Email(
        to=to,
        subject=f"Spot request for {camp_name}: {session_name or session_dates}",
        html=(
            f"<p>A parent would like a spot at <strong>{_e(camp_name)}</strong> for "
            f"<strong>{_e(session_name or 'a session')}</strong> ({_e(session_dates)}).</p>"
            f"<p>Child: {_e(child_first_name)}, age {child_age}.</p>"
            f"{note}"
            f"<p><a href=\"{_e(base)}&answer=confirm\">Confirm the spot</a> &nbsp;|&nbsp; "
            f"<a href=\"{_e(base)}&answer=decline\">Sorry, no room</a></p>"
            f"<p>Once you confirm, we send you the child's forms and the parent's contact details, "
            f"and you collect payment the way you normally do.</p>"
        ),
    )


def spot_confirmed_to_parent(to: str, first_name: str | None, camp_name: str, session_dates: str,
                             camp_email: str | None, camp_note: str | None) -> Email:
    note = f"<p>From the camp: {_e(camp_note)}</p>" if camp_note else ""
    contact = f"<p>Camp contact: {_e(camp_email)}</p>" if camp_email else ""
    return Email(
        to=to,
        subject=f"Confirmed: {camp_name}, {session_dates}",
        html=(
            f"<p>Hi {_e(first_name or 'there')},</p>"
            f"<p><strong>{_e(camp_name)}</strong> confirmed your spot for {_e(session_dates)}.</p>"
            f"{note}{contact}"
            f"<p>The camp will be in touch about payment.</p>"
        ),
    )


def spot_declined_to_parent(to: str, first_name: str | None, camp_name: str, session_dates: str,
                            camp_note: str | None) -> Email:
    note = f"<p>From the camp: {_e(camp_note)}</p>" if camp_note else ""
    return Email(
        to=to,
        subject=f"No room: {camp_name}, {session_dates}",
        html=(
            f"<p>Hi {_e(first_name or 'there')},</p>"
            f"<p>{_e(camp_name)} couldn't offer a spot for {_e(session_dates)}.</p>{note}"
            f"<p>Your summer plan is still saved. Want alternatives for those dates? Reply to this email.</p>"
        ),
    )


def registration_alert(to: str, camp_name: str, opens_at: str, camp_url: str, unsubscribe_token: str) -> Email:
    unsub = f"{get_settings().site_url}/alerts/unsubscribe?token={unsubscribe_token}"
    return Email(
        to=to,
        subject=f"Registration opens soon: {camp_name}",
        html=(
            f"<p>Registration for <strong>{_e(camp_name)}</strong> opens {_e(opens_at)}.</p>"
            f"<p><a href=\"{_e(camp_url)}\">See sessions and prices</a></p>"
            f"<p><a href=\"{_e(unsub)}\">Stop alerts for this camp</a></p>"
        ),
        headers={"List-Unsubscribe": f"<{unsub}>"},
    )


# ── Owner confirmation ─────────────────────────────────────────────────────
# Wording from docs/brand/OUTREACH-CAMPS.md, scripts 1 and 4: Andrew's own
# first-contact emails, sent one camp at a time by a person, so they carry his
# name (docs/decisions/agents.md, rule 1). Replies go to the team inbox.

def upcoming_season(today: date | None = None) -> int:
    """The summer parents are planning now: this one until August, then next year's."""
    today = today or date.today()
    return today.year if today.month < 9 else today.year + 1


def _reply_to() -> dict[str, str]:
    team = get_settings().team_email
    return {"Reply-To": team} if team else {}


def _money(value: object) -> str:
    return f"${value}" if value not in (None, "") else ""


def _ages(c: dict[str, object]) -> str:
    if c.get("age_min") is not None or c.get("age_max") is not None:
        return f"{c.get('age_min') or '?'} to {c.get('age_max') or '?'}"
    if c.get("grade_min") is not None or c.get("grade_max") is not None:
        return f"grades {c.get('grade_min') if c.get('grade_min') is not None else '?'} to {c.get('grade_max') if c.get('grade_max') is not None else '?'}"
    return ""


def _listing_table(snapshot: dict[str, object]) -> str:
    c = snapshot["camp"]  # type: ignore[index]
    rows = [
        ("Name", c.get("name")),
        ("Town", f"{c.get('city')}, {c.get('state')}"),
        ("Kind", {"day": "Day camp", "sleepaway": "Overnight camp", "specialty": "Specialty camp"}.get(c.get("camp_type"), c.get("camp_type"))),
        ("Ages", _ages(c) or "not listed"),
        ("Price per week", _money(c.get("price_per_week")) or "not listed"),
        ("Website", c.get("website_url") or "not listed"),
    ]
    cells = "".join(f"<tr><td><strong>{_e(k)}</strong></td><td>{_e(v)}</td></tr>" for k, v in rows)
    sessions = snapshot["sessions"]  # type: ignore[index]
    if sessions:
        items = "".join(
            f"<li>{_e(s.get('name') or 'Session')}: {_e(s['start_date'])} to {_e(s['end_date'])}"
            f"{', ' + _e(_money(s.get('price'))) if s.get('price') else ''}"
            f"{', registration opens ' + _e(str(s['registration_opens_at'])[:10]) if s.get('registration_opens_at') else ''}</li>"
            for s in sessions
        )
        session_html = f"<p><strong>Sessions</strong></p><ul>{items}</ul>"
    else:
        session_html = "<p><strong>Sessions</strong>: none listed yet.</p>"
    return f"<table>{cells}</table>{session_html}"


def listing_confirmation(to: str, first_name: str | None, camp: dict[str, object], snapshot: dict[str, object],
                         token: str) -> Email:
    settings = get_settings()
    page = f"{settings.site_url}/owners/confirm?token={token}"
    camp_url = f"{settings.site_url}/camps/{camp['slug']}"
    upcoming = upcoming_season()
    shown = camp.get("season_year")
    old_season = (
        f"<p>The dates below are from your {_e(shown)} season, which is what your website shows now. "
        f"Send {upcoming} dates whenever you have them.</p>"
        if shown and int(shown) < upcoming else ""
    )
    signature = settings.team_signature
    phone = f"<br>{_e(settings.team_phone)}" if settings.team_phone else ""
    return Email(
        to=to,
        subject=f"Your camp's {upcoming} listing (please check it)",
        html=(
            f"<p>Hi {_e(first_name or 'there')},</p>"
            f"<p>I'm a Providence parent building a site that helps families plan the whole summer. "
            f"I built a page for <strong>{_e(camp['name'])}</strong> from your website so parents searching "
            f"near {_e(camp['city'])} can find you.</p>"
            f"<p>Here is what it says:</p>"
            f"{old_season}"
            f"{_listing_table(snapshot)}"
            f"<p><a href=\"{_e(camp_url)}\">See the page</a></p>"
            f"<p>Two asks:</p>"
            f"<ol><li>Is anything wrong? Reply with the fix and I'll change it the same day. "
            f"If it's all right, <a href=\"{_e(page)}\">tell me it looks right</a>.</li>"
            f"<li>When does {upcoming} registration open? Parents can ask to be told, "
            f"and I'll send them your way.</li></ol>"
            f"<p>No login, no fee to be listed, nothing to install. If you'd rather not be on it, reply "
            f"\"remove\" or <a href=\"{_e(page)}\">take it down here</a>, and it's gone.</p>"
            f"<p>Thanks, {_e(signature)}{phone}</p>"
        ),
        headers=_reply_to(),
    )


def listing_confirmed(to: str, camp_name: str) -> Email:
    signature = get_settings().team_signature
    return Email(
        to=to,
        subject=f"Done: {camp_name} is confirmed",
        html=(
            f"<p>Done. Your page now shows \"confirmed by the camp\" with today's date.</p>"
            f"<p>From here, anything that changes, just reply to any email from me: \"Week 3 is full,\" "
            f"\"price is now $325,\" \"added a session August 9.\" The page updates and I'll confirm back.</p>"
            f"<p>When a parent asks for a spot, you'll get an email with the child's first name and age and "
            f"two buttons: confirm or no room. You collect payment the way you do now.</p>"
            f"<p>Thanks, {_e(signature)}</p>"
        ),
        headers=_reply_to(),
    )


def listing_removed(to: str, camp_name: str) -> Email:
    return Email(
        to=to,
        subject=f"Removed: {camp_name}",
        html=(
            f"<p><strong>{_e(camp_name)}</strong> is off the site. Parents can no longer find it through us.</p>"
            f"<p>If that was a mistake, reply to this email and a person will put it back.</p>"
            f"<p>CampFinder</p>"
        ),
        headers=_reply_to(),
    )
