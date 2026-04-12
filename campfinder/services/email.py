"""
Transactional email via Resend.
Falls back to a no-op if RESEND_API_KEY is not set (dev mode).
"""

from __future__ import annotations

import os
from typing import Any


async def send_results_email(
    to_email: str,
    first_name: str | None,
    location: str,
    camps: list[dict[str, Any]],
) -> None:
    """Send matched camp results to a parent lead."""
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        return  # dev mode — skip silently

    import httpx

    name = first_name or "there"
    camp_rows = "\n".join(
        f"- {c['name']} ({c.get('city', '')}, {c.get('state', '')}) "
        f"— {c.get('camp_type', 'camp')} "
        f"{'| Ages ' + str(c['age_min']) + '–' + str(c['age_max']) if c.get('age_min') else ''} "
        f"{'| $' + str(int(c['price_per_week'])) + '/wk' if c.get('price_per_week') else ''}"
        for c in camps
    )

    html = f"""
    <p>Hi {name},</p>
    <p>Here are your matched summer camps near <strong>{location}</strong>:</p>
    <ul>
      {''.join(f'<li><strong>{c["name"]}</strong> — {c.get("city","")}, {c.get("state","")} '
               f'({c.get("camp_type","camp")})'
               f'{"<br>Ages " + str(c["age_min"]) + "–" + str(c["age_max"]) if c.get("age_min") else ""}'
               f'{"<br>$" + str(int(c["price_per_week"])) + "/week" if c.get("price_per_week") else ""}'
               f'{"<br><em>" + c["description_short"] + "</em>" if c.get("description_short") else ""}'
               f'<br><a href="https://campfinder.com/camps/{c["id"]}">View full details</a>'
               f'</li>'
               for c in camps)}
    </ul>
    <p>— The CampFinder Team</p>
    """

    async with httpx.AsyncClient() as client:
        await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": "CampFinder <hello@campfinder.com>",
                "to": [to_email],
                "subject": f"Your matched summer camps near {location}",
                "html": html,
            },
            timeout=10,
        )


async def send_claim_verification_email(to_email: str, camp_name: str, token: str) -> None:
    """Send verification email to a camp operator initiating a claim."""
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        return

    import httpx

    verify_url = f"https://campfinder.com/claim/verify?token={token}"
    html = f"""
    <p>Hi,</p>
    <p>You requested to claim the listing for <strong>{camp_name}</strong> on CampFinder.</p>
    <p><a href="{verify_url}" style="background:#1d4ed8;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;">
      Verify your email
    </a></p>
    <p>This link expires in 24 hours.</p>
    <p>If you didn't request this, you can ignore this email.</p>
    """

    async with httpx.AsyncClient() as client:
        await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": "CampFinder <hello@campfinder.com>",
                "to": [to_email],
                "subject": f"Verify your claim for {camp_name}",
                "html": html,
            },
            timeout=10,
        )
