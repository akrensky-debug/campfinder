from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from tests.booking.conftest import CAMP, OTHER_CAMP, OWNER, SESSION, STRANGER, h, window
from tests.fakes import FakeSupabase


def regs(client: TestClient, fam: dict[str, Any]) -> str:
    return f"/api/v1/families/{fam['id']}/registrations"


def events(db: FakeSupabase, fam: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in db.tables.get("family_events", []) if e["family_id"] == fam["id"]]


def test_watch_puts_opening_day_on_the_calendar(client: TestClient, db: FakeSupabase, family: dict[str, Any]) -> None:
    window(db, 10)
    res = client.post(regs(client, family), headers=h(OWNER),
                      json={"camp_id": CAMP, "session_id": SESSION, "child_name": "Maya"})
    assert res.status_code == 201, res.text
    r = res.json()
    assert r["status"] == "watching" and r["opens_at_source"] == "camp"
    assert "in 10 days" in r["next_step"] or "in 9 days" in r["next_step"]
    assert r["registration_url"] == "https://riverside.example/register"
    [ev] = events(db, family)
    assert ev["title"] == "Registration opens: Riverside Soccer Camp"
    # Watching again is a no-op, not a duplicate.
    again = client.post(regs(client, family), headers=h(OWNER),
                        json={"camp_id": CAMP, "session_id": SESSION, "child_name": "maya"}).json()
    assert again["id"] == r["id"] and len(db.tables["family_registrations"]) == 1


def test_family_date_wins_when_camp_has_none(client: TestClient, db: FakeSupabase, family: dict[str, Any]) -> None:
    r = client.post(regs(client, family), headers=h(OWNER),
                    json={"camp_id": OTHER_CAMP, "opens_at": "2027-01-15T14:00:00Z"}).json()
    assert r["opens_at_source"] == "family"
    assert r["next_step"].startswith("Registration opens Fri Jan 15 at 9:00 am")


def test_registered_and_paid_flow_updates_calendar(client: TestClient, db: FakeSupabase, family: dict[str, Any]) -> None:
    window(db, 3)
    r = client.post(regs(client, family), headers=h(OWNER),
                    json={"camp_id": CAMP, "session_id": SESSION, "child_name": "Maya"}).json()
    url = f"{regs(client, family)}/{r['id']}"

    res = client.patch(url, headers=h(OWNER), json={
        "status": "registered", "payment_status": "deposit", "amount_paid": 100, "paid_on": "2027-01-15",
        "balance_due": 325, "payment_due_date": "2027-05-01", "forms_due_date": "2027-06-01",
        "confirmation_number": "RSC-1042"})
    assert res.status_code == 200, res.text
    r = res.json()
    assert r["status"] == "registered" and r["payment_status"] == "deposit"
    assert "Pay $325 by Sat May 1" in r["next_step"]
    titles = sorted(e["title"] for e in events(db, family))
    assert titles == ["Maya: Riverside Soccer Camp", "Maya: forms due for Riverside Soccer Camp",
                      "Payment due: Riverside Soccer Camp ($325)"]
    session_ev = next(e for e in events(db, family) if e["title"] == "Maya: Riverside Soccer Camp")
    assert (session_ev["start_date"], session_ev["end_date"]) == ("2027-07-06", "2027-07-10")
    assert "RSC-1042" in session_ev["notes"]

    r = client.patch(url, headers=h(OWNER), json={"payment_status": "paid", "amount_paid": 425}).json()
    assert r["balance_due"] is None and r["paid_on"]
    assert not any(e["title"].startswith("Payment due") for e in events(db, family))

    r = client.patch(url, headers=h(OWNER), json={"status": "cancelled"}).json()
    assert r["status"] == "cancelled" and events(db, family) == []


def test_waitlist_and_adopting_the_agents_calendar_entry(client: TestClient, db: FakeSupabase, family: dict[str, Any]) -> None:
    # The agent already put the session on the calendar while planning.
    db.table("family_events").insert({"family_id": family["id"], "title": "Maya: Riverside Soccer", "start_date": "2027-07-06",
                                      "end_date": "2027-07-10", "child_name": "Maya", "camp_id": CAMP,
                                      "session_id": SESSION}).execute()
    r = client.post(regs(client, family), headers=h(OWNER),
                    json={"camp_id": CAMP, "session_id": SESSION, "child_name": "Maya"}).json()
    r = client.patch(f"{regs(client, family)}/{r['id']}", headers=h(OWNER), json={"status": "waitlisted"}).json()
    assert r["next_step"].startswith("On the waitlist")
    [ev] = events(db, family)
    assert ev["title"] == "Maya: Riverside Soccer Camp (waitlist)"


def test_delete_removes_only_its_own_events(client: TestClient, db: FakeSupabase, family: dict[str, Any]) -> None:
    window(db, 5)
    db.table("family_events").insert({"family_id": family["id"], "title": "Dentist", "start_date": "2027-02-01",
                                      "end_date": "2027-02-01"}).execute()
    r = client.post(regs(client, family), headers=h(OWNER), json={"camp_id": CAMP}).json()
    assert len(events(db, family)) == 2
    assert client.delete(f"{regs(client, family)}/{r['id']}", headers=h(OWNER)).status_code == 204
    assert [e["title"] for e in events(db, family)] == ["Dentist"]


def test_access_rules(client: TestClient, db: FakeSupabase, family: dict[str, Any]) -> None:
    assert client.get(regs(client, family), headers=h(STRANGER)).status_code == 403
    assert client.get(regs(client, family)).status_code == 401
    # Guest families can track registrations (like the calendar) but not share packages.
    guest = client.post("/api/v1/families").json()
    assert client.post(regs(client, guest), json={"camp_id": CAMP}).status_code == 201
    res = client.post(f"/api/v1/families/{guest['id']}/registration-package/preview", json={"camp_id": CAMP},
                      headers=h(OWNER))
    assert res.status_code == 403
    assert client.post(regs(client, family), headers=h(OWNER),
                       json={"camp_id": OTHER_CAMP, "session_id": SESSION}).status_code == 404


def test_checklist_reports_readiness_without_kit_values(client: TestClient, db: FakeSupabase, family: dict[str, Any]) -> None:
    window(db, 2)
    res = client.get(f"/api/v1/families/{family['id']}/register-checklist",
                     params={"camp_id": CAMP, "session_id": SESSION, "child": "Maya"}, headers=h(OWNER))
    assert res.status_code == 200, res.text
    c = res.json()
    assert c["registration_url"] == "https://riverside.example/register" and c["price"] == 425
    assert c["form"]["typical"] is True and c["kit_available"] is True
    by_q = {f["question"]: f for f in c["form"]["fields"]}
    assert by_q["Allergies"]["ready"] is True
    assert by_q["Grade in the fall"]["ready"] is False and by_q["Grade in the fall"]["missing_for"] == ["Maya"]
    assert by_q["Signed waiver and photo release"]["kit_field"] is None
    kit_step = next(s for s in c["steps"] if s["key"] == "kit")
    assert kit_step["done"] is False and "Grade" in kit_step["text"]
    body = json.dumps(c)
    for secret in ("Peanuts", "XJ-55521", "401-555", "2018-04-02", "Rosa"):
        assert secret not in body


def test_checklist_for_guest_has_no_kit(client: TestClient, db: FakeSupabase) -> None:
    guest = client.post("/api/v1/families").json()
    c = client.get(f"/api/v1/families/{guest['id']}/register-checklist", params={"camp_id": CAMP}).json()
    assert c["kit_available"] is False and all(f["ready"] is None for f in c["form"]["fields"])


def test_camp_form_mapping_is_used(client: TestClient, db: FakeSupabase, family: dict[str, Any]) -> None:
    db.tables["registration_forms"] = [{"camp_id": CAMP, "platform": "campminder", "source": "camp", "fields": [
        {"question": "Camper name", "kit_field": "child.name"},
        {"question": "Food allergies", "kit_field": "child.allergies"},
        {"question": "Emergency contact", "kit_field": "household.emergency_contacts"},
        {"question": "Shirt", "kit_field": "child.tshirt_size", "required": False},
        {"question": "Bogus", "kit_field": "child.ssn"},
        {"question": "How did you hear about us?", "kit_field": None},
    ]}]
    res = client.get(f"/api/v1/camps/{CAMP}/registration")
    assert res.status_code == 200
    form = res.json()["form"]
    assert form["typical"] is False and form["platform"] == "campminder"
    assert [f["question"] for f in form["fields"]] == [
        "Camper name", "Food allergies", "Emergency contact", "Shirt", "How did you hear about us?"]

    p = client.post(f"/api/v1/families/{family['id']}/registration-package/preview",
                    json={"camp_id": CAMP}, headers=h(OWNER)).json()
    assert p["children"] == ["Maya"]  # the only kid in the kit
    assert p["household_fields"] == ["emergency_contacts"]
    assert p["child_fields"] == ["allergies", "tshirt_size"]
    assert p["missing"] == [] and p["not_in_kit"] == ["How did you hear about us?"]


def test_package_shares_only_after_confirm(client: TestClient, db: FakeSupabase, family: dict[str, Any]) -> None:
    base = f"/api/v1/families/{family['id']}/registration-package"
    p = client.post(f"{base}/preview", json={"camp_id": CAMP, "children": ["Maya"]}, headers=h(OWNER)).json()
    assert "Grade in the fall (Maya)" in p["missing"]
    assert "Signed waiver and photo release" in p["not_in_kit"]
    assert not db.tables.get("kit_shares")  # previews share nothing

    body = {"camp_id": CAMP, "children": ["Maya"], "household_fields": ["parents", "emergency_contacts"],
            "child_fields": ["date_of_birth", "allergies"]}
    assert client.post(base, json={**body, "confirm": False}, headers=h(OWNER)).status_code == 422
    assert client.post(base, json=body, headers=h(OWNER)).status_code == 422  # confirm is required
    assert client.post(base, json={**body, "confirm": True}, headers=h(STRANGER)).status_code == 403
    assert not db.tables.get("kit_shares")

    res = client.post(base, json={**body, "confirm": True}, headers=h(OWNER))
    assert res.status_code == 201, res.text
    out = res.json()
    assert out["share"]["recipient"] == "Riverside Soccer Camp" and out["share"]["camp_id"] == CAMP
    token = out["url"].rsplit("/", 1)[1]
    pkg = client.get(f"/api/v1/shares/{token}").json()
    assert pkg["children"] == [{"name": "Maya", "date_of_birth": "2018-04-02", "allergies": "Peanuts (EpiPen)"}]
    assert set(pkg["household"]) == {"parents", "emergency_contacts"}

    c = client.get(f"/api/v1/families/{family['id']}/register-checklist", params={"camp_id": CAMP},
                   headers=h(OWNER)).json()
    assert len(c["shares"]) == 1 and next(s for s in c["steps"] if s["key"] == "package")["done"] is True


def test_next_step_flags_unpaid_balance_without_due_date(client: TestClient, db: FakeSupabase, family: dict[str, Any]) -> None:
    r = client.post(regs(client, family), headers=h(OWNER), json={"camp_id": CAMP, "session_id": SESSION}).json()
    r = client.patch(f"{regs(client, family)}/{r['id']}", headers=h(OWNER),
                     json={"status": "registered", "balance_due": 425}).json()
    assert r["next_step"] == "Pay $425 to the camp. Add the due date so we can remind you."
    r = client.patch(f"{regs(client, family)}/{r['id']}", headers=h(OWNER), json={"payment_status": "paid"}).json()
    assert r["next_step"] == "All set."
