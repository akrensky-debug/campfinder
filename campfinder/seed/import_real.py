"""
Import real, sourced camp listings from the reviewed dataset in data/camps/.

Each file in data/camps/*.json holds one metro:

    {"metro": "Providence, RI", "camps": [<camp>, ...]}

A camp record uses the column names of the `camps` table (see schema.sql), plus:

    "slug":     stable id for the listing, unique across files (kebab-case)
    "sessions": [{"name", "start_date", "end_date", "price", "availability"}]
    "sources":  [{"url": "...", "checked": "YYYY-MM-DD", "fields": ["name", "age_min", ...]}]

Rules the validator enforces:
  - every filled field (and "sessions", if any) is listed under exactly one source;
    every listed field is filled. Unknown facts stay null, never guessed.
  - city/state must be in campfinder/seed/cities.py (geo search depends on it)
  - booleans (extended_care, transportation, meals_included, financial_aid,
    aca_accredited) are true, false or null; false means the site says no.
  - listings are imported as verification_status 'unverified' with public_web sources.

Camp and session ids are derived from the slug (uuid5), so re-running the import
updates rows in place instead of duplicating them, and a camp's sessions and
field sources are replaced with what the dataset says now.

Usage:
    python -m campfinder.seed.import_real --check          # validate and summarise
    python -m campfinder.seed.import_real --sql out.sql    # write SQL to run elsewhere
    python -m campfinder.seed.import_real --load           # upsert via Supabase (service key)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from campfinder.seed.cities import geocode_city

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "camps"
NAMESPACE = uuid.UUID("6f1c2a0e-8a43-4f5e-9d1e-0c4a7b2e9f10")

CAMP_TYPES = {"day", "sleepaway", "specialty"}
AVAILABILITY = {"open", "waitlist", "full", "unknown"}
CATEGORIES = {
    "general", "sports", "arts", "performing_arts", "STEM", "technology", "nature",
    "outdoor", "academic", "sailing", "swimming", "adventure", "leadership", "faith",
    "special_needs",
}
TRI_STATE = ("extended_care", "transportation", "meals_included", "financial_aid", "aca_accredited")

# Fields a record may carry, all mapped 1:1 onto camps columns.
CAMP_FIELDS = (
    "name", "operator_name", "website_url", "registration_url", "email", "phone",
    "street_address", "city", "state", "zip", "region", "camp_type",
    "primary_categories", "secondary_categories", "activities", "gender_policy",
    "age_min", "age_max", "grade_min", "grade_max", "description_short",
    "indoor_outdoor", "religious_affiliation",
    "price_min", "price_max", "price_per_week", "price_per",
    "extended_care", "transportation", "meals_included", "financial_aid",
    "refund_policy_summary", "special_needs_notes", "swim_waterfront_notes",
    "aca_accredited", "aca_source_url", "season_year",
)
REQUIRED = ("name", "website_url", "city", "state", "zip", "camp_type", "season_year")
# Derived or bookkeeping fields that don't need their own source row.
UNSOURCED = {"region", "season_year", "slug"}


def _is_filled(v: Any) -> bool:
    return v is not None and v != "" and v != []


def camp_id(slug: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"camp:{slug}"))


def session_id(slug: str, s: dict[str, Any]) -> str:
    return str(uuid.uuid5(NAMESPACE, f"session:{slug}:{s['start_date']}:{s['end_date']}:{s.get('name') or ''}"))


def load_dataset(data_dir: Path = DATA_DIR) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for path in sorted(data_dir.glob("*.json")):
        doc = json.loads(path.read_text())
        for camp in doc["camps"]:
            out.append((doc["metro"], camp))
    return out


def validate(records: list[tuple[str, dict[str, Any]]]) -> list[str]:
    errors: list[str] = []
    seen_slugs: set[str] = set()
    seen_sites: dict[str, str] = {}
    for metro, c in records:
        slug = c.get("slug") or "<no slug>"
        where = f"{metro} / {slug}"

        def err(msg: str) -> None:
            errors.append(f"{where}: {msg}")

        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
            err("slug must be kebab-case")
        if slug in seen_slugs:
            err("duplicate slug")
        seen_slugs.add(slug)

        unknown = set(c) - set(CAMP_FIELDS) - {"slug", "sessions", "sources", "notes"}
        if unknown:
            err(f"unknown keys {sorted(unknown)}")
        for f in REQUIRED:
            if not _is_filled(c.get(f)):
                err(f"missing required {f}")
        if c.get("camp_type") not in CAMP_TYPES:
            err(f"camp_type must be one of {sorted(CAMP_TYPES)}")
        if c.get("state") and geocode_city(c.get("city", ""), c["state"]) is None:
            err(f"city {c.get('city')!r}, {c['state']} is not in cities.py")
        if c.get("zip") and not re.fullmatch(r"\d{5}", str(c["zip"])):
            err("zip must be 5 digits")
        for f in TRI_STATE:
            if c.get(f) not in (True, False, None):
                err(f"{f} must be true, false or null")
        if c.get("aca_accredited") and not c.get("aca_source_url"):
            err("aca_accredited needs aca_source_url")
        for f in ("primary_categories", "secondary_categories"):
            bad = [x for x in c.get(f) or [] if x not in CATEGORIES]
            if bad:
                err(f"{f} has unknown categories {bad}; use {sorted(CATEGORIES)}")
        mn, mx = c.get("age_min"), c.get("age_max")
        if mn is not None and mx is not None and mn > mx:
            err("age_min > age_max")
        site = (c.get("website_url") or "").rstrip("/").lower()
        key = f"{site}|{c.get('name', '').lower()}"
        if key in seen_sites:
            err(f"same website and name as {seen_sites[key]}")
        seen_sites[key] = slug

        for i, s in enumerate(c.get("sessions") or []):
            try:
                start, end = date.fromisoformat(s["start_date"]), date.fromisoformat(s["end_date"])
            except (KeyError, TypeError, ValueError):
                err(f"session {i} needs ISO start_date and end_date")
                continue
            if end < start:
                err(f"session {i} ends before it starts")
            if c.get("season_year") and start.year != c["season_year"]:
                err(f"session {i} is not in season_year {c['season_year']}")
            if s.get("availability", "unknown") not in AVAILABILITY:
                err(f"session {i} availability must be one of {sorted(AVAILABILITY)}")

        # Provenance: every filled field has exactly one source and vice versa.
        sourced: dict[str, str] = {}
        for src in c.get("sources") or []:
            if not str(src.get("url", "")).startswith("http"):
                err(f"source url {src.get('url')!r} is not a URL")
            try:
                date.fromisoformat(src.get("checked", ""))
            except ValueError:
                err(f"source {src.get('url')} needs checked: YYYY-MM-DD")
            for f in src.get("fields") or []:
                if f in sourced:
                    err(f"field {f} listed under two sources")
                sourced[f] = src.get("url", "")
        filled = {f for f in CAMP_FIELDS if _is_filled(c.get(f))} - UNSOURCED
        if c.get("sessions"):
            filled.add("sessions")
        for f in sorted(filled - set(sourced)):
            err(f"field {f} is filled but has no source")
        for f in sorted(set(sourced) - filled):
            err(f"field {f} has a source but no value")
    return errors


def build_rows(records: list[tuple[str, dict[str, Any]]]) -> tuple[list[dict], list[dict], list[dict]]:
    camps, sessions, sources = [], [], []
    for metro, c in records:
        cid = camp_id(c["slug"])
        lat, lng = geocode_city(c["city"], c["state"])
        row = {f: c.get(f) for f in CAMP_FIELDS}
        row.update({
            "id": cid,
            "slug": c["slug"],
            "region": c.get("region") or metro,
            "location": f"SRID=4326;POINT({lng} {lat})",
            "is_day_camp": c["camp_type"] == "day",
            "is_sleepaway": c["camp_type"] == "sleepaway",
            "is_specialty": c["camp_type"] == "specialty",
            "stem_focus": "STEM" in (c.get("primary_categories") or []),
            "arts_focus": bool({"arts", "performing_arts"} & set(c.get("primary_categories") or [])),
            "sports_focus": "sports" in (c.get("primary_categories") or []),
            "nature_focus": bool({"nature", "outdoor"} & set(c.get("primary_categories") or [])),
            "verification_status": "unverified",
            "sources": sorted({s["url"] for s in c.get("sources") or []}),
            "last_reviewed_date": max((s["checked"] for s in c.get("sources") or []), default=None),
            "last_updated_date": max((s["checked"] for s in c.get("sources") or []), default=None),
            "is_active": True,
        })
        camps.append(row)

        for s in c.get("sessions") or []:
            start, end = date.fromisoformat(s["start_date"]), date.fromisoformat(s["end_date"])
            days = (end - start).days + 1
            sessions.append({
                "id": session_id(c["slug"], s),
                "camp_id": cid,
                "name": s.get("name"),
                "start_date": s["start_date"],
                "end_date": s["end_date"],
                "length_days": days,
                "length_weeks": round(days / 7, 1),
                "price": s.get("price"),
                "full_season": bool(s.get("full_season")),
                "availability": s.get("availability") or "unknown",
            })

        for src in c.get("sources") or []:
            for f in src["fields"]:
                sources.append({
                    "camp_id": cid,
                    "field_name": f,
                    "source_type": "public_web",
                    "source_url": src["url"],
                    "last_verified": src["checked"],
                    "notes": src.get("note"),
                })
    return camps, sessions, sources


def summarise(records: list[tuple[str, dict[str, Any]]]) -> str:
    lines = []
    by = Counter((m, c["camp_type"]) for m, c in records)
    for metro in sorted({m for m, _ in records}):
        parts = ", ".join(f"{t} {by[(metro, t)]}" for t in ("day", "specialty", "sleepaway"))
        total = sum(v for (m, _), v in by.items() if m == metro)
        lines.append(f"{metro}: {total} camps ({parts})")
    seasons = Counter(c["season_year"] for _, c in records)
    lines.append("Seasons: " + ", ".join(f"{y}: {n}" for y, n in sorted(seasons.items())))
    n_sessions = sum(len(c.get("sessions") or []) for _, c in records)
    lines.append(f"Sessions: {n_sessions}; camps with sessions: {sum(1 for _, c in records if c.get('sessions'))}")
    watch = ("price_per_week", "age_min", "extended_care", "transportation", "meals_included",
             "financial_aid", "aca_accredited", "registration_url", "street_address", "phone", "email")
    missing = Counter(f for _, c in records for f in watch if c.get(f) is None)
    missing["sessions"] = sum(1 for _, c in records if not c.get("sessions"))
    lines.append("Missing (null) counts: " + ", ".join(f"{f} {n}" for f, n in missing.most_common()))
    return "\n".join(lines)


# ── SQL output (for running through the Supabase SQL editor or MCP) ─────────

def _lit(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, list):
        return "ARRAY[" + ",".join(_lit(x) for x in v) + "]::text[]" if v else "'{}'::text[]"
    return "'" + str(v).replace("'", "''") + "'"


def _insert(table: str, rows: list[dict], conflict: str, chunk: int = 50) -> list[str]:
    stmts = []
    if not rows:
        return stmts
    cols = list(rows[0])
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "id")
    for i in range(0, len(rows), chunk):
        values = ",\n".join(
            "(" + ", ".join(
                f"ST_GeogFromText({_lit(r[c])})" if c == "location" else _lit(r[c]) for c in cols
            ) + ")"
            for r in rows[i:i + chunk]
        )
        stmts.append(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n{values}\n"
            f"ON CONFLICT ({conflict}) DO UPDATE SET {updates};"
        )
    return stmts


def to_sql(camps: list[dict], sessions: list[dict], sources: list[dict]) -> list[str]:
    ids = ", ".join(_lit(c["id"]) for c in camps)
    return [
        *_insert("camps", camps, "id"),
        f"DELETE FROM sessions WHERE camp_id IN ({ids});",
        f"DELETE FROM field_sources WHERE camp_id IN ({ids});",
        *_insert("sessions", sessions, "id"),
        *_insert("field_sources", sources, "camp_id, field_name"),
    ]


def load(camps: list[dict], sessions: list[dict], sources: list[dict]) -> None:
    from supabase import create_client

    url, key = os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    client = create_client(url, key)
    ids = [c["id"] for c in camps]
    for i in range(0, len(camps), 25):
        client.table("camps").upsert(camps[i:i + 25], on_conflict="id").execute()
    for i in range(0, len(ids), 50):
        client.table("sessions").delete().in_("camp_id", ids[i:i + 50]).execute()
        client.table("field_sources").delete().in_("camp_id", ids[i:i + 50]).execute()
    for i in range(0, len(sessions), 100):
        client.table("sessions").insert(sessions[i:i + 100]).execute()
    for i in range(0, len(sources), 200):
        client.table("field_sources").insert(sources[i:i + 200]).execute()
    print(f"Loaded {len(camps)} camps, {len(sessions)} sessions, {len(sources)} field sources")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", type=Path, default=DATA_DIR)
    p.add_argument("--check", action="store_true", help="validate and print a summary")
    p.add_argument("--sql", type=Path, help="write SQL statements to this file")
    p.add_argument("--load", action="store_true", help="upsert into Supabase")
    args = p.parse_args(argv)

    records = load_dataset(args.data)
    errors = validate(records)
    if errors:
        print(f"{len(errors)} problems:", *errors, sep="\n  ", file=sys.stderr)
        return 1
    print(summarise(records))
    camps, sessions, sources = build_rows(records)
    if args.sql:
        args.sql.write_text("\n\n".join(to_sql(camps, sessions, sources)) + "\n")
        print(f"Wrote {args.sql}")
    if args.load:
        load(camps, sessions, sources)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
