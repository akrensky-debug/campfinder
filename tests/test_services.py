"""Pure logic: ranking, planning, freshness, limiter."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from campfinder.security import SlidingWindowLimiter, hash_token, new_token
from campfinder.services.freshness import compute_freshness_grade
from campfinder.services.planning import build_plan
from campfinder.services.ranking import score_camp


def test_score_camp_reasons() -> None:
    camp = {"age_min": 6, "age_max": 12, "primary_categories": ["STEM"], "price_per_week": 300,
            "description_short": "x", "verification_status": "camp_verified",
            "updated_at": datetime.now(timezone.utc)}
    sessions = [{"start_date": date(2027, 7, 5), "end_date": date(2027, 7, 9)}]
    score, reasons = score_camp(camp, sessions, age=8, requested_weeks=["2027-07-05"], categories=["stem"],
                                distance_miles=5, max_price_per_week=400)
    assert score > 1.8
    assert "Matches age 8" in reasons
    assert "Has Jul sessions" in reasons
    assert "Verified listing" in reasons


def test_build_plan_counts_each_session_once() -> None:
    sessions = [
        {"id": "s1", "camp_id": "c1", "camp_name": "A", "start_date": date(2027, 7, 5), "end_date": date(2027, 7, 16), "price": 700},
        {"id": "s2", "camp_id": "c2", "camp_name": "B", "start_date": date(2027, 7, 12), "end_date": date(2027, 7, 16), "price": 300},
    ]
    plan = build_plan(sessions, date(2027, 7, 5), date(2027, 7, 25))
    assert plan["weeks_total"] == 3
    assert [w["status"] for w in plan["weeks"]] == ["covered", "overlap", "gap"]
    assert plan["total_estimated_cost"] == 1000


def test_freshness_grades() -> None:
    now = datetime.now(timezone.utc)
    assert compute_freshness_grade(now) == "current"
    assert compute_freshness_grade(now - timedelta(days=45)) == "aging"
    assert compute_freshness_grade(now - timedelta(days=120)) == "stale"
    assert compute_freshness_grade(None) == "stale"


def test_tokens_are_random_and_hashed() -> None:
    a, b = new_token(), new_token()
    assert a != b and len(a) >= 40
    assert hash_token(a) != a and len(hash_token(a)) == 64


def test_sliding_window_limiter() -> None:
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)
    assert limiter.allow("ip", now=0) and limiter.allow("ip", now=1)
    assert not limiter.allow("ip", now=2)
    assert limiter.allow("other", now=2)
    assert limiter.allow("ip", now=61)
