"""Owner confirmation: send, look, confirm or take down; refused if the listing changed."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from campfinder.owners import service
from campfinder.owners.__main__ import main as cli

CAMP_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def camp(db):
    db.table("camps").insert({
        "id": CAMP_ID, "name": "Riverside Soccer Camp", "city": "Providence", "state": "RI", "zip": "02906",
        "camp_type": "day", "age_min": 6, "age_max": 12, "price_per_week": 325.0, "email": "Info@Riverside.example",
        "website_url": "https://riverside.example", "verification_status": "unverified", "is_active": True,
        "primary_categories": ["sports"], "season_year": 2026,
    }).execute()
    db.table("sessions").insert([
        {"camp_id": CAMP_ID, "name": "Week 1", "start_date": "2027-07-05", "end_date": "2027-07-09",
         "price": 325.0, "availability": "open"},
    ]).execute()
    db.table("field_sources").insert([
        {"camp_id": CAMP_ID, "field_name": "price_per_week", "source_type": "public_web",
         "source_url": "https://riverside.example/rates"},
    ]).execute()
    return service.find_camp(CAMP_ID)


def token_from(outbox) -> str:
    link = next(line for line in outbox[-1].text.splitlines() if "/owners/confirm/" in line)
    return link.rsplit("/owners/confirm/", 1)[1].strip()


async def test_send_needs_a_person_to_check_first(camp, outbox):
    with pytest.raises(service.ConfirmationError, match="checked by a person"):
        await service.send(camp, sent_by="Andrew")
    assert outbox == []


async def test_preview_records_and_sends_nothing(camp, db, outbox, capsys):
    assert cli(["preview", CAMP_ID]) == 0
    out = capsys.readouterr().out
    assert "To: info@riverside.example" in out and "Riverside Soccer Camp" in out and "$325" in out
    assert not db.tables.get("listing_confirmations") and outbox == []


async def test_confirm_flow(client, camp, db, outbox):
    assert service.mark_checked(camp, "Andrew") == "team_verified"
    first = await service.send(service.find_camp(CAMP_ID), sent_by="Andrew")
    await service.send(service.find_camp(CAMP_ID), sent_by="Andrew")   # a resend supersedes the first link
    assert [c["status"] for c in db.tables["listing_confirmations"]] == ["superseded", "sent"]
    assert client.get(f"/api/v1/owners/confirm/{first.token}").status_code == 404

    email = outbox[-1]
    assert email.to == "info@riverside.example" and "CampFinder" in email.text and "Andrew" not in email.text
    token = token_from(outbox)

    view = client.get(f"/api/v1/owners/confirm/{token}").json()       # looking changes nothing
    assert view["camp_name"] == "Riverside Soccer Camp" and not view["changed_since_sent"]
    assert db.tables["camps"][0]["verification_status"] == "team_verified"

    res = client.post(f"/api/v1/owners/confirm/{token}", json={"answer": "confirm"})
    assert res.json() == {"outcome": "confirmed", "camp_name": "Riverside Soccer Camp"}
    assert db.tables["camps"][0]["verification_status"] == "camp_verified"
    price = [f for f in db.tables["field_sources"] if f["field_name"] == "price_per_week"]
    assert len(price) == 1 and price[0]["source_type"] == "camp_verified"   # upgraded in place
    assert price[0]["source_url"] == "https://riverside.example/rates"
    assert {f["field_name"] for f in db.tables["field_sources"]} >= {"name", "age_min", "sessions"}
    assert db.tables["camp_contacts"][0]["verified_at"] is not None
    assert outbox[-1].subject == "Confirmed: Riverside Soccer Camp"

    # Second click: the link is used up.
    assert client.post(f"/api/v1/owners/confirm/{token}", json={"answer": "confirm"}).status_code == 404

    # Parents and agents see who confirmed it and when.
    detail = client.get(f"/api/v1/camps/{CAMP_ID}").json()
    assert detail["trust_summary"]["confirmed_by_camp_at"] and "price_per_week" in detail["trust_summary"]["fields_verified"]
    log = [(c["field_name"], c["changed_by"]) for c in db.tables["listing_changes"]]
    assert ("verification_status", "team") in log and ("verification_status", "owner_web") in log


async def test_confirm_refused_if_listing_changed(client, camp, db, outbox):
    service.mark_checked(camp, "Andrew")
    await service.send(service.find_camp(CAMP_ID), sent_by="Andrew")
    token = token_from(outbox)
    db.table("sessions").update({"availability": "full"}).eq("camp_id", CAMP_ID).execute()
    assert client.get(f"/api/v1/owners/confirm/{token}").json()["changed_since_sent"] is True
    res = client.post(f"/api/v1/owners/confirm/{token}", json={"answer": "confirm"})
    assert res.json()["outcome"] == "changed"
    assert db.tables["camps"][0]["verification_status"] == "team_verified"
    assert db.tables["listing_confirmations"][0]["status"] == "superseded"


async def test_take_it_down(client, camp, db, outbox):
    service.mark_checked(camp, "Andrew")
    await service.send(service.find_camp(CAMP_ID), sent_by="Andrew")
    token = token_from(outbox)
    res = client.post(f"/api/v1/owners/confirm/{token}", json={"answer": "remove"})
    assert res.json()["outcome"] == "removed"
    assert db.tables["camps"][0]["is_active"] is False
    assert client.get(f"/api/v1/camps/{CAMP_ID}").status_code == 404
    assert outbox[-1].subject == "Removed: Riverside Soccer Camp"


async def test_expired_link(client, camp, db, outbox):
    service.mark_checked(camp, "Andrew")
    await service.send(service.find_camp(CAMP_ID), sent_by="Andrew")
    token = token_from(outbox)
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    db.table("listing_confirmations").update({"expires_at": past}).eq("camp_id", CAMP_ID).execute()
    assert client.get(f"/api/v1/owners/confirm/{token}").status_code == 404
    assert client.post(f"/api/v1/owners/confirm/{token}", json={"answer": "confirm"}).status_code == 404


async def test_find_camp_by_slug_and_name(camp, db):
    import uuid
    slug_id = str(uuid.uuid5(service.SLUG_NAMESPACE, "camp:beaver-summer-camp"))
    db.table("camps").insert({"id": slug_id, "name": "Beaver Summer Camp", "city": "Newton", "state": "MA",
                              "zip": "02467", "camp_type": "day", "verification_status": "unverified"}).execute()
    assert service.find_camp("beaver-summer-camp")["id"] == slug_id
    assert service.find_camp("riverside soccer camp")["id"] == CAMP_ID
    with pytest.raises(service.ConfirmationError):
        service.find_camp("no-such-camp")


async def test_log_mode_records_that_nothing_was_emailed(camp, db):
    from campfinder import mailer
    mailer.set_mailer(mailer.LogMailer())
    service.mark_checked(camp, "Andrew")
    await service.send(service.find_camp(CAMP_ID), sent_by="Andrew")
    assert any(isinstance(c.get("new_value"), dict) and c["new_value"].get("not_emailed")
               for c in db.tables["listing_changes"])


async def test_email_counts_families_waiting_for_registration(camp, db, outbox):
    db.table("registration_alerts").insert([
        {"camp_id": CAMP_ID, "email": "a@example.com", "token": "t1", "confirmed_at": "2026-10-01T00:00:00+00:00"},
        {"camp_id": CAMP_ID, "email": "b@example.com", "token": "t2", "confirmed_at": "2026-10-01T00:00:00+00:00"},
        {"camp_id": CAMP_ID, "email": "c@example.com", "token": "t3"},   # never confirmed: not counted
    ]).execute()
    email = service.prepare(service.find_camp(CAMP_ID)).email
    assert "2 families have asked us to tell them." in email.text and "c@example.com" not in email.text


def test_queue_and_send_ready(db, outbox, capsys):
    base = {"city": "Providence", "state": "RI", "zip": "02906", "camp_type": "day", "is_active": True,
            "season_year": 2026}
    ids = {n: f"44444444-0000-0000-0000-00000000000{i}" for i, n in enumerate(
        ["Asked", "Checked", "Confirmed", "No Email", "Off Site", "Unchecked", "With Contact"], 1)}
    db.table("camps").insert([
        {**base, "id": ids["Asked"], "name": "Asked", "email": "a@x.example", "verification_status": "team_verified"},
        {**base, "id": ids["Checked"], "name": "Checked", "email": "b@x.example", "verification_status": "team_verified"},
        {**base, "id": ids["Confirmed"], "name": "Confirmed", "email": "c@x.example", "verification_status": "camp_verified"},
        {**base, "id": ids["No Email"], "name": "No Email", "verification_status": "team_verified"},
        {**base, "id": ids["Off Site"], "name": "Off Site", "email": "o@x.example", "is_active": False,
         "verification_status": "team_verified"},
        {**base, "id": ids["Unchecked"], "name": "Unchecked", "email": "u@x.example", "verification_status": "unverified"},
        {**base, "id": ids["With Contact"], "name": "With Contact", "email": "info@w.example",
         "verification_status": "team_verified"},
    ]).execute()
    db.table("camp_contacts").insert({"camp_id": ids["With Contact"], "email": "Director@W.example",
                                      "is_primary": True}).execute()
    db.table("listing_confirmations").insert({
        "camp_id": ids["Asked"], "email": "a@x.example", "token_hash": "h", "snapshot": {}, "status": "sent",
        "sent_by": "Andrew", "sent_at": "2026-10-01T00:00:00+00:00",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=20)).isoformat(),
    }).execute()

    q = service.queue()
    assert [(c["name"], e) for c, e in q.ready] == [("Checked", "b@x.example"), ("With Contact", "director@w.example")]
    why = {c["name"]: w for c, w in q.waiting}
    assert why["Asked"].startswith("asked; link works until") and "not checked" in why["Unchecked"]
    assert "no email" in why["No Email"] and "Confirmed" not in why and "Off Site" not in why

    assert cli(["send-ready", "--by", "Andrew", "--limit", "1"]) == 0     # lists only
    assert "would ask Checked" in capsys.readouterr().out and outbox == []
    assert cli(["send-ready", "--by", "Andrew", "--limit", "1", "--yes"]) == 0
    assert [e.to for e in outbox] == ["b@x.example"]
    assert [c["name"] for c, _ in service.queue().ready] == ["With Contact"]

    assert cli(["checked", ids["Unchecked"], ids["No Email"], "--by", "Andrew"]) == 0
    assert "Unchecked: team_verified" in capsys.readouterr().out
