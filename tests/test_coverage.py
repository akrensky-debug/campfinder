"""Summer coverage: work hours, vacations and the family calendar, week by week."""

from __future__ import annotations

from datetime import date, time
from typing import Any

from campfinder.agent import tools
from campfinder.models.coverage import WorkBlock
from campfinder.seed.import_real import build_rows, load_dataset
from campfinder.services.coverage import care_windows, compute_coverage, week_options

WORK = [
    {"parent": "Mom", "days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "start": "8:30", "end": "5pm"},
    {"parent": "Dad", "days": ["Mon", "Tue", "Wed", "Thu"], "start": "9:00", "end": "17:30"},
]
DAY_CAMP_EXT = "11111111-1111-1111-1111-111111111111"
DAY_CAMP_NO_EXT = "22222222-2222-2222-2222-222222222222"
SLEEPAWAY = "33333333-3333-3333-3333-333333333333"
CAMPS = {
    DAY_CAMP_EXT: {"id": DAY_CAMP_EXT, "camp_type": "day", "extended_care": True},
    DAY_CAMP_NO_EXT: {"id": DAY_CAMP_NO_EXT, "camp_type": "day", "extended_care": False},
    SLEEPAWAY: {"id": SLEEPAWAY, "camp_type": "sleepaway", "extended_care": None},
}


def profile(**extra: Any) -> dict[str, Any]:
    return {
        "kids": [{"name": "Maya", "age": 8}, {"name": "Leo", "age": 11}],
        "home_location": "Providence, RI",
        "summer_start": "2027-06-21",
        "summer_end": "2027-08-13",
        "work_schedule": WORK,
        "away": [
            {"start_date": "2027-07-26", "end_date": "2027-07-30", "label": "Cape Cod"},
            {"start_date": "2027-08-02", "end_date": "2027-08-06", "label": "Week at Grandma's", "child_name": "Maya"},
        ],
        **extra,
    }


def event(title: str, start: str, end: str, child: str = "Maya", **kw: Any) -> dict[str, Any]:
    return {"title": title, "start_date": start, "end_date": end, "child_name": child, **kw}


EVENTS = [
    event("Bayside Y", "2027-06-21", "2027-06-25", camp_id=DAY_CAMP_EXT),
    event("Farm camp", "2027-06-28", "2027-07-02", camp_id=DAY_CAMP_NO_EXT),
    event("Camp JORI", "2027-07-05", "2027-07-10", camp_id=SLEEPAWAY),
    event("Art week", "2027-07-12", "2027-07-16", kind="camp", start_time="09:00", end_time="15:00"),
    event("Leo soccer", "2027-07-05", "2027-12-31", child="Leo", kind="activity", rrule="FREQ=WEEKLY;BYDAY=TU",
          start_time="17:00", end_time="18:00"),
]


def weeks_by_start(result: Any, kid: str) -> dict[str, Any]:
    k = next(k for k in result.kids if k.name == kid)
    return {w.week_of.isoformat(): w for w in k.weeks}


def test_care_hours_are_when_every_parent_is_at_work() -> None:
    windows = care_windows([WorkBlock.model_validate(w) for w in WORK])
    assert windows["Mon"] == (time(9, 0), time(17, 0))
    assert windows["Fri"] is None  # Dad is home on Fridays
    assert windows["Sat"] is None


def test_weeks_are_covered_checked_partial_open_or_away() -> None:
    result = compute_coverage(profile(), EVENTS, CAMPS)
    assert result.care_hours == {d: "9:00-17:00" for d in ("Mon", "Tue", "Wed", "Thu")}
    maya = weeks_by_start(result, "Maya")

    # Camp with extended care listed: counted, but the hours need confirming.
    assert maya["2027-06-21"].status == "check_hours"
    assert "offers extended care" in maya["2027-06-21"].check_hours[0]
    # Camp without extended care can't cover 9-5.
    assert maya["2027-06-28"].status == "partial"
    # Sleepaway covers the whole week.
    assert maya["2027-07-05"].status == "covered"
    # A 9-3 camp leaves 3-5 uncovered each workday.
    art = maya["2027-07-12"]
    assert art.status == "partial" and art.gaps[0].uncovered == "15:00-17:00" and art.days_needed == 4
    # Nothing booked.
    assert maya["2027-07-19"].status == "open" and len(maya["2027-07-19"].gaps) == 4
    # Family vacation, and Maya's week at Grandma's.
    assert maya["2027-07-26"].status == "away" and maya["2027-07-26"].away == ["Cape Cod"]
    assert maya["2027-08-02"].status == "away"

    # Leo's weekly soccer practice is not childcare; Grandma's week is Maya's only.
    leo = weeks_by_start(result, "Leo")
    assert leo["2027-07-05"].status == "open"
    assert leo["2027-08-02"].status == "open"
    assert leo["2027-07-26"].status == "away"


def test_without_work_hours_every_weekday_needs_care_but_hours_are_not_checked() -> None:
    result = compute_coverage(profile(work_schedule=[]), EVENTS, CAMPS)
    maya = weeks_by_start(result, "Maya")
    assert maya["2027-06-28"].status == "covered"
    assert maya["2027-07-12"].status == "covered"
    assert maya["2027-07-19"].days_needed == 5
    assert result.care_hours == {} and result.notes


def test_options_use_real_camps_and_fall_back_to_last_season() -> None:
    camps, sessions, _ = build_rows(load_dataset())
    by_camp: dict[str, list[dict[str, Any]]] = {}
    for s in sessions:
        by_camp.setdefault(s["camp_id"], []).append(s)
    rows = [{**c, "sessions": by_camp.get(c["id"], [])} for c in camps if c["region"] == "Providence, RI"]

    opts = week_options(rows, date(2027, 7, 19), (time(8, 0), time(17, 30)))
    assert len(opts) == 3
    assert all(o.extended_care for o in opts)  # long workday: extended care first
    # This season's posted dates rank first; camps without 2027 dates fall back to the same
    # week last season, marked as such.
    flags = [o.last_season for o in opts]
    assert flags == sorted(flags)
    assert all(o.start_date.year == (2026 if o.last_season else 2027) for o in opts)
    assert any(o.last_season for o in opts)

    # Camps that already posted 2027 dates are offered as this season's sessions.
    posted = week_options(rows, date(2027, 6, 28), None, limit=50)
    assert any(not o.last_season and o.start_date.year == 2027 for o in posted)


async def test_coverage_tool_reads_the_family_and_suggests_camps(db: Any) -> None:
    fam = "44444444-4444-4444-4444-444444444444"
    db.table("families").insert({"id": fam, "profile": profile()}).execute()
    db.table("family_events").insert([{**e, "family_id": fam} for e in EVENTS]).execute()
    db.table("camps").insert([
        {**CAMPS[DAY_CAMP_EXT], "name": "Bayside Y", "city": "Barrington", "state": "RI", "is_active": True,
         "age_min": 5, "age_max": 14, "region": "Providence, RI"},
        {"id": "55555555-5555-5555-5555-555555555555", "name": "Kent County Y", "city": "Warwick", "state": "RI",
         "camp_type": "day", "extended_care": True, "is_active": True, "age_min": 5, "age_max": 14},
    ]).execute()
    db.table("sessions").insert([
        {"id": "66666666-6666-6666-6666-666666666666", "camp_id": "55555555-5555-5555-5555-555555555555",
         "name": "Week 5", "start_date": "2027-07-19", "end_date": "2027-07-23", "availability": "open"},
    ]).execute()

    out = await tools.run_tool("check_summer_coverage", {}, family_id=fam)
    assert out.ui and out.ui["type"] == "coverage"
    maya = next(k for k in out.content["kids"] if k["name"] == "Maya")
    july19 = next(w for w in maya["weeks"] if w["week_of"] == "2027-07-19")
    assert july19["status"] == "open"
    assert july19["options"][0]["name"] == "Kent County Y" and not july19["options"][0]["last_season"]


async def test_profile_saves_work_hours_and_trips(db: Any) -> None:
    fam = "77777777-7777-7777-7777-777777777777"
    db.table("families").insert({"id": fam, "profile": {}}).execute()
    await tools.run_tool("update_family_profile", {"work_schedule": WORK, "away": profile()["away"]}, family_id=fam)
    saved = db.table("families").select("profile").eq("id", fam).execute().data[0]["profile"]
    assert saved["work_schedule"][0]["parent"] == "Mom"
    assert saved["away"][1]["child_name"] == "Maya"


def test_coverage_is_family_only() -> None:
    spec = tools.ALL_TOOLS["check_summer_coverage"]
    assert spec.family
    assert "check_summer_coverage" not in {t.name for t in tools.CAMP_TOOLS}
