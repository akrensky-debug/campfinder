"""Owner confirmation: here is your listing, does it look right?"""

from __future__ import annotations

from datetime import date

import asyncpg
import httpx
import pytest

from campfinder.owners import as_text
from campfinder.services import owner_confirmation
from campfinder.services import email as email_module
from campfinder.services.email import Email
from tests.factories import make_camp, make_session

URL = "/api/v1/owners/listing-confirmation"


def _token(message: Email) -> str:
    return message.html.split("/owners/confirm?token=")[1].split('"')[0]


async def _checked_camp(conn: asyncpg.Connection, **overrides):
    camp_id = await make_camp(conn, **overrides)
    await make_session(conn, camp_id, start_date=date(2027, 7, 5), name="Week 1")
    await make_session(conn, camp_id, start_date=date(2027, 7, 12), name="Week 2", price=375)
    await bookings_contact(conn, camp_id)
    await owner_confirmation.mark_checked(conn, camp_id, checked_by="andrew")
    return camp_id


async def bookings_contact(conn: asyncpg.Connection, camp_id) -> None:
    from campfinder.repositories import bookings

    await bookings.upsert_contact(conn, camp_id=camp_id, email="dana@riverbend.example", name="Dana Ruiz", is_primary=True)


async def test_unchecked_camp_is_never_emailed(conn: asyncpg.Connection, outbox) -> None:
    camp_id = await make_camp(conn)
    preview = await owner_confirmation.send_confirmation(conn, camp_id, sent_by="andrew", send=False)
    assert preview.to == "director@riverbend.example"
    with pytest.raises(owner_confirmation.ConfirmationError, match="not been checked"):
        await owner_confirmation.send_confirmation(conn, camp_id, sent_by="andrew")
    assert outbox == []
    assert await conn.fetchval("SELECT count(*) FROM listing_confirmations") == 0


async def test_preview_records_and_sends_nothing(conn: asyncpg.Connection, outbox) -> None:
    camp_id = await _checked_camp(conn)
    preview = await owner_confirmation.send_confirmation(conn, camp_id, sent_by="andrew", send=False)
    assert outbox == []
    assert await conn.fetchval("SELECT count(*) FROM listing_confirmations") == 0
    text = as_text(preview.html)
    assert "Hi Dana," in text
    assert "Week 2: 2027-07-12 to 2027-07-16, $375" in text
    assert "Thanks, Andrew" in text


async def test_owner_confirms_what_they_were_shown(client: httpx.AsyncClient, conn: asyncpg.Connection, outbox) -> None:
    camp_id = await _checked_camp(conn)
    sent = await owner_confirmation.send_confirmation(conn, camp_id, sent_by="andrew")
    assert outbox == [sent]
    assert sent.to == "dana@riverbend.example"
    season = email_module.upcoming_season()
    assert sent.subject == f"Your camp's {season} listing (please check it)"
    assert f"When does {season} registration open?" in sent.html
    assert "Price per week</strong></td><td>$350" in sent.html
    token = _token(sent)

    # Opening the page changes nothing, however often a mail scanner does it.
    for _ in range(2):
        r = await client.get(URL, params={"token": token})
        assert r.status_code == 200
        assert r.json()["camp_name"] == "Riverbend Day Camp"
        assert r.json()["changed_since_sent"] is False
        assert [s["name"] for s in r.json()["snapshot"]["sessions"]] == ["Week 1", "Week 2"]
    assert await conn.fetchval("SELECT verification_status FROM camps WHERE id = $1", camp_id) == "team_verified"

    r = await client.post(f"{URL}/respond", json={"token": token, "answer": "confirm"})
    assert r.status_code == 200
    assert r.json() == {"outcome": "confirmed", "camp_name": "Riverbend Day Camp"}

    camp = await conn.fetchrow("SELECT verification_status, last_reviewed_at FROM camps WHERE id = $1", camp_id)
    assert camp["verification_status"] == "camp_verified"
    sources = {r["field_name"]: r["source_type"] for r in await conn.fetch(
        "SELECT field_name, source_type FROM field_sources WHERE camp_id = $1", camp_id)}
    assert sources["name"] == sources["price_per_week"] == sources["sessions"] == "camp_verified"
    assert "grade_min" not in sources  # not on the listing, so not confirmed
    assert await conn.fetchval(
        "SELECT verified_at IS NOT NULL FROM camp_contacts WHERE camp_id = $1 AND email = 'dana@riverbend.example'", camp_id)
    change = await conn.fetchrow(
        "SELECT * FROM listing_changes WHERE camp_id = $1 AND field_name = 'verification_status' AND changed_by = 'owner_web'",
        camp_id)
    assert change["actor"] == "dana@riverbend.example"
    assert change["new_value"] == "camp_verified"
    assert outbox[-1].subject == "Done: Riverbend Day Camp is confirmed"
    trust = (await client.get(f"/api/v1/camps/{camp_id}")).json()["trust_summary"]
    assert trust["verification_status"] == "camp_verified"
    assert trust["confirmed_by_camp_at"] is not None

    # One use only.
    r = await client.post(f"{URL}/respond", json={"token": token, "answer": "confirm"})
    assert r.status_code == 404
    assert (await client.get(URL, params={"token": token})).status_code == 404


async def test_a_change_after_sending_voids_the_confirmation(client: httpx.AsyncClient, conn: asyncpg.Connection, outbox) -> None:
    camp_id = await _checked_camp(conn)
    token = _token(await owner_confirmation.send_confirmation(conn, camp_id, sent_by="andrew"))
    await conn.execute("UPDATE sessions SET price = 410 WHERE camp_id = $1 AND name = 'Week 2'", camp_id)

    r = await client.get(URL, params={"token": token})
    assert r.json()["changed_since_sent"] is True
    r = await client.post(f"{URL}/respond", json={"token": token, "answer": "confirm"})
    assert r.json()["outcome"] == "changed"
    assert await conn.fetchval("SELECT verification_status FROM camps WHERE id = $1", camp_id) == "team_verified"
    assert await conn.fetchval("SELECT status FROM listing_confirmations WHERE camp_id = $1", camp_id) == "superseded"
    assert (await client.post(f"{URL}/respond", json={"token": token, "answer": "confirm"})).status_code == 404


async def test_owner_takes_the_camp_down(client: httpx.AsyncClient, conn: asyncpg.Connection, outbox) -> None:
    camp_id = await _checked_camp(conn)
    token = _token(await owner_confirmation.send_confirmation(conn, camp_id, sent_by="andrew"))
    r = await client.post(f"{URL}/respond", json={"token": token, "answer": "remove"})
    assert r.json() == {"outcome": "removed", "camp_name": "Riverbend Day Camp"}
    assert await conn.fetchval("SELECT is_active FROM camps WHERE id = $1", camp_id) is False
    assert outbox[-1].subject == "Removed: Riverbend Day Camp"
    r = await client.post("/api/v1/search", json={"location": "Providence, RI"})
    assert r.json()["results"] == []


async def test_only_the_newest_link_works(client: httpx.AsyncClient, conn: asyncpg.Connection, outbox) -> None:
    camp_id = await _checked_camp(conn)
    first = _token(await owner_confirmation.send_confirmation(conn, camp_id, sent_by="andrew"))
    second = _token(await owner_confirmation.send_confirmation(conn, camp_id, sent_by="andrew", to="Other@Riverbend.example"))
    assert outbox[-1].to == "other@riverbend.example"
    assert (await client.post(f"{URL}/respond", json={"token": first, "answer": "confirm"})).status_code == 404
    assert (await client.post(f"{URL}/respond", json={"token": second, "answer": "confirm"})).json()["outcome"] == "confirmed"


async def test_expired_link(client: httpx.AsyncClient, conn: asyncpg.Connection, outbox) -> None:
    camp_id = await _checked_camp(conn)
    token = _token(await owner_confirmation.send_confirmation(conn, camp_id, sent_by="andrew"))
    await conn.execute("UPDATE listing_confirmations SET expires_at = NOW() - interval '1 minute'")
    assert (await client.get(URL, params={"token": token})).status_code == 404
    assert (await client.post(f"{URL}/respond", json={"token": token, "answer": "confirm"})).status_code == 404


async def test_inactive_camp_and_missing_email(conn: asyncpg.Connection) -> None:
    gone = await make_camp(conn, name="Closed Camp", is_active=False)
    with pytest.raises(owner_confirmation.ConfirmationError, match="not active"):
        await owner_confirmation.send_confirmation(conn, gone, sent_by="andrew", send=False)
    no_email = await make_camp(conn, name="Quiet Camp", email=None)
    with pytest.raises(owner_confirmation.ConfirmationError, match="--to"):
        await owner_confirmation.send_confirmation(conn, no_email, sent_by="andrew", send=False)


def test_upcoming_season_turns_over_in_september() -> None:
    assert email_module.upcoming_season(date(2026, 8, 31)) == 2026
    assert email_module.upcoming_season(date(2026, 9, 1)) == 2027
    assert email_module.upcoming_season(date(2027, 2, 1)) == 2027


async def test_last_seasons_dates_are_called_that(conn: asyncpg.Connection, outbox) -> None:
    camp_id = await _checked_camp(conn, season_year=2020)
    preview = await owner_confirmation.send_confirmation(conn, camp_id, sent_by="andrew", send=False)
    assert "from your 2020 season" in preview.html
