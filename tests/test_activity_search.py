from datetime import date, timedelta

from fastapi.testclient import TestClient

from campfinder.activity import programs as activities
from campfinder.activity.schedule import TimeWindow
from campfinder.main import create_app
from tests.conftest import API_KEY

AUTH = {"Authorization": f"Bearer {API_KEY}"}


def _search(db, **kw):
    return activities.search_activities(db, activities.ActivityQuery(location="Providence, RI", **kw))


def test_search_by_interest_and_age(seeded):
    names = [r["name"] for r in _search(seeded, interests=["swim"], age=5)]
    assert set(names) == {"Youth Swim Lessons", "Group Swim Lessons"}
    assert [r["name"] for r in _search(seeded, interests=["art"], age=8)] == ["Kids Pottery"]
    assert _search(seeded, interests=["art"], age=4) == []


def test_offering_level_ages_filter_offerings(seeded):
    # Program is 3-12, but the Tuesday Stage 2 class is 4-6.
    r = _search(seeded, interests=["swim"], age=9, window=TimeWindow.build(["TU"]))
    assert r == []
    r = _search(seeded, interests=["swim"], age=5, window=TimeWindow.build(["TU"]))
    assert [o["external_key"] for o in r[0]["offerings"]] == ["stage2-tue-1600"]


def test_time_windows_after_school_and_saturday_mornings(seeded):
    after = _search(seeded, window=TimeWindow.build(["weekdays"], "15:30"))
    assert {r["name"] for r in after} == {"Youth Swim Lessons", "Kids Pottery"}
    sat = _search(seeded, window=TimeWindow.build(["Saturday"], time_of_day="morning"))
    assert [o["external_key"] for o in sat[0]["offerings"]] == ["stage1-sat-0930"]
    # Programs without a published schedule drop out once a schedule is required.
    assert "Group Swim Lessons" not in {r["name"] for r in sat}


def test_price_and_distance_filters(seeded):
    # Stage 2: $105 / 7 classes = $15 a class; pottery $30 a class
    cheap = _search(seeded, max_price_per_class=20, window=TimeWindow.build(["weekdays"]))
    assert [r["name"] for r in cheap] == ["Youth Swim Lessons"]
    assert all(r["distance_miles"] <= 3 for r in _search(seeded, radius_miles=3))
    assert "Kids Pottery" not in {r["name"] for r in _search(seeded, radius_miles=3)}


def test_reasons_explain_the_fit(seeded):
    r = _search(seeded, interests=["swim"], age=5, window=TimeWindow.build(["weekdays"], "15:30"))[0]
    text = " | ".join(r["match_reasons"])
    assert "Ages 4–6 fits a 5-year-old" in text
    assert "Tuesdays 4–4:30pm" in text and "after 3:30pm" in text
    assert "From $15 a class" in text and "Enrollment open until" in text
    assert "Trial class available" in text and "Not yet verified" in text


def test_term_filter(seeded):
    r = _search(seeded, term="winter")
    assert [o["term_name"] for o in r[0]["offerings"]] == ["Winter Session"]


def test_activity_api_programs_merge_and_kind(seeded):
    client = TestClient(create_app())
    res = client.get("/api/activity/v1/programs", params={"near": "Providence, RI", "kind": "lesson",
                                                          "include_sessions": True}, headers=AUTH)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["schema_version"] == "2026-10-02" and body["total"] == 2
    y = next(p for p in body["data"] if p["name"] == "Youth Swim Lessons")
    assert y["kind"] == "lesson" and y["trial_available"] is True and y["price"]["per_class"] == 15
    s = next(s for s in y["sessions"] if s["skill_level"] == "Stage 2")
    assert s["schedule"]["days_of_week"] == ["TU"] and s["schedule"]["start_time"] == "16:00"
    assert s["schedule"]["meeting_count"] == 7 and s["enrollment"]["status"] == "open"
    assert {p["audience"] for p in s["prices"]} == {"member", "non-member"}
    assert "registration_url" not in y["verification"]["fields_missing"]
    # schedule filters through the API
    res = client.get("/api/activity/v1/programs", params={"near": "Providence, RI", "day": ["weekdays"],
                                                          "earliest_start": "15:30"}, headers=AUTH)
    assert {p["name"] for p in res.json()["data"]} == {"Youth Swim Lessons", "Kids Pottery"}
    # bad day is a 422, not a 500
    bad = client.get("/api/activity/v1/programs", params={"near": "Providence, RI", "day": "someday"}, headers=AUTH)
    assert bad.status_code == 422


def test_activity_api_program_detail_and_recurring_ics(seeded):
    client = TestClient(create_app())
    pid = next(p["id"] for p in seeded.tables["programs"] if p["slug"] == "test-y-swim")
    detail = client.get(f"/api/activity/v1/programs/{pid}", headers=AUTH).json()["data"]
    tue = next(s for s in detail["sessions"] if s["skill_level"] == "Stage 2")
    ics = client.get(f"/api/activity/v1/sessions/{tue['id']}.ics").text
    assert "RRULE:FREQ=WEEKLY;BYDAY=TU;UNTIL=" in ics
    assert "DTSTART;TZID=America/New_York:" in ics and "T160000" in ics
    assert "EXDATE;TZID=America/New_York:" in ics and "BEGIN:VTIMEZONE" in ics


def test_sessions_window_includes_terms_when_asked(seeded):
    client = TestClient(create_app())
    res = client.get("/api/activity/v1/sessions", params={
        "near": "Providence, RI", "kind": "lesson",
        "starts_on_or_after": (date.today() + timedelta(days=20)).isoformat()}, headers=AUTH)
    assert res.status_code == 200, res.text
    assert [m["session"]["term"] for m in res.json()["data"]] == ["Winter Session"]


def test_demand_accepts_days_and_times(db):
    client = TestClient(create_app())
    res = client.post("/api/activity/v1/demand", json={
        "location": "Providence, RI", "ages": [5], "kinds": ["lesson"], "categories": ["swimming"],
        "days_of_week": ["SA"], "latest_end": "12:00", "results_shown": 0, "satisfied": False}, headers=AUTH)
    assert res.status_code == 202
    assert db.tables["activity_demand"][0]["days_of_week"] == ["SA"]


def test_per_class_price_is_never_estimated(seeded):
    seeded.table("program_offerings").update({"class_count": None}).eq("external_key", "stage2-tue-1600").execute()
    r = _search(seeded, interests=["swim"], age=5, window=TimeWindow.build(["TU"]))[0]
    assert activities.per_class_price(r, r["offerings"][0]) is None
    assert "From $105 a term" in r["match_reasons"]


def test_town_level_distance_wording(seeded):
    r = _search(seeded, interests=["swim"], age=5)
    reasons = {x["name"]: x["match_reasons"] for x in r}
    assert "In Providence" in reasons["Youth Swim Lessons"]
    assert any(m.startswith("About 3 mi from Providence (Cranston)") for m in reasons["Group Swim Lessons"])
