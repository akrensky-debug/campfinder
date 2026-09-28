"""The listing tool: safe fetching, text extraction, import. The model call is faked."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import asyncpg
import pytest

from campfinder.ingest import extract, fetch
from campfinder.ingest.importer import ImportError_, import_listing, listing_to_rows
from campfinder.ingest.schema import Evidence, ProposedListing, ProposedSession
from campfinder.jobs.send_alerts import send_due_alerts
from campfinder.repositories import bookings as bookings_repo
from tests.factories import make_camp, make_session, soon

SAMPLE_HTML = """
<html><head><title>Riverbend Day Camp</title><style>.x{}</style></head>
<body><script>var a=1;</script>
<h1>Riverbend Day Camp</h1>
<p>Ages 6 to 12. Weekly sessions June 21 to August 13, 2027.</p>
<ul><li>Week 1: June 21-25, $350</li><li>Week 2: June 28-July 2, $350</li></ul>
<a href="/register">Register here</a> <a href="mailto:x@y">Email</a>
</body></html>
"""


def test_html_to_text_strips_scripts_and_keeps_links() -> None:
    text, title, links = fetch.html_to_text(SAMPLE_HTML, "https://riverbend.example/summer")
    assert title == "Riverbend Day Camp"
    assert "var a=1" not in text and ".x{}" not in text
    assert "Week 1: June 21-25, $350" in text
    assert ("Register here", "https://riverbend.example/register") in links


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/admin", "http://localhost:8000/", "http://10.0.0.5/", "http://169.254.169.254/latest/meta-data",
    "ftp://example.com/x", "http://user:pw@example.com/",
])
def test_unsafe_urls_are_refused(url: str) -> None:
    with pytest.raises(fetch.UnsafeURL):
        fetch.check_url(url)


def test_read_local_html(tmp_path: Path) -> None:
    p = tmp_path / "camp.html"
    p.write_text(SAMPLE_HTML)
    source = fetch.read_file(p)
    assert source.kind == "html" and source.title == "Riverbend Day Camp"


def _source(text: str) -> fetch.Source:
    return fetch.Source(url="https://camp.example", kind="html", title=None, text=text)


@pytest.mark.parametrize("text", ["Please wait while your request is being verified...",
                                  "One moment, please... " + "word " * 60])
def test_bot_check_pages_are_refused(text: str) -> None:
    with pytest.raises(fetch.FetchError, match="bot-check"):
        fetch.check_content(_source(text))


def test_near_empty_pages_are_refused() -> None:
    with pytest.raises(fetch.FetchError, match="almost no text"):
        fetch.check_content(_source("Loading"))


def test_real_page_passes_even_if_it_mentions_javascript() -> None:
    text = "Riverbend Day Camp, ages 6 to 12, $250 a week. " * 30 + "Please enable JavaScript and cookies for the map."
    assert fetch.check_content(_source(text)).text == text


async def test_extract_uses_structured_output(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class FakeMessages:
        async def parse(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(stop_reason="end_turn", parsed_output=ProposedListing(name="Riverbend Day Camp", city="Providence", state="RI"))

    fake_client = SimpleNamespace(messages=FakeMessages())
    source = fetch.Source(url="https://riverbend.example", kind="html", title="Riverbend", text="Ages 6 to 12",
                          links=[("Register", "https://riverbend.example/register")])
    listing = await extract.extract_listing(source, client=fake_client, model="claude-opus-5-5", today=date(2026, 10, 1))
    assert listing.name == "Riverbend Day Camp"
    assert listing.website_url == "https://riverbend.example"
    assert captured["output_format"] is ProposedListing
    assert captured["model"] == "claude-opus-5-5"
    assert "Today is 2026-10-01" in captured["messages"][0]["content"]
    assert "Register: https://riverbend.example/register" in captured["messages"][0]["content"]


def test_listing_to_rows_requires_basics() -> None:
    with pytest.raises(ImportError_):
        listing_to_rows(ProposedListing(name="X"), source_url="u")
    with pytest.raises(ImportError_):
        listing_to_rows(ProposedListing(name="X", city="Nowhere", state="ZZ", camp_type="day"), source_url="u")


async def test_import_listing_writes_camp_sessions_sources(conn: asyncpg.Connection) -> None:
    listing = ProposedListing(
        name="Riverbend Day Camp", city="Providence", state="ri", camp_type="day", age_min=6, age_max=12,
        price_per_week=350, primary_categories=["Nature"],
        sessions=[ProposedSession(name="Week 1", start_date=date(2027, 6, 21), end_date=date(2027, 6, 25), price=350),
                  ProposedSession(name="No dates")],
        evidence=[Evidence(field="price_per_week", quote="$350 per week", confidence=0.9)],
    )
    camp_id = await import_listing(conn, listing, source_url="https://riverbend.example")
    camp = await conn.fetchrow("SELECT state, verification_status, sources, transportation FROM camps WHERE id = $1", camp_id)
    assert camp["state"] == "RI" and camp["verification_status"] == "unverified"
    assert camp["sources"] == ["https://riverbend.example"] and camp["transportation"] is False
    assert await conn.fetchval("SELECT count(*) FROM sessions WHERE camp_id = $1", camp_id) == 1
    note = await conn.fetchval("SELECT notes FROM field_sources WHERE camp_id = $1 AND field_name = 'price_per_week'", camp_id)
    assert note == "ingest confidence 0.90"
    assert await conn.fetchval("SELECT changed_by FROM listing_changes WHERE camp_id = $1", camp_id) == "ingest"


async def test_send_due_alerts(conn: asyncpg.Connection, outbox: list) -> None:
    from campfinder.services import email

    email.reset_outbox()
    camp_id = await make_camp(conn)
    await make_session(conn, camp_id, registration_opens_at=soon(3))
    later = await make_camp(conn, name="Later Camp")
    await make_session(conn, later, registration_opens_at=soon(40))
    await bookings_repo.create_alert(conn, email="p@example.com", camp_id=camp_id, family_id=None)
    await bookings_repo.create_alert(conn, email="p@example.com", camp_id=later, family_id=None)

    assert await send_due_alerts(conn) == 1
    assert outbox[0].to == "p@example.com" and "Riverbend" in outbox[0].subject
    assert "List-Unsubscribe" in outbox[0].headers
    assert await conn.fetchval("SELECT status FROM registration_alerts WHERE camp_id = $1", camp_id) == "sent"
    assert await send_due_alerts(conn) == 0
