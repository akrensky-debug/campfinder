"""The listing tool over many camps: drafts for a person to check, then promoted into the dataset."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from campfinder.ingest import batch, promote
from campfinder.ingest.draft import to_draft
from campfinder.ingest.fetch import FetchError, Refused, Source
from campfinder.ingest.schema import Evidence, ProposedListing, ProposedSession
from campfinder.seed.import_real import DATA_DIR, validate

TODAY = date(2026, 10, 7)
PAGE = Source(url="https://riverside.example/camp", kind="html", title="Summer camp", text="...")


def listing(**over) -> ProposedListing:
    base = dict(
        name="Riverside Soccer Camp", operator_name="Riverside FC", city="Cranston", state="ri", zip="02920-1234",
        camp_type="day", primary_categories=["Sports", "Outdoor", "Underwater basket weaving"], age_min=6, age_max=12,
        price_per_week=325.0, aca_accredited=True, season_year=2027,
        sessions=[ProposedSession(name="Week 1", start_date=date(2027, 7, 5), end_date=date(2027, 7, 9), price=325.0),
                  ProposedSession(name="Old", start_date=date(2026, 7, 6), end_date=date(2026, 7, 10)),
                  ProposedSession(name="TBA")],
        evidence=[Evidence(field="price_per_week", quote="$325 per week", confidence=0.95),
                  Evidence(field="age_max", quote="ages 6 to 12ish", confidence=0.6)],
        unknowns=["email"], warnings=["Prices are from 2026"],
    )
    return ProposedListing(**{**base, **over})


def test_draft_is_a_dataset_record_with_review_notes() -> None:
    d = to_draft(listing(), PAGE, metro="Providence, RI", today=TODAY, taken_slugs={"riverside-soccer-camp-cranston"})
    review = d.pop("review")
    assert d["slug"] == "riverside-soccer-camp-cranston-2"
    assert (d["state"], d["zip"], d["website_url"]) == ("RI", "02920", PAGE.url)
    assert d["primary_categories"] == ["sports", "outdoor"] and d["price_per_week"] == 325 and d["price_per"] == "week"
    assert "aca_accredited" not in d                     # never claimed without the ACA source
    assert [s["name"] for s in d["sessions"]] == ["Week 1"] and d["sessions"][0]["price"] == 325
    assert validate([("Providence, RI", d)]) == []        # promotable as it stands
    src = d["sources"][0]
    assert src["url"] == PAGE.url and set(src["fields"]) >= {"name", "age_max", "sessions", "website_url"}

    assert review["status"] == "unchecked" and review["errors"] == []
    assert review["low_confidence"] == [{"field": "age_max", "confidence": 0.6, "quote": "ages 6 to 12ish"}]
    notes = " ".join(review["warnings"])
    assert "Prices are from 2026" in notes and "Underwater basket weaving" in notes and "acacamps.org" in notes
    assert "1 sessions outside the 2027 season" in notes and "1 sessions without full dates" in notes
    assert review["unknowns"] == ["email"]


def test_what_the_validator_rejects_is_in_the_review() -> None:
    d = to_draft(listing(city="Atlantis", zip=None, sessions=[]), PAGE, metro="Providence, RI", today=TODAY)
    errors = " ".join(d["review"]["errors"])
    assert "missing required zip" in errors and "not in cities.py" in errors


@pytest.fixture
def fake_tool(monkeypatch):
    pages = {
        "https://riverside.example/camp": listing(),
        "https://lakeside.example/arts": listing(name="Lakeside Arts", city="Warwick", zip="02886",
                                                 primary_categories=["Arts"], aca_accredited=None),
    }

    async def fetch(url):
        if "refuses" in url:
            raise Refused(f"{url} refused (403): ask the owner for the brochure")
        if "broken" in url:
            raise FetchError("connection reset")
        return Source(url=url, kind="html", title=None, text="page")

    async def extract(source, today=None):
        return pages[source.url]
    monkeypatch.setattr(batch, "fetch", fetch)
    monkeypatch.setattr(batch, "extract_listing", extract)


CANDIDATES = [
    {"name": "Riverside", "url": "https://riverside.example/camp"},
    {"name": "Lakeside", "url": "https://lakeside.example/arts"},
    {"name": "Grumpy", "url": "https://refuses.example/camp"},
    {"name": "Broken", "url": "https://broken.example/camp"},
    {"name": "Already listed", "url": "https://savebay.org/family-fun/camp/"},
]


async def test_batch_writes_drafts_and_a_review_sheet(fake_tool, tmp_path):
    drafts = tmp_path / "providence"
    log = await batch.run(CANDIDATES, metro="Providence, RI", drafts=drafts, limit=None, concurrency=2, today=TODAY)
    assert sorted(x["outcome"] for x in log) == ["drafted", "drafted", "failed", "refused"]   # the listed camp is skipped
    files = sorted(f.name for f in drafts.glob("*.json") if not f.name.startswith("_"))
    assert files == ["lakeside-arts-warwick.json", "riverside-soccer-camp-cranston.json"]
    sheet = (drafts / "REVIEW.md").read_text()
    assert "Ask the owner for the brochure" in sheet and "Grumpy: https://refuses.example/camp" in sheet
    assert "Broken" in sheet and "connection reset" in sheet

    # A second run picks up where it left off: drafted and refused hosts are not fetched again.
    seen = []

    async def fetch(url):
        seen.append(url)
        raise FetchError("still broken")
    batch.fetch = fetch
    await batch.run(CANDIDATES, metro="Providence, RI", drafts=drafts, limit=None, concurrency=2, today=TODAY)
    assert seen == ["https://broken.example/camp"]


async def test_promote_moves_a_checked_draft_into_the_dataset(fake_tool, tmp_path):
    data = tmp_path / "camps"
    shutil.copytree(DATA_DIR, data)
    drafts = tmp_path / "drafts" / "providence"
    await batch.run(CANDIDATES[:2], metro="Providence, RI", drafts=drafts, limit=None, concurrency=1, today=TODAY)
    before = len(json.loads((data / "providence.json").read_text())["camps"])

    rec = promote.promote(drafts / "riverside-soccer-camp-cranston.json", by="Andrew", today=date(2026, 10, 8),
                          data_dir=data)
    dataset = json.loads((data / "providence.json").read_text())
    assert len(dataset["camps"]) == before + 1 and dataset["camps"][-1]["slug"] == rec["slug"]
    assert "review" not in dataset["camps"][-1]
    assert dataset["camps"][-1]["sources"][0]["checked"] == "2026-10-08"
    assert "checked against this page by Andrew" in dataset["camps"][-1]["sources"][0]["note"]
    assert not (drafts / "riverside-soccer-camp-cranston.json").exists()

    # A draft the validator rejects stays a draft, and the dataset is untouched.
    bad = drafts / "lakeside-arts-warwick.json"
    d = json.loads(bad.read_text())
    d["city"] = "Atlantis"
    bad.write_text(json.dumps(d))
    with pytest.raises(ValueError, match="cities.py"):
        promote.promote(bad, by="Andrew", data_dir=data)
    assert bad.exists() and len(json.loads((data / "providence.json").read_text())["camps"]) == before + 1


def test_promote_cli_reports_failures(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "nowhere" / "x.json"
    assert promote.main([str(missing), "--by", "Andrew"]) == 1
    assert "x.json" in capsys.readouterr().err
