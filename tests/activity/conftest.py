from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

import pytest

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from campfinder import database  # noqa: E402
from campfinder.activity import auth as activity_auth  # noqa: E402
from tests.fakes import FakeSupabase  # noqa: E402

API_KEY = "cfa_live_test_key_for_partner"


def _monday_after(d: date, weeks: int = 0) -> date:
    return d + timedelta(days=(7 - d.weekday()) % 7 or 7) + timedelta(weeks=weeks)


def make_dataset(today: date | None = None) -> dict[str, Any]:
    """A small synthetic dataset (not real providers) shaped like data/pilots/*.json,
    with dates relative to today so tests don't age out."""
    today = today or date.today()
    mon = _monday_after(today)
    tue, sat = mon + timedelta(days=1), mon + timedelta(days=5)
    src = "s1"
    f = lambda v: {"value": v, "source": src}  # noqa: E731
    return {
        "dataset": "test-swim",
        "category": "swimming",
        "researched_on": today.isoformat(),
        "verification_status": "unverified",
        "sources": {src: {"url": "https://example.org/swim", "title": "Test", "retrieved_on": today.isoformat()}},
        "programs": [
            {
                "slug": "test-y-swim",
                "kind": "lesson",
                "categories": ["swimming"],
                "name": f("Youth Swim Lessons"),
                "provider_name": f("Test YMCA"),
                "age_min": f(3),
                "age_max": f(12),
                "skill_levels": f(["Stage 1", "Stage 2"]),
                "trial_available": f(True),
                "registration_url": f("https://example.org/register"),
                "street_address": f("1 Pool St"),
                "city": f("Providence"),
                "state": f("RI"),
                "offerings": [
                    {
                        "key": "stage2-tue-1600",
                        "name": f("Stage 2 – Tuesdays 4pm"),
                        "term_name": f("Fall Session"),
                        "skill_level": f("Stage 2"),
                        "age_min": f(4),
                        "age_max": f(6),
                        "start_date": f(tue.isoformat()),
                        "end_date": f((tue + timedelta(weeks=7)).isoformat()),
                        "days": f(["TU"]),
                        "start_time": f("16:00"),
                        "end_time": f("16:30"),
                        "exdates": f([(tue + timedelta(weeks=2)).isoformat()]),
                        "class_count": f(7),
                        "enrollment_opens": f((today - timedelta(days=10)).isoformat()),
                        "enrollment_closes": f((tue - timedelta(days=1)).isoformat()),
                        "availability": f("open"),
                        "prices": [
                            {"type": "full_term", "amount": f(105), "audience": "member"},
                            {"type": "full_term", "amount": f(140), "audience": "non-member"},
                        ],
                    },
                    {
                        "key": "stage1-sat-0930",
                        "name": f("Stage 1 – Saturdays 9:30am"),
                        "term_name": f("Winter Session"),
                        "skill_level": f("Stage 1"),
                        "start_date": f((sat + timedelta(weeks=4)).isoformat()),
                        "end_date": f((sat + timedelta(weeks=11)).isoformat()),
                        "days": f(["SA"]),
                        "start_time": f("09:30"),
                        "end_time": f("10:00"),
                        "enrollment_opens": f((today + timedelta(days=14)).isoformat()),
                        "prices": [{"type": "full_term", "amount": f(160)}],
                    },
                ],
            },
            {
                "slug": "test-swim-school",
                "kind": "lesson",
                "categories": ["swimming"],
                "name": f("Group Swim Lessons"),
                "provider_name": f("Test Swim School"),
                "age_min": f(1),
                "age_max": f(10),
                "city": f("Cranston"),
                "state": f("RI"),
                "prices": [{"type": "monthly", "amount": f(150), "covers": "4 lessons"}],
            },
            {
                "slug": "test-pottery",
                "kind": "class",
                "categories": ["arts"],
                "name": f("Kids Pottery"),
                "provider_name": f("Test Clay Studio"),
                "age_min": f(6),
                "age_max": f(12),
                "city": f("Pawtucket"),
                "state": f("RI"),
                "offerings": [
                    {
                        "key": "wed-1530",
                        "start_date": f((mon + timedelta(days=2)).isoformat()),
                        "end_date": f((mon + timedelta(days=2, weeks=5)).isoformat()),
                        "days": f(["WE"]),
                        "start_time": f("15:30"),
                        "end_time": f("17:00"),
                        "prices": [{"type": "per_class", "amount": f(30)}, {"type": "trial", "amount": f(0)}],
                    }
                ],
            },
        ],
    }


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeSupabase:
    fake = FakeSupabase()
    monkeypatch.setattr(database, "_supabase", fake)
    activity_auth._client_cache.clear()
    activity_auth._windows.clear()
    fake.tables["api_clients"] = [{
        "id": "client-1", "name": "Partner", "key_hash": activity_auth.hash_key(API_KEY),
        "rate_limit_per_minute": 1000, "active": True,
    }]
    return fake


@pytest.fixture
def seeded(db: FakeSupabase) -> FakeSupabase:
    from campfinder.activity.importer import apply_plan, plan_dataset
    apply_plan(db, plan_dataset(make_dataset()))
    return db


@pytest.fixture
def family(db: FakeSupabase) -> str:
    row = db.table("families").insert({"profile": {"home_location": "Providence, RI"}}).execute().data[0]
    return row["id"]
