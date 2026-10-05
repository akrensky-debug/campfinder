"""Camp search, detail, compare and plan live in services; routers and tools are thin callers."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from campfinder.agent.tools import ToolError, run_tool
from campfinder.models.compare import CompareRequest
from campfinder.models.plan import PlanRequest
from campfinder.services import camps, compare, plan
from campfinder.services.errors import NotFound

ROOT = Path(__file__).resolve().parents[1] / "campfinder"
OPEN, CLOSED, GONE = ("aaaaaaaa-0000-0000-0000-00000000000%d" % i for i in (1, 2, 3))
WEEK_1, WEEK_2 = "bbbbbbbb-0000-0000-0000-000000000001", "bbbbbbbb-0000-0000-0000-000000000002"


def test_only_the_api_layer_imports_routers() -> None:
    """The agent, MCP server, Activity API and services must not depend on router signatures."""
    offenders = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("routers/") or rel == "main.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            names = [node.module or ""] if isinstance(node, ast.ImportFrom) else \
                [a.name for a in node.names] if isinstance(node, ast.Import) else []
            if any(n == "campfinder.routers" or n.startswith("campfinder.routers.") for n in names):
                offenders.append(rel)
    assert offenders == []


@pytest.fixture
def listed(db):
    base = {"city": "Providence", "state": "RI", "zip": "02906", "camp_type": "day", "verification_status": "team_verified"}
    db.table("camps").insert([
        {**base, "id": OPEN, "name": "Riverside Soccer", "is_active": True, "price_per_week": 300},
        {**base, "id": CLOSED, "name": "Taken Down Arts", "is_active": False},
    ]).execute()
    db.table("sessions").insert([
        {"id": WEEK_1, "camp_id": OPEN, "name": "Week 1", "start_date": "2027-07-05", "end_date": "2027-07-09", "price": 300},
        {"id": WEEK_2, "camp_id": OPEN, "name": "Week 2", "start_date": "2027-07-12", "end_date": "2027-07-16", "price": 300},
    ]).execute()
    return db


def test_detail(listed) -> None:
    detail = camps.get_camp_detail(OPEN)
    assert detail.name == "Riverside Soccer" and [s.name for s in detail.sessions] == ["Week 1", "Week 2"]
    for missing in (CLOSED, GONE):
        with pytest.raises(NotFound):
            camps.get_camp_detail(missing)


def test_compare_leaves_out_taken_down_camps(listed) -> None:
    with pytest.raises(NotFound, match=CLOSED):
        compare.compare_camps(CompareRequest(camp_ids=[OPEN, CLOSED]))


def test_plan(listed) -> None:
    res = plan.build_summer_plan(PlanRequest(
        camp_sessions=[{"camp_id": OPEN, "session_id": WEEK_1}, {"camp_id": OPEN, "session_id": WEEK_2}],
        summer_start="2027-07-05", summer_end="2027-07-16"))
    assert res.weeks_covered == 2 and res.total_estimated_cost == 600
    with pytest.raises(NotFound):
        plan.build_summer_plan(PlanRequest(camp_sessions=[{"camp_id": OPEN, "session_id": GONE}],
                                           summer_start="2027-07-05", summer_end="2027-07-16"))


def test_api_and_tools_report_not_found_their_own_way(listed, client) -> None:
    res = client.get(f"/api/v1/camps/{CLOSED}")
    assert res.status_code == 404 and res.json() == {"detail": "Camp not found"}
    res = client.post("/api/v1/compare", json={"camp_ids": [OPEN, GONE]})
    assert res.status_code == 404 and GONE in res.json()["detail"]
    assert client.get(f"/api/v1/camps/{OPEN}").json()["name"] == "Riverside Soccer"


async def test_agent_tool_turns_not_found_into_a_message(listed) -> None:
    with pytest.raises(ToolError, match="Camp not found"):
        await run_tool("get_camp_details", {"camp_id": CLOSED})
    out = await run_tool("get_camp_details", {"camp_id": OPEN})
    assert out.content["name"] == "Riverside Soccer"
