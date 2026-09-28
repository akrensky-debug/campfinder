"""
Outbound email.

With RESEND_API_KEY set, messages go through Resend. Without it, they are
appended to OUTBOX and logged, which is what tests and local development use.
Every template lives here so the wording is in one place.
"""

from __future__ import annotations

import html
import logging
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
