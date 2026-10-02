"""Household members, roles, invites, tasks, feeds and the audit log, through the HTTP API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tests.conftest import DAD, GRANDMA, OWNER, STRANGER, h, invite, join


def test_invite_accept_and_roles(client, db, family, outbox):
    fid = family["id"]
    created = invite(client, fid, "Grandma", "Grandma@Example.com", "caregiver")
    assert created["emailed"] is True and created["member"]["status"] == "invited"
    assert len(outbox) == 1
    mail = outbox[0]
    assert mail.to == "grandma@example.com" and created["url"] in mail.text
    assert "Maya" not in mail.text and "peanut" not in mail.text  # no kid details in an invite

    token = created["url"].rsplit("/", 1)[1]
    preview = client.get(f"/api/v1/invites/{token}").json()
    assert preview["role"] == "caregiver" and preview["email_hint"].startswith("g") and "grandma@" not in preview["email_hint"]

    # A forwarded link is useless: the signed-in email must match.
    res = client.post(f"/api/v1/invites/{token}/accept", headers=h(STRANGER))
    assert res.status_code == 403
    assert join(client, created, GRANDMA)["role"] == "caregiver"
    # The token is single-use.
    assert client.post(f"/api/v1/invites/{token}/accept", headers=h(GRANDMA)).status_code == 404

    # Grandma's view of the family: kids' first names only, no family feed, her own feed.
    fam = client.get(f"/api/v1/me/family", headers=h(GRANDMA)).json()
    assert fam["id"] == fid and fam["role"] == "caregiver"
    assert fam["profile"] == {"kids": [{"name": "Maya"}]}
    assert fam["calendar_url"] is None and fam["my_calendar_url"].endswith(".ics")
    assert len(fam["events"]) == 2

    # Caregivers can't chat with the agent, see the kit, or manage people.
    assert client.post("/api/v1/agent/chat", headers=h(GRANDMA), json={"family_id": fid, "message": "hi"}).status_code == 403
    assert client.get(f"/api/v1/families/{fid}/kit", headers=h(GRANDMA)).status_code == 403
    assert client.post(f"/api/v1/families/{fid}/members/invite", headers=h(GRANDMA),
                       json={"display_name": "X", "email": "x@example.com", "role": "viewer"}).status_code == 403
    assert client.delete(f"/api/v1/families/{fid}", headers=h(GRANDMA)).status_code == 403

    # A stranger gets nothing.
    assert client.get(f"/api/v1/families/{fid}", headers=h(STRANGER)).status_code == 403
    assert client.get(f"/api/v1/families/{fid}/tasks", headers=h(STRANGER)).status_code == 403


def test_household_view_is_least_data(client, family):
    fid = family["id"]
    join(client, invite(client, fid, "Grandma", "grandma@example.com", "caregiver"), GRANDMA)
    join(client, invite(client, fid, "Dan", "dad@example.com", "co_parent"), DAD)

    owner = client.get(f"/api/v1/families/{fid}/household", headers=h(OWNER)).json()
    assert owner["can_manage"] and {m["display_name"] for m in owner["members"]} == {"Mom", "Grandma", "Dan"}
    assert all(m["email"] for m in owner["members"])

    dad = client.get(f"/api/v1/families/{fid}/household", headers=h(DAD)).json()
    assert dad["role"] == "co_parent" and not dad["can_manage"]
    others = [m for m in dad["members"] if not m["is_you"]]
    assert others and all(m["email"] is None for m in others)

    grandma = client.get(f"/api/v1/families/{fid}/household", headers=h(GRANDMA)).json()
    assert [m["display_name"] for m in grandma["members"]] == ["Grandma"]


def test_kit_is_owner_only_unless_granted(client, db, family, monkeypatch):
    import base64, os
    from campfinder.config import get_settings
    monkeypatch.setattr(get_settings(), "kit_encryption_key", base64.urlsafe_b64encode(os.urandom(32)).decode())
    fid = family["id"]
    dad = join(client, invite(client, fid, "Dan", "dad@example.com", "co_parent"), DAD)
    members = client.get(f"/api/v1/families/{fid}/household", headers=h(OWNER)).json()["members"]
    dan = next(m for m in members if m["display_name"] == "Dan")

    assert client.get(f"/api/v1/families/{fid}/kit", headers=h(DAD)).status_code == 403
    assert client.get(f"/api/v1/families/{fid}/kit", headers=h(OWNER)).status_code == 200

    # Caregivers can never be given the kit.
    g = invite(client, fid, "Grandma", "grandma@example.com", "caregiver")["member"]
    assert client.patch(f"/api/v1/families/{fid}/members/{g['id']}", headers=h(OWNER), json={"kit_access": True}).status_code == 422

    assert client.patch(f"/api/v1/families/{fid}/members/{dan['id']}", headers=h(OWNER), json={"kit_access": True}).status_code == 200
    assert client.get(f"/api/v1/families/{fid}/kit", headers=h(DAD)).status_code == 200
    # Demoting him closes it again.
    client.patch(f"/api/v1/families/{fid}/members/{dan['id']}", headers=h(OWNER), json={"role": "caregiver"})
    assert client.get(f"/api/v1/families/{fid}/kit", headers=h(DAD)).status_code == 403

    actions = [e["action"] for e in client.get(f"/api/v1/families/{fid}/audit", headers=h(OWNER)).json()]
    assert "kit_viewed" in actions and "member_updated" in actions
    assert dad["role"] == "co_parent"


def test_generate_assign_and_complete(client, db, family):
    fid = family["id"]
    gm = invite(client, fid, "Grandma", "grandma@example.com", "caregiver")["member"]

    res = client.post(f"/api/v1/families/{fid}/tasks/generate", headers=h(OWNER),
                      json={"dropoff_time": "08:30", "pickup_time": "15:00"})
    tasks = res.json()
    kinds = [t["kind"] for t in tasks]
    # Jul 6-10 and 13-17 2027 run Tue-Sat: 4 weekdays each, plus one packing list per session.
    assert kinds.count("dropoff") == 8 and kinds.count("pickup") == 8 and kinds.count("packing") == 2
    packing = next(t for t in tasks if t["kind"] == "packing")
    assert packing["due_date"] == "2027-07-05" and packing["checklist"]
    # Running it again adds nothing.
    assert client.post(f"/api/v1/families/{fid}/tasks/generate", headers=h(OWNER), json={}).json() == []

    tuesday_pickups = [t["id"] for t in tasks if t["kind"] == "pickup"
                       and datetime.fromisoformat(t["due_date"]).weekday() == 1]
    assert len(tuesday_pickups) == 2
    res = client.post(f"/api/v1/families/{fid}/tasks/assign", headers=h(OWNER),
                      json={"task_ids": tuesday_pickups, "member_id": gm["id"]})
    assert {t["assignee_name"] for t in res.json()} == {"Grandma"}

    # Before she accepts, Grandma has no access; after, she sees only her two jobs.
    created = invite(client, fid, "Grandma", "grandma@example.com", "caregiver")  # re-invite renews the link
    join(client, created, GRANDMA)
    mine = client.get(f"/api/v1/families/{fid}/tasks", headers=h(GRANDMA)).json()
    assert sorted(t["id"] for t in mine) == sorted(tuesday_pickups)

    # She can complete her own job, but not edit it or touch anyone else's.
    tid = mine[0]["id"]
    done = client.patch(f"/api/v1/families/{fid}/tasks/{tid}", headers=h(GRANDMA), json={"status": "done"}).json()
    assert done["status"] == "done" and done["completed_by_name"] == "Grandma"
    assert client.patch(f"/api/v1/families/{fid}/tasks/{tid}", headers=h(GRANDMA), json={"title": "x"}).status_code == 403
    other = next(t["id"] for t in tasks if t["id"] not in tuesday_pickups)
    assert client.patch(f"/api/v1/families/{fid}/tasks/{other}", headers=h(GRANDMA), json={"status": "done"}).status_code == 403
    assert client.post(f"/api/v1/families/{fid}/tasks/assign", headers=h(GRANDMA),
                       json={"task_ids": [other], "member_id": gm["id"]}).status_code == 403

    log = client.get(f"/api/v1/families/{fid}/audit", headers=h(OWNER)).json()
    completed = next(e for e in log if e["action"] == "task_completed")
    assert completed["actor_name"] == "Grandma"
    assert any(e["action"] == "tasks_assigned" and e["detail"]["to"] == "Grandma" for e in log)
    assert client.get(f"/api/v1/families/{fid}/audit", headers=h(GRANDMA)).status_code == 403


def test_viewer_cannot_be_assigned_and_sees_no_tasks(client, family):
    fid = family["id"]
    v = invite(client, fid, "Aunt Jo", "stranger@example.com", "viewer")
    join(client, v, STRANGER)
    tasks = client.post(f"/api/v1/families/{fid}/tasks", headers=h(OWNER), json=[
        {"kind": "form", "title": "Riverside health form", "due_date": "2027-06-01"}]).json()
    assert client.post(f"/api/v1/families/{fid}/tasks/assign", headers=h(OWNER),
                       json={"task_ids": [tasks[0]["id"]], "member_id": v["member"]["id"]}).status_code == 422
    assert client.get(f"/api/v1/families/{fid}/tasks", headers=h(STRANGER)).json() == []
    fam = client.get(f"/api/v1/families/{fid}", headers=h(STRANGER)).json()
    assert fam["profile"] == {} and len(fam["events"]) == 2


def test_remove_and_leave(client, db, family):
    fid = family["id"]
    gm = invite(client, fid, "Grandma", "grandma@example.com", "caregiver")
    join(client, gm, GRANDMA)
    t = client.post(f"/api/v1/families/{fid}/tasks", headers=h(OWNER), json=[
        {"kind": "pickup", "title": "Pick up Maya", "due_date": "2027-07-06", "assignee_id": gm["member"]["id"]}]).json()[0]
    assert t["assignee_name"] == "Grandma"

    assert client.delete(f"/api/v1/families/{fid}/members/{gm['member']['id']}", headers=h(OWNER)).status_code == 204
    assert client.get(f"/api/v1/families/{fid}", headers=h(GRANDMA)).status_code == 403
    assert client.get(f"/api/v1/families/{fid}/tasks", headers=h(OWNER)).json()[0]["assignee_id"] is None

    dad = invite(client, fid, "Dan", "dad@example.com", "co_parent")
    join(client, dad, DAD)
    assert client.post(f"/api/v1/families/{fid}/leave", headers=h(DAD)).status_code == 204
    assert client.get(f"/api/v1/families/{fid}", headers=h(DAD)).status_code == 403
    assert client.post(f"/api/v1/families/{fid}/leave", headers=h(OWNER)).status_code == 422
    actions = [e["action"] for e in client.get(f"/api/v1/families/{fid}/audit", headers=h(OWNER)).json()]
    assert "member_removed" in actions and "left" in actions


def test_expired_invite(client, db, family):
    created = invite(client, family["id"], "Grandma", "grandma@example.com", "caregiver")
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    db.table("family_members").update({"invite_expires_at": past}).eq("email", "grandma@example.com").execute()
    token = created["url"].rsplit("/", 1)[1]
    assert client.get(f"/api/v1/invites/{token}").json()["expired"] is True
    assert client.post(f"/api/v1/invites/{token}/accept", headers=h(GRANDMA)).status_code == 410


def test_member_calendar_feed(client, family):
    fid = family["id"]
    gm = invite(client, fid, "Grandma", "grandma@example.com", "caregiver")
    join(client, gm, GRANDMA)
    client.post(f"/api/v1/families/{fid}/tasks", headers=h(OWNER), json=[
        {"kind": "pickup", "title": "Pick up Maya from Riverside", "due_date": "2027-07-06", "due_time": "15:00",
         "assignee_id": gm["member"]["id"]},
        {"kind": "payment", "title": "Pay Riverside balance", "due_date": "2027-06-01"},
    ])
    url = client.get("/api/v1/me/family", headers=h(GRANDMA)).json()["my_calendar_url"]
    ics = client.get(url.replace("http://testserver", "")).text
    assert "Pick up Maya from Riverside" in ics and "DTSTART:20270706T150000" in ics
    assert "Pay Riverside balance" not in ics  # not hers
    assert "Riverside Soccer Camp" in ics      # the family calendar is included

    # Resetting her link kills the old one.
    old = url.rsplit("/", 1)[1]
    client.post(f"/api/v1/families/{fid}/me/calendar/reset", headers=h(GRANDMA))
    assert client.get(f"/api/v1/calendar/member/{old}").status_code == 404


def test_guest_family_tasks_work_but_household_needs_account(client):
    fam = client.post("/api/v1/families").json()
    res = client.post(f"/api/v1/families/{fam['id']}/tasks", json=[
        {"kind": "deadline", "title": "Registration opens: Lakeside", "due_date": "2027-01-15"}])
    assert res.status_code == 201
    assert client.get(f"/api/v1/families/{fam['id']}/household").json()["members"] == []
    assert client.post(f"/api/v1/families/{fam['id']}/members/invite",
                       json={"display_name": "G", "email": "g@example.com", "role": "caregiver"}).status_code == 401
