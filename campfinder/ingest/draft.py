"""
Turn what the listing tool read into a draft camp record, in the reviewed dataset's own format
(data/camps/*.json), for a person to check before it goes anywhere near the site.

A draft is the dataset record plus a "review" block: what the tool was unsure of, what it
couldn't find, its warnings, and whatever the dataset validator would reject. Drafts live in
data/drafts/<metro>/ and are never imported. `python -m campfinder.ingest.promote` moves a
checked one into data/camps/ (docs/decisions/agents.md: publishing a new camp goes to Andrew).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from campfinder.ingest.fetch import Source
from campfinder.ingest.schema import ProposedListing
from campfinder.seed.import_real import CAMP_FIELDS, CATEGORIES, _is_filled, validate

LOW_CONFIDENCE = 0.8

# The extractor's category names onto the dataset's.
CATEGORY_MAP = {
    "sports": "sports", "arts": "arts", "stem": "STEM", "nature": "nature", "outdoor": "outdoor",
    "performing arts": "performing_arts", "performing_arts": "performing_arts", "technology": "technology",
    "academic": "academic", "faith-based": "faith", "faith": "faith", "special needs": "special_needs",
    "special_needs": "special_needs", "general": "general", "sailing": "sailing", "swimming": "swimming",
    "adventure": "adventure", "leadership": "leadership",
}

# ProposedListing fields that map 1:1 onto dataset fields.
COPIED = [f for f in ProposedListing.model_fields if f in CAMP_FIELDS]


def slugify(*parts: str | None) -> str:
    text = " ".join(p for p in parts if p).lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:80].strip("-")


def _plain(v: Any) -> Any:
    return int(v) if isinstance(v, float) and v.is_integer() else v


def to_draft(listing: ProposedListing, source: Source, *, metro: str, today: date,
             taken_slugs: set[str] = frozenset()) -> dict[str, Any]:
    """The listing as a dataset record plus its review notes. Unknown stays null."""
    notes: list[str] = []
    rec: dict[str, Any] = {}
    for f in COPIED:
        v = getattr(listing, f)
        rec[f] = [x for x in v] if isinstance(v, list) else _plain(v)

    if not rec.get("website_url") and source.kind == "html":
        rec["website_url"] = source.url
    if rec.get("state"):
        rec["state"] = rec["state"].strip().upper()
    if rec.get("zip"):
        m = re.match(r"\d{5}", str(rec["zip"]))
        rec["zip"] = m.group(0) if m else None

    cats, dropped = [], []
    for c in rec.get("primary_categories") or []:
        mapped = CATEGORY_MAP.get(c.strip().lower()) or (c if c in CATEGORIES else None)
        if mapped and mapped not in cats:
            cats.append(mapped)
        elif not mapped:
            dropped.append(c)
    rec["primary_categories"] = cats
    if dropped:
        notes.append(f"Categories not in our list, left out: {', '.join(dropped)}")
    if rec.get("price_per_week") is not None:
        rec["price_per"] = "week"
    if rec.get("aca_accredited"):
        rec["aca_accredited"] = None
        notes.append("The page says ACA accredited: check it on acacamps.org and add aca_accredited with aca_source_url")

    sessions = [s for s in listing.sessions if s.start_date and s.end_date]
    season = listing.season_year or (sessions[0].start_date.year if sessions else None)
    rec["season_year"] = season
    kept = [s for s in sessions if s.start_date.year == season]
    if len(kept) < len(sessions):
        notes.append(f"{len(sessions) - len(kept)} sessions outside the {season} season were left out")
    if len(sessions) < len(listing.sessions):
        notes.append(f"{len(listing.sessions) - len(sessions)} sessions without full dates were left out")
    rec["sessions"] = [{"name": s.name, "start_date": s.start_date.isoformat(), "end_date": s.end_date.isoformat(),
                        "price": _plain(s.price), "availability": s.availability} for s in kept]

    slug = base = slugify(rec.get("name"), rec.get("city"))
    n = 2
    while slug in taken_slugs:
        slug, n = f"{base}-{n}", n + 1
    filled = [f for f in CAMP_FIELDS if f != "season_year" and _is_filled(rec.get(f))]
    record = {"slug": slug, **{f: v for f, v in rec.items() if f == "sessions" or _is_filled(v) or f in ("city", "state", "zip")}}
    record["sources"] = [{
        "url": source.url, "checked": today.isoformat(),
        "fields": filled + (["sessions"] if record.get("sessions") else []),
        "note": "Drafted by the listing tool from this page",
    }]
    if not record.get("sessions"):
        record.pop("sessions", None)

    low = []
    for e in listing.evidence:
        if e.confidence < LOW_CONFIDENCE:
            low.append({"field": e.field, "confidence": round(e.confidence, 2), "quote": e.quote})
    errors = [e.split(": ", 1)[-1] for e in validate([(metro, {k: v for k, v in record.items()})])]
    record["review"] = {
        "status": "unchecked",
        "source": {"url": source.url, "kind": source.kind, "title": source.title},
        "warnings": listing.warnings + notes,
        "unknowns": listing.unknowns,
        "low_confidence": low,
        "errors": errors,
    }
    return record
