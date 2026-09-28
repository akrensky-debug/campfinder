"""
Send registration alerts for camps whose registration opens within a week.

    python -m campfinder.jobs.send_alerts

Run daily. Each alert is sent once; the parent can stop it from the email.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import asyncpg

from campfinder.config import get_settings
from campfinder.database import _init_connection
from campfinder.repositories import bookings as repo
from campfinder.security import new_token, hash_token
from campfinder.services import email

WINDOW = timedelta(days=7)


async def send_due_alerts(conn: asyncpg.Connection) -> int:
    settings = get_settings()
    sent = 0
    for alert in await repo.alerts_due(conn, within=WINDOW):
        # Rotate the unsubscribe token so the emailed link is the only copy in the wild.
        token = new_token()
        await conn.execute(
            "UPDATE registration_alerts SET unsubscribe_token_hash = $2 WHERE id = $1", alert["id"], hash_token(token)
        )
        await email.send(email.registration_alert(
            to=alert["email"], camp_name=alert["camp_name"],
            opens_at=alert["opens_at"].strftime("%A %B %-d at %-I:%M %p UTC"),
            camp_url=f"{settings.site_url}/camps/{alert['slug']}", unsubscribe_token=token,
        ))
        await repo.mark_alert_sent(conn, alert["id"])
        sent += 1
    return sent


async def _main() -> None:
    conn = await asyncpg.connect(get_settings().asyncpg_dsn)
    await _init_connection(conn)
    try:
        print(f"sent {await send_due_alerts(conn)} alerts")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(_main())
