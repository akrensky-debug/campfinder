"""
One hourly tick runs every scheduled job at the right local time (REMINDER_TZ, default
America/New_York), so the scheduler stays a dumb "call this every hour":

    every hour   registration alerts (announced / opens soon / open now)
    7am          registration reminders, household morning digests
    6pm          household evening (day-before) reminders

Every job records what it sent, so a repeated or late tick sends nothing twice. Called by
POST /api/v1/internal/cron/tick (X-Cron-Secret: BOOKING_CRON_SECRET), or
`python -m campfinder.jobs.tick [--at ISO-TIME] [--dry-run]`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from campfinder.alerts import service as alerts
from campfinder.booking import reminders as registration_reminders
from campfinder.booking.service import local_tz
from campfinder.household.reminders import run_reminders as household_reminders

MORNING, EVENING = 7, 18


async def tick(now: datetime | None = None, dry_run: bool = False) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(local_tz())
    ran: dict[str, Any] = {"at": now.isoformat(), "local_hour": local.hour, "dry_run": dry_run}

    ran["registration_alerts"] = {k: v for k, v in (await alerts.run(now, dry_run)).items() if k != "emails"}
    if local.hour == MORNING:
        out = await registration_reminders.run(local.date(), dry_run)
        ran["registration_reminders"] = {k: v for k, v in out.items() if k != "emails"}
        ran["household_morning"] = len(await household_reminders(local.date(), dry_run=dry_run, slot="morning"))
    if local.hour == EVENING:
        ran["household_evening"] = len(await household_reminders(local.date(), dry_run=dry_run, slot="evening"))
    return ran


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run the hourly scheduled jobs once.")
    p.add_argument("--at", type=datetime.fromisoformat, help="Pretend it is this time (ISO, with offset).")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    print(json.dumps(asyncio.run(tick(args.at, args.dry_run)), default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
