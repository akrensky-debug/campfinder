"""The hourly tick runs each scheduled job at the right local hour, behind the cron secret."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from campfinder.jobs import tick as tick_mod

NY = ZoneInfo("America/New_York")


@pytest.fixture
def calls(monkeypatch):
    seen: list[tuple[str, object]] = []

    async def alerts_run(now, dry_run=False):
        seen.append(("alerts", dry_run))
        return {"addresses_emailed": 0, "emails": []}

    async def registration_run(today, dry_run=False):
        seen.append(("registration", today))
        return {"families_emailed": 0, "emails": []}

    async def household(today, *, weekly=None, dry_run=False, slot=None):
        seen.append((f"household_{slot}", today))
        return []

    monkeypatch.setattr(tick_mod.alerts, "run", alerts_run)
    monkeypatch.setattr(tick_mod.registration_reminders, "run", registration_run)
    monkeypatch.setattr(tick_mod, "household_reminders", household)
    return seen


@pytest.mark.parametrize("hour,expected", [
    (3, ["alerts"]),
    (7, ["alerts", "registration", "household_morning"]),
    (12, ["alerts"]),
    (18, ["alerts", "household_evening"]),
])
async def test_jobs_run_at_their_local_hour(calls, hour, expected) -> None:
    out = await tick_mod.tick(datetime(2027, 1, 12, hour, 5, tzinfo=NY))   # winter: UTC-5
    assert [c[0] for c in calls] == expected and out["local_hour"] == hour


async def test_summer_time_is_local_too(calls) -> None:
    await tick_mod.tick(datetime(2027, 7, 12, 11, 5, tzinfo=ZoneInfo("UTC")))   # 7:05am EDT
    assert "household_morning" in [c[0] for c in calls]


def test_endpoint_needs_the_secret(client, calls, monkeypatch) -> None:
    url = "/api/v1/internal/cron/tick"
    assert client.post(url).status_code == 404
    monkeypatch.setenv("BOOKING_CRON_SECRET", "s3cret")
    assert client.post(url, headers={"X-Cron-Secret": "nope"}).status_code == 404
    res = client.post(url, params={"dry_run": True, "at": "2027-01-12T12:05:00+00:00"},
                      headers={"X-Cron-Secret": "s3cret"})
    assert res.status_code == 200 and res.json()["local_hour"] == 7 and res.json()["dry_run"] is True
    assert ("alerts", True) in calls
