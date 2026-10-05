"""Phase 1 removals: no Pro plan, no email gate, no selling parent contacts to camps."""

from __future__ import annotations

from campfinder import mailer

CAMP_ID = "33333333-3333-3333-3333-333333333333"


def test_lead_and_payment_endpoints_are_gone(client) -> None:
    for path, body in [
        ("/api/v1/leads", {"parent_email": "mom@example.com"}),
        ("/api/v1/leads/request-info", {"parent_email": "mom@example.com", "target_camp_id": CAMP_ID}),
        ("/api/v1/stripe/checkout", {"camp_id": CAMP_ID, "email": "owner@example.com"}),
        ("/api/v1/stripe/webhook", {}),
    ]:
        assert client.post(path, json=body).status_code == 404, path
    paths = client.get("/openapi.json").json()["paths"]
    assert not [p for p in paths if "/leads" in p or "/stripe" in p]


def test_claim_email_goes_through_the_shared_mailer(client, db, outbox) -> None:
    db.table("camps").insert({"id": CAMP_ID, "name": "Riverside Soccer", "city": "Providence", "state": "RI",
                              "zip": "02906", "camp_type": "day"}).execute()
    res = client.post("/api/v1/claims", json={"camp_id": CAMP_ID, "email": "owner@example.com"})
    assert res.status_code == 200
    email = outbox[-1]
    token = db.tables["claim_requests"][0]["verification_token"]
    assert email.to == "owner@example.com" and token in email.text
    assert f"/operators/claim?camp_id={CAMP_ID}" in email.text

    # In log mode (the default) nothing leaves, even with a Resend key set.
    mailer.set_mailer(mailer.LogMailer())
    outbox.clear()
    assert client.post("/api/v1/claims", json={"camp_id": CAMP_ID, "email": "owner@example.com"}).status_code == 200
    assert outbox == []
