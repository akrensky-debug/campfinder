"""Operator emails that predate owner confirmation: the claim verification code."""

from __future__ import annotations

import html

from campfinder.config import get_settings
from campfinder.mailer import Email, get_mailer


async def send_claim_verification_email(to_email: str, camp_id: str, camp_name: str, token: str) -> bool:
    """Email the code that proves the operator reads this address. Goes through the shared mailer,
    so nothing is sent unless EMAIL_MODE=resend."""
    page = f"{get_settings().frontend_url.rstrip('/')}/operators/claim?camp_id={camp_id}"
    text = (f"Hi,\n\nYou asked to claim the listing for {camp_name} on CampFinder.\n\n"
            f"Your verification code: {token}\n\nEnter it here: {page}\n\n"
            "If you didn't ask for this, ignore this email.\n\nCampFinder")
    body = (f"<p>Hi,</p><p>You asked to claim the listing for <strong>{html.escape(camp_name)}</strong> on "
            f"CampFinder.</p><p>Your verification code:</p><p><code>{html.escape(token)}</code></p>"
            f"<p><a href='{html.escape(page)}'>Enter it here</a></p>"
            "<p style='color:#666'>If you didn't ask for this, ignore this email.</p><p>CampFinder</p>")
    return await get_mailer().send(Email(to=to_email, subject=f"Verify your claim for {camp_name}", html=body, text=text))
