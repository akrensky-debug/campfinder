"""Family data export: everything we hold, to the owner only, with link secrets left out."""

from __future__ import annotations

import base64
import json
import os

import pytest

from campfinder.config import get_settings
from tests.conftest import DAD, OWNER, STRANGER, h, invite, join

KIT = {
    "household": {"parents": [{"name": "Ana Silva", "phone": "401-555-0100"}], "emergency_contacts": [],
                  "authorized_pickups": [], "insurance_provider": "Blue Cross RI"},
    "children": [{"name": "Maya", "allergies": "Peanuts (EpiPen)"}],
}


@pytest.fixture(autouse=True)
def kit_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "kit_encryption_key", base64.urlsafe_b64encode(os.urandom(32)).decode())


def test_owner_downloads_everything(client, db, family):
    fid = family["id"]
    assert client.put(f"/api/v1/families/{fid}/kit", json=KIT, headers=h(OWNER)).status_code == 200
    join(client, invite(client, fid, "Dan", "dad@example.com", "co_parent"), DAD)
    members = client.get(f"/api/v1/families/{fid}/household", headers=h(OWNER)).json()["members"]
    mom = next(m for m in members if m["display_name"] == "Mom")
    dan = next(m for m in members if m["display_name"] == "Dan")
    db.table("agent_conversations").insert([
        {"family_id": fid, "started_by": mom["id"], "messages": [{"role": "user", "content": "mom's plan"}]},
        {"family_id": fid, "started_by": None, "messages": [{"role": "user", "content": "older chat"}]},
        {"family_id": fid, "started_by": dan["id"], "messages": [{"role": "user", "content": "dan's private chat"}]},
    ]).execute()
    # Mom typed a neighbour's address as her reminder email; nothing verified it.
    db.table("registration_reminder_prefs").insert({"family_id": fid, "email": "neighbour@example.com"}).execute()
    share = client.post(f"/api/v1/families/{fid}/kit/shares", headers=h(OWNER), json={
        "recipient": "Riverside Soccer", "children": ["Maya"], "child_fields": ["allergies"]}).json()
    share_token = share["url"].rsplit("/", 1)[1]
    assert client.get(f"/api/v1/shares/{share_token}").status_code == 200       # the camp opens it once
    db.table("registration_alerts").insert([
        {"camp_id": "11111111-1111-1111-1111-111111111111", "email": "mom@example.com", "token": "alert-secret",
         "confirmed_at": "2026-10-01T00:00:00+00:00"},
        {"camp_id": "11111111-1111-1111-1111-111111111111", "email": "someone@else.com", "token": "x"},
        {"camp_id": "11111111-1111-1111-1111-111111111111", "email": "neighbour@example.com", "token": "y",
         "confirmed_at": "2026-10-02T00:00:00+00:00"},
    ]).execute()

    res = client.get(f"/api/v1/families/{fid}/export", headers=h(OWNER))
    assert res.status_code == 200
    assert res.headers["content-disposition"].startswith('attachment; filename="campfinder-family-')
    assert res.headers["cache-control"] == "private, no-store"
    data = res.json()

    assert data["format"] == "campfinder-family-export" and data["family"]["account_email"] == "mom@example.com"
    assert data["family"]["profile"]["kids"][0]["name"] == "Maya"
    assert data["info_kit"]["children"][0]["allergies"] == "Peanuts (EpiPen)"     # decrypted, for the owner
    assert len(data["calendar_events"]) == 2
    assert {m["display_name"] for m in data["household"]["members"]} == {"Mom", "Dan"}
    # Only her own, verified address: not the neighbour's sign-ups, even though she typed it in.
    assert [a["email"] for a in data["registration_alerts"]] == ["mom@example.com"]
    assert "neighbour@example.com" not in [a["email"] for a in data["registration_alerts"]]
    # Her own chats and the older ones, never Dan's.
    said = [c["messages"][0]["content"] for c in data["conversations"]]
    assert sorted(said) == ["mom's plan", "older chat"] and "dan's private chat" not in res.text
    assert data["not_included"]
    assert data["info_kit_shares"]["links"][0]["recipient"] == "Riverside Soccer"
    assert data["info_kit_shares"]["links"][0]["open_count"] == 1 and data["info_kit_shares"]["opens"]

    # No secrets anywhere in the file.
    raw = res.text
    family_row = db.tables["families"][0]
    for secret in [family_row["calendar_token"], "alert-secret", share_token,
                   db.tables["kit_shares"][0]["token_hash"],
                   *(m.get("calendar_token") for m in db.tables["family_members"]),
                   *(m.get("invite_token_hash") for m in db.tables["family_members"]),
                   db.tables["family_kits"][0]["ciphertext"]]:
        if secret:
            assert secret not in raw
    assert "token" not in json.dumps(list(data["family"]))

    # The download is in the family's activity log.
    actions = [e["action"] for e in client.get(f"/api/v1/families/{fid}/audit", headers=h(OWNER)).json()]
    assert "family_exported" in actions


def test_only_the_owner_can_export(client, family):
    fid = family["id"]
    join(client, invite(client, fid, "Dan", "dad@example.com", "co_parent"), DAD)
    assert client.get(f"/api/v1/families/{fid}/export", headers=h(DAD)).status_code == 403
    assert client.get(f"/api/v1/families/{fid}/export", headers=h(STRANGER)).status_code == 403
    assert client.get(f"/api/v1/families/{fid}/export").status_code == 401


def test_guest_family_exports_without_a_kit(client):
    fam = client.post("/api/v1/families").json()
    data = client.get(f"/api/v1/families/{fam['id']}/export").json()
    assert data["info_kit"] is None and data["family"]["account_email"] is None
    assert data["registration_alerts"] == []


def test_every_family_table_is_exported():
    """A new table keyed by family must be added to the export, or this fails.

    It only sees tables created with IF NOT EXISTS that have their own family_id column.
    Tables linked through another table (reminder_sends, kit_share_events,
    registration_reminder_sends) are not checked here: add those by hand."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    tables = set()
    for f in sorted((root / "migrations").glob("*.sql")):
        for name, body in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", f.read_text(), re.S):
            if re.search(r"\bfamily_id\s+UUID", body):
                tables.add(name)
    source = (root / "campfinder" / "services" / "family_export.py").read_text()
    assert tables and not [t for t in sorted(tables) if f'"{t}"' not in source]
