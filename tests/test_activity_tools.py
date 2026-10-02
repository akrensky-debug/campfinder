import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from campfinder.activity.schedule import parse_date
from campfinder.agent import runner
from campfinder.agent.tools import ToolError, anthropic_tools, run_tool
from campfinder.main import create_app
from tests.fakes import FakeAnthropic, text_block, tool_use_block


def _offering(db, key):
    return next(o for o in db.tables["program_offerings"] if o["external_key"] == key)


async def test_find_activities_tool_cards_and_compact_content(seeded):
    out = await run_tool("find_activities", {"location": "Providence, RI", "age": 5, "interests": ["swim"],
                                             "days": ["weekdays"], "earliest_start": "3:30pm"})
    assert out.ui["type"] == "activities"
    card = out.ui["activities"][0]
    assert card["name"] == "Youth Swim Lessons" and card["per_class"] == 15
    assert card["offerings"][0]["schedule"] == "Tuesdays 4–4:30pm"
    assert card["offerings"][0]["enrollment_status"] == "open"
    assert out.content["activities"][0]["offerings"][0]["id"] == card["offerings"][0]["id"]


async def test_find_activities_no_results_logs_demand(seeded):
    out = await run_tool("find_activities", {"location": "Providence, RI", "interests": ["fencing"], "days": ["SU"]})
    assert out.content["activities"] == [] and "pilot" in out.content["note"]
    assert seeded.tables["activity_demand"][0]["days_of_week"] == ["SU"]


async def test_bad_day_is_a_tool_error(seeded):
    with pytest.raises(ToolError):
        await run_tool("find_activities", {"location": "Providence, RI", "days": ["Funday"]})


async def test_get_activity_details(seeded):
    pid = next(p["id"] for p in seeded.tables["programs"] if p["slug"] == "test-y-swim")
    out = await run_tool("get_activity_details", {"program_id": pid})
    assert out.content["kind"] == "lesson" and len(out.content["sessions"]) == 2
    assert out.ui["type"] == "activity_detail"


async def test_schedule_fit_against_family_calendar(seeded, family):
    tue = _offering(seeded, "stage2-tue-1600")
    first = parse_date(tue["start_date"])
    seeded.table("family_events").insert([
        {"family_id": family, "title": "Piano", "child_name": "Maya", "start_date": first.isoformat(),
         "end_date": (first + timedelta(weeks=10)).isoformat(), "rrule": "FREQ=WEEKLY;BYDAY=TU",
         "start_time": "15:45", "end_time": "16:15"},
        {"family_id": family, "title": "Soccer", "child_name": "Leo", "start_date": first.isoformat(),
         "end_date": (first + timedelta(weeks=10)).isoformat(), "rrule": "FREQ=WEEKLY;BYDAY=TU",
         "start_time": "16:40", "end_time": "17:30"},
    ]).execute()
    out = await run_tool("check_schedule_fit", {"offering_ids": [tue["id"]], "child_name": "Maya"}, family)
    r = out.content["results"][0]
    assert r["fits"] is False and r["meetings_left"] == 7
    assert sorted(c["severity"] for c in r["conflicts"]) == ["clash", "logistics"]
    assert out.ui["type"] == "schedule_fit"


async def test_schedule_fit_over_mcp_uses_given_commitments(seeded):
    tue = _offering(seeded, "stage2-tue-1600")
    out = await run_tool("check_schedule_fit", {
        "offering_ids": [tue["id"]], "child_name": "Maya",
        "commitments": [{"title": "School pickup", "child_name": "Leo", "days": ["weekdays"],
                         "start_time": "16:30", "end_time": "16:45"}]})
    r = out.content["results"][0]
    assert r["fits"] is True and [c["severity"] for c in r["conflicts"]] == ["logistics"]
    assert out.content["checked_against"] == "the commitments given"


async def test_schedule_fit_without_published_times(seeded):
    seeded.table("program_offerings").update({"start_time": None}).eq("external_key", "stage1-sat-0930").execute()
    sat = _offering(seeded, "stage1-sat-0930")
    out = await run_tool("check_schedule_fit", {"offering_ids": [sat["id"]]})
    assert out.content["results"][0]["fits"] is None


async def test_add_activity_and_custom_commitment_to_calendar_and_feed(seeded, family):
    tue = _offering(seeded, "stage2-tue-1600")
    out = await run_tool("add_activity_to_calendar", {"offering_id": tue["id"], "child_name": "Maya"}, family)
    assert out.content["added"] == "Maya: Youth Swim Lessons (Stage 2)"
    assert out.ui["type"] == "week"
    week_items = [i for d in out.ui["week"]["days"] for i in d["items"]]
    assert any(i["title"].startswith("Maya: Youth Swim") and i["time_label"] == "4–4:30pm" for i in week_items)

    out = await run_tool("add_activity_to_calendar", {
        "title": "Leo: school pickup", "child_name": "Leo", "days": ["weekdays"],
        "start_time": "16:20", "end_time": "16:40"}, family)
    assert [c["severity"] for c in out.content["conflicts"]] == ["logistics"]

    ev = seeded.tables["family_events"]
    assert ev[0]["rrule"] == "FREQ=WEEKLY;BYDAY=TU" and ev[0]["exdates"]
    client = TestClient(create_app())
    feed = client.get(f"/api/v1/calendar/{'t' * 32}.ics").text
    assert feed.count("BEGIN:VEVENT") == 2 and "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;UNTIL=" in feed
    assert "EXDATE;TZID=America/New_York" in feed and "LOCATION:1 Pool St\\, Providence" in feed


async def test_custom_commitment_needs_days_and_times(seeded, family):
    with pytest.raises(ToolError):
        await run_tool("add_activity_to_calendar", {"title": "Pickup"}, family)


async def test_remind_enrollment(seeded, family):
    pid = next(p["id"] for p in seeded.tables["programs"] if p["slug"] == "test-y-swim")
    out = await run_tool("remind_enrollment", {"program_id": pid, "child_name": "Maya"}, family)
    titles = [r["title"] for r in out.content["reminders"]]
    # Stage 2 closes before its first class; Winter opens in two weeks.
    assert any(t.startswith("Last day to register: Youth Swim Lessons (Fall Session)") for t in titles)
    assert any(t.startswith("Registration opens: Youth Swim Lessons (Winter Session)") for t in titles)
    feed = TestClient(create_app()).get(f"/api/v1/calendar/{'t' * 32}.ics").text
    assert "BEGIN:VALARM" in feed and "TRIGGER:-PT900M" in feed


async def test_remind_enrollment_with_no_dates(seeded, family):
    pid = next(p["id"] for p in seeded.tables["programs"] if p["slug"] == "test-pottery")
    out = await run_tool("remind_enrollment", {"program_id": pid}, family)
    assert out.content["added"] == 0 and "registration page" in out.content["note"]


async def test_family_week_tool_and_endpoint(seeded, family):
    tue = _offering(seeded, "stage2-tue-1600")
    await run_tool("add_activity_to_calendar", {"offering_id": tue["id"], "child_name": "Maya"}, family)
    week_of = parse_date(tue["start_date"])
    out = await run_tool("show_family_week", {"week_of": week_of.isoformat()}, family)
    assert "Tue" in out.content["days"] and out.ui["week"]["kids"] == ["Maya"]
    res = TestClient(create_app()).get(f"/api/v1/families/{family}/week", params={"week_of": week_of.isoformat()})
    assert res.status_code == 200 and res.json()["days"][1]["items"][0]["child_name"] == "Maya"


def test_family_tools_not_offered_without_family():
    names = {t["name"] for t in anthropic_tools(include_family=False)}
    assert {"find_activities", "check_schedule_fit"} <= names
    assert not {"add_activity_to_calendar", "remind_enrollment", "show_family_week"} & names


async def test_mcp_lists_activity_tools_with_parent_phrasing_and_widget(seeded):
    from campfinder.mcp_server import _widget_payload, mcp
    tools = {t.name: t for t in await mcp.list_tools()}
    assert "swim lessons near me for a 5 year old" in tools["find_activities"].description
    assert "Saturday soccer for kids in Cranston" in tools["find_activities"].description
    assert "add_activity_to_calendar" not in tools
    args = {"location": "Providence, RI", "age": 5, "interests": ["swim"]}
    out = await run_tool("find_activities", args)
    payload = _widget_payload("find_activities", args, out)
    assert payload["activities"][0]["url"].startswith("http") and "utm_campaign=activity_card" in payload["activities"][0]["url"]
    assert "activity_handoff" in payload["plan_url"]


async def test_agent_turn_runs_find_activities(seeded, family, monkeypatch):
    fake = FakeAnthropic([
        ([tool_use_block("find_activities", {"location": "Providence, RI", "age": 5, "interests": ["swim"],
                                             "days": ["weekdays"], "earliest_start": "15:30"})], "tool_use"),
        ([text_block("The Tuesday 4pm Stage 2 class fits.")], "end_turn"),
    ])
    monkeypatch.setattr(runner, "_client", lambda: fake)
    events = [e async for e in runner.run_agent(family, None, "swim lessons after 3:30 on weekdays for my 5 year old")]
    kinds = [e["type"] for e in events]
    assert kinds[0] == "conversation" and "ui" in kinds and kinds[-1] == "done"
    ui = next(e for e in events if e["type"] == "ui")["data"]
    assert ui["type"] == "activities" and ui["activities"][0]["name"] == "Youth Swim Lessons"
    # The system prompt covers year-round requests and the tool result went back to the model.
    assert "find_activities" in fake.requests[0]["system"]
    tool_results = [b for m in fake.requests[1]["messages"] if m["role"] == "user"
                    for b in m["content"] if b.get("type") == "tool_result"]
    result = json.loads(tool_results[0]["content"])
    assert result["activities"][0]["offerings"][0]["schedule"] == "Tuesdays 4–4:30pm"


async def test_ongoing_class_without_term_dates(seeded, family):
    seeded.table("program_offerings").update({"start_date": None, "end_date": None}).eq("external_key", "stage2-tue-1600").execute()
    tue = _offering(seeded, "stage2-tue-1600")
    fit = await run_tool("check_schedule_fit", {"offering_ids": [tue["id"]], "child_name": "Maya"}, family)
    r = fit.content["results"][0]
    assert r["fits"] is True and "Ongoing" in r["note"] and r["meetings_left"] is None
    out = await run_tool("add_activity_to_calendar", {"offering_id": tue["id"], "child_name": "Maya"}, family)
    ev = seeded.tables["family_events"][0]
    assert ev["rrule"] == "FREQ=WEEKLY;BYDAY=TU" and "Ongoing class" in ev["notes"]
    assert (parse_date(ev["end_date"]) - parse_date(ev["start_date"])).days > 150
    assert out.content["added"].startswith("Maya: Youth Swim Lessons")
