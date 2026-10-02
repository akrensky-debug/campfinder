"""The agent's household tools, driven through /agent/chat with a scripted fake Claude."""

from __future__ import annotations

import json

import pytest

from campfinder.agent import runner
from campfinder.agent.tools import CAMP_TOOLS, ToolError, run_tool
from tests.conftest import DAD, GRANDMA, OWNER, h, invite, join
from tests.fakes import Block, FakeAnthropic


def chat(client, family_id, user, message):
    res = client.post("/api/v1/agent/chat", headers=h(user), json={"family_id": family_id, "message": message})
    assert res.status_code == 200, res.text
    return [json.loads(line[6:]) for line in res.text.split("\n\n") if line.startswith("data: ")]


def use(monkeypatch, turns):
    fake = FakeAnthropic(turns)
    monkeypatch.setattr(runner, "_client", lambda: fake)
    return fake


def test_assign_tuesday_pickups_in_july_to_grandma(client, db, family, monkeypatch):
    fid = family["id"]
    gm = invite(client, fid, "Grandma", "grandma@example.com", "caregiver")
    join(client, gm, GRANDMA)
    gm_id = gm["member"]["id"]

    fake = use(monkeypatch, [
        [Block("tool_use", id="t1", name="generate_plan_tasks", input={"dropoff_time": "08:30", "pickup_time": "15:00"})],
        [Block("tool_use", id="t2", name="list_household", input={})],
        [Block("tool_use", id="t3", name="propose_assignment", input={
            "kinds": ["pickup"], "weekdays": ["tue"], "start": "2027-07-01", "end": "2027-07-31", "member_id": gm_id})],
        [Block("text", text="Here's the handoff for Grandma. Confirm and I'll let her know.")],
    ])
    events = chat(client, fid, OWNER, "Set up the rides, then give the Tuesday pickups in July to Grandma")

    proposal = next(e["data"] for e in events if e["type"] == "ui" and e["data"]["type"] == "assign_proposal")
    assert proposal["member"]["name"] == "Grandma" and len(proposal["task_ids"]) == 2
    assert all(t["kind"] == "pickup" for t in proposal["tasks"])

    # Proposed, not done: nothing is assigned until the parent confirms on the card.
    assert all(t["assignee_id"] is None for t in db.tables["family_tasks"])
    res = client.post(f"/api/v1/families/{fid}/tasks/assign", headers=h(OWNER),
                      json={"task_ids": proposal["task_ids"], "member_id": gm_id})
    assert res.status_code == 200
    mine = client.get(f"/api/v1/families/{fid}/tasks", headers=h(GRANDMA)).json()
    assert {t["due_date"] for t in mine} == {"2027-07-06", "2027-07-13"}

    # The model never sees email addresses or kit data; it does see the household.
    sent = json.dumps(fake.calls[-1]["messages"])
    assert "grandma@example.com" not in sent and "mom@example.com" not in sent
    assert "Household: Mom (owner), Grandma (caregiver)" in sent
    # Tasks created through the assistant are attributed to the parent, via the assistant.
    log = db.tables["family_audit_log"]
    created = next(e for e in log if e["action"] == "tasks_created")
    assert created["actor_name"] == "Mom" and created["via"] == "assistant"


def test_invite_and_message_are_only_proposed(client, db, family, monkeypatch, outbox):
    fid = family["id"]
    dad = invite(client, fid, "Dan", "dad@example.com", "co_parent")
    join(client, dad, DAD)
    outbox.clear()
    use(monkeypatch, [
        [Block("tool_use", id="a", name="propose_invite", input={"display_name": "Rosa", "role": "caregiver"})],
        [Block("tool_use", id="b", name="draft_household_message", input={
            "to": "everyone", "subject": "July pickups", "body": "Grandma has Tuesdays."})],
        [Block("text", text="Drafted.")],
    ])
    events = chat(client, fid, OWNER, "Invite our nanny Rosa and tell everyone the plan")
    ui = {e["data"]["type"]: e["data"] for e in events if e["type"] == "ui"}
    assert ui["invite_proposal"]["display_name"] == "Rosa" and ui["invite_proposal"]["email"] == ""
    assert [r["name"] for r in ui["message_draft"]["recipients"]] == ["Dan"]
    assert ui["message_draft"]["recipients"][0]["email"] == "dad@example.com"  # owner's own UI only
    assert outbox == []  # nothing went out
    assert not any(m["display_name"] == "Rosa" for m in db.tables["family_members"])

    # A co-parent can plan with the agent but not invite; the draft hides emails from them.
    use(monkeypatch, [
        [Block("tool_use", id="c", name="propose_invite", input={"display_name": "Rosa", "role": "caregiver"})],
        [Block("tool_use", id="d", name="draft_household_message", input={
            "to": "everyone", "subject": "Hi", "body": "Plan attached."})],
        [Block("text", text="ok")],
    ])
    events = chat(client, fid, DAD, "Invite Rosa")
    assert not any(e["type"] == "ui" and e["data"]["type"] == "invite_proposal" for e in events)
    draft = next(e["data"] for e in events if e["type"] == "ui" and e["data"]["type"] == "message_draft")
    assert draft["recipients"] == [{"name": "Mom", "email": None}]


def test_create_and_complete_tasks_via_agent(client, db, family, monkeypatch):
    fid = family["id"]
    use(monkeypatch, [
        [Block("tool_use", id="a", name="create_tasks", input={"tasks": [
            {"kind": "deadline", "title": "Registration opens: Lakeside", "due_date": "2027-01-15", "due_time": "09:00"},
            {"kind": "payment", "title": "Pay Riverside deposit", "due_date": "2027-02-01"},
        ]})],
        [Block("text", text="Added.")],
    ])
    chat(client, fid, OWNER, "Remind us when Lakeside registration opens and to pay the deposit")
    tasks = client.get(f"/api/v1/families/{fid}/tasks", headers=h(OWNER)).json()
    assert {t["kind"] for t in tasks} == {"deadline", "payment"}

    pay = next(t for t in tasks if t["kind"] == "payment")
    use(monkeypatch, [
        [Block("tool_use", id="b", name="update_tasks", input={"task_ids": [pay["id"]], "status": "done"})],
        [Block("tool_use", id="c", name="list_tasks", input={})],
        [Block("text", text="Done.")],
    ])
    events = chat(client, fid, OWNER, "I paid the deposit")
    listed = [e["data"] for e in events if e["type"] == "ui" and e["data"]["type"] == "tasks"][-1]
    assert [t["title"] for t in listed["tasks"]] == ["Registration opens: Lakeside"]


def test_household_tools_are_not_on_mcp():
    names = {t.name for t in CAMP_TOOLS}
    assert not names & {"list_tasks", "create_tasks", "propose_assignment", "list_household", "propose_invite"}


@pytest.mark.asyncio
async def test_household_tools_need_a_family():
    with pytest.raises(ToolError):
        await run_tool("list_tasks", {}, None)
