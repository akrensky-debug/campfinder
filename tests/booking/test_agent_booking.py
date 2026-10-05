from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from campfinder.agent import runner
from campfinder.agent.tools import ALL_TOOLS
from tests.booking.conftest import CAMP, OWNER, SESSION, h, window
from tests.fakes import Block, FakeAnthropic, FakeSupabase

KIT_SECRETS = ("Peanuts", "XJ-55521", "401-555", "2018-04-02", "Rosa Silva", "Blue Cross")


def chat(client: TestClient, fam: dict[str, Any], fake: FakeAnthropic, monkeypatch: pytest.MonkeyPatch,
         message: str) -> list[dict[str, Any]]:
    monkeypatch.setattr(runner, "_client", lambda: fake)
    res = client.post("/api/v1/agent/chat", headers=h(OWNER), json={"family_id": fam["id"], "message": message})
    assert res.status_code == 200
    return [json.loads(line[6:]) for line in res.text.splitlines() if line.startswith("data: ")]


def test_agent_can_propose_but_not_share(client: TestClient, db: FakeSupabase, family: dict[str, Any],
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    window(db, 2)
    fake = FakeAnthropic([
        [Block("tool_use", id="t1", name="watch_registration",
               input={"camp_id": CAMP, "session_id": SESSION, "child_name": "Maya"})],
        [Block("tool_use", id="t2", name="propose_registration_package", input={"camp_id": CAMP, "child_name": "Maya"}),
         Block("tool_use", id="t3", name="registration_checklist", input={"camp_id": CAMP, "child_name": "Maya"})],
        [Block("tool_use", id="t4", name="share_info_kit", input={"camp_id": CAMP})],  # no such tool
        [Block("text", text="I've set it up. Review the package card and press Share when you're ready.")],
    ])
    events = chat(client, family, fake, monkeypatch, "Get Maya ready for Riverside registration and send them her info")

    ui = [e["data"]["type"] for e in events if e["type"] == "ui"]
    assert ui == ["registrations", "registration_package", "register_checklist"]
    assert not db.tables.get("kit_shares")  # nothing was shared
    assert len(db.tables["family_registrations"]) == 1

    sent_to_model = json.dumps(fake.calls[-1]["messages"])
    for secret in KIT_SECRETS:
        assert secret not in sent_to_model
    assert "Nothing has been shared" in sent_to_model
    assert "Unknown tool: share_info_kit" in sent_to_model
    assert "Grade in the fall" in sent_to_model  # it may know which answers are missing


def test_agent_records_what_parent_reports(client: TestClient, db: FakeSupabase, family: dict[str, Any],
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    rid = client.post(f"/api/v1/families/{family['id']}/registrations", headers=h(OWNER),
                      json={"camp_id": CAMP, "session_id": SESSION, "child_name": "Maya"}).json()["id"]
    fake = FakeAnthropic([
        [Block("tool_use", id="t1", name="record_registration", input={
            "registration_id": rid, "status": "registered", "payment_status": "deposit", "amount_paid": 100,
            "balance_due": 325, "payment_due_date": "2027-05-01"})],
        [Block("text", text="Recorded. I'll remind you before May 1.")],
    ])
    chat(client, family, fake, monkeypatch, "I got Maya in! Paid the $100 deposit, rest due May 1")
    reg = db.tables["family_registrations"][0]
    assert reg["status"] == "registered" and reg["balance_due"] == 325
    assert {e["title"] for e in db.tables["family_events"]} == {
        "Maya: Riverside Soccer Camp", "Payment due: Riverside Soccer Camp ($325)"}
    # The registration shows up in the agent's context on a new conversation.
    assert "Registrations:" in fake.calls[0]["messages"][0]["content"][0]["text"]


def test_no_agent_tool_can_share_book_or_pay() -> None:
    import campfinder.agent.booking_tools as bt

    source = open(bt.__file__).read()
    for forbidden in ("confirm_package", "create_share", "bookings", "providers", "stripe"):
        assert forbidden not in source
    for name in ALL_TOOLS:
        assert not any(w in name for w in ("share", "book", "pay", "submit"))
