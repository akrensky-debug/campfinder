"""
Import a curated dataset of year-round programs (see data/pilots/) into Supabase.

Every fact in a dataset is `{"value": ..., "source": "<key>"}`, pointing at a source page
and the date it was read. The importer keeps that provenance per field in
`program_field_sources`, marks every program `unverified`, and never fills a gap: a fact
that isn't in the file stays empty.

    python -m campfinder.activity.importer data/pilots/providence-swim-2026.json          # dry run
    python -m campfinder.activity.importer data/pilots/providence-swim-2026.json --apply  # write

Re-running is safe: programs are keyed by `slug` and offerings by `(program, key)`. Prices
and field sources for the dataset's programs are replaced, and offerings no longer in the
file are removed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from campfinder.activity.schedule import describe, normalize_days, parse_time, weekly_rrule

KINDS = {"class", "lesson", "league", "after_school", "event"}
PRICE_TYPES = {"full_term", "per_class", "drop_in", "trial", "registration_fee", "membership", "monthly"}
AVAILABILITY = {"open", "limited", "waitlist", "full"}

PROGRAM_FIELDS = (
    "name", "provider_name", "provider_website", "provider_phone", "provider_email", "description",
    "age_min", "age_max", "grade_min", "grade_max", "skill_levels", "trial_available", "trial_notes",
    "financial_aid", "registration_url", "membership_required", "location_name", "street_address",
    "city", "state", "zip", "activities",
)
OFFERING_FIELDS = (
    "name", "term_name", "skill_level", "age_min", "age_max", "location_name", "street_address", "city",
    "state", "zip", "start_date", "end_date", "days", "start_time", "end_time", "exdates", "class_count",
    "enrollment_opens", "enrollment_closes", "availability", "drop_in_allowed", "notes",
)
DATE_FIELDS = {"start_date", "end_date", "enrollment_opens", "enrollment_closes"}
INT_FIELDS = {"age_min", "age_max", "grade_min", "grade_max", "class_count"}
BOOL_FIELDS = {"trial_available", "financial_aid", "membership_required", "drop_in_allowed"}
LIST_FIELDS = {"skill_levels", "activities", "days", "exdates"}


class DatasetError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


@dataclass
class Plan:
    """Rows to write, keyed so they can be linked after upsert."""

    dataset: str
    programs: list[dict[str, Any]] = field(default_factory=list)
    offerings: list[dict[str, Any]] = field(default_factory=list)       # carry "_slug"
    prices: list[dict[str, Any]] = field(default_factory=list)          # carry "_slug", "_key"
    sources: list[dict[str, Any]] = field(default_factory=list)         # carry "_slug", "_key"


def _check_value(name: str, value: Any, where: str, problems: list[str]) -> Any:
    try:
        if name in DATE_FIELDS:
            return date.fromisoformat(value).isoformat()
        if name in ("start_time", "end_time"):
            t = parse_time(value)
            return t.strftime("%H:%M") if t else None
        if name in INT_FIELDS:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError("expected a whole number")
            return value
        if name in BOOL_FIELDS:
            if not isinstance(value, bool):
                raise ValueError("expected true/false")
            return value
        if name == "days":
            return normalize_days(value)
        if name == "exdates":
            return [date.fromisoformat(d).isoformat() for d in value]
        if name in LIST_FIELDS:
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ValueError("expected a list of strings")
            return value
        if name == "state":
            if not re.fullmatch(r"[A-Z]{2}", str(value)):
                raise ValueError("expected a 2-letter state")
            return value
        if name == "availability":
            if value not in AVAILABILITY:
                raise ValueError(f"expected one of {sorted(AVAILABILITY)}")
            return value
        if not isinstance(value, str) or not value.strip():
            raise ValueError("expected text")
        return value.strip()
    except (ValueError, TypeError) as e:
        problems.append(f"{where}.{name}: {e} (got {value!r})")
        return None


def _facts(rec: dict[str, Any], names: tuple[str, ...], where: str, sources: dict[str, Any], problems: list[str]) -> tuple[dict[str, Any], dict[str, str]]:
    """Pull sourced facts out of a record. Returns (values, field -> source key)."""
    values, provenance = {}, {}
    for name in names:
        if name not in rec:
            continue
        fact = rec[name]
        if not isinstance(fact, dict) or "value" not in fact or "source" not in fact:
            problems.append(f"{where}.{name}: every fact needs {{value, source}}")
            continue
        if fact["source"] not in sources:
            problems.append(f"{where}.{name}: unknown source {fact['source']!r}")
            continue
        if fact["value"] in (None, "", []):
            continue  # unknown stays unknown
        v = _check_value(name, fact["value"], where, problems)
        if v is not None:
            values[name] = v
            provenance[name] = fact["source"]
    return values, provenance


def _prices(items: list[dict[str, Any]], where: str, sources: dict[str, Any], problems: list[str]) -> list[dict[str, Any]]:
    out = []
    for i, p in enumerate(items or []):
        w = f"{where}.prices[{i}]"
        if p.get("type") not in PRICE_TYPES:
            problems.append(f"{w}.type: expected one of {sorted(PRICE_TYPES)}")
            continue
        amount = p.get("amount")
        if not isinstance(amount, dict) or amount.get("source") not in sources:
            problems.append(f"{w}.amount: needs {{value, source}} with a known source")
            continue
        if not isinstance(amount.get("value"), (int, float)) or isinstance(amount.get("value"), bool) or amount["value"] < 0:
            problems.append(f"{w}.amount: expected a non-negative number")
            continue
        out.append({
            "price_type": p["type"], "amount": float(amount["value"]), "audience": p.get("audience"),
            "covers": p.get("covers"), "notes": p.get("note") or amount.get("note"), "_source": amount["source"],
        })
    return out


def plan_dataset(data: dict[str, Any]) -> Plan:
    """Validate a dataset and turn it into rows. Raises DatasetError listing every problem."""
    problems: list[str] = []
    sources = data.get("sources") or {}
    for key, src in sources.items():
        if not str(src.get("url", "")).startswith(("http://", "https://")):
            problems.append(f"sources.{key}: needs an http(s) url")
        try:
            date.fromisoformat(src.get("retrieved_on", ""))
        except (TypeError, ValueError):
            problems.append(f"sources.{key}: needs retrieved_on as YYYY-MM-DD")
    dataset = data.get("dataset") or ""
    if not dataset:
        problems.append("dataset: needs a name")
    plan = Plan(dataset=dataset)
    seen_slugs: set[str] = set()

    def add_sources(provenance: dict[str, str], slug: str, key: str | None) -> None:
        for name, src in provenance.items():
            plan.sources.append({
                "_slug": slug, "_key": key, "field_name": name, "source_type": "public_web",
                "source_url": sources[src]["url"], "retrieved_on": sources[src]["retrieved_on"],
            })

    for i, p in enumerate(data.get("programs") or []):
        slug = p.get("slug") or ""
        where = f"programs[{slug or i}]"
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
            problems.append(f"{where}.slug: lowercase letters, digits and dashes")
            continue
        if slug in seen_slugs:
            problems.append(f"{where}.slug: duplicate")
            continue
        seen_slugs.add(slug)
        if p.get("kind") not in KINDS:
            problems.append(f"{where}.kind: expected one of {sorted(KINDS)}")
        values, provenance = _facts(p, PROGRAM_FIELDS, where, sources, problems)
        if "name" not in values:
            problems.append(f"{where}.name: required")
        offerings_in = p.get("offerings") or []
        offering_rows = []
        seen_keys: set[str] = set()
        for j, o in enumerate(offerings_in):
            key = o.get("key") or ""
            ow = f"{where}.offerings[{key or j}]"
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", key) or key in seen_keys:
                problems.append(f"{ow}.key: required, unique, letters/digits/._-")
                continue
            seen_keys.add(key)
            ov, oprov = _facts(o, OFFERING_FIELDS, ow, sources, problems)
            if "start_date" in ov and "end_date" in ov and ov["end_date"] < ov["start_date"]:
                problems.append(f"{ow}: end_date before start_date")
            if "start_time" in ov and "end_time" in ov and ov["end_time"] <= ov["start_time"]:
                problems.append(f"{ow}: end_time not after start_time")
            days = ov.pop("days", None)
            if days:
                ov["rrule"] = weekly_rrule(days)
                oprov["rrule"] = oprov.pop("days")
            offering_rows.append({"_slug": slug, "external_key": key, **ov})
            add_sources(oprov, slug, key)
            for pr in _prices(o.get("prices"), ow, sources, problems):
                plan.prices.append({"_slug": slug, "_key": key, **pr})
                plan.sources.append({
                    "_slug": slug, "_key": key, "field_name": f"prices.{pr['price_type']}.{pr['audience'] or 'all'}",
                    "source_type": "public_web", "source_url": sources[pr["_source"]]["url"],
                    "retrieved_on": sources[pr["_source"]]["retrieved_on"],
                })
        for pr in _prices(p.get("prices"), where, sources, problems):
            plan.prices.append({"_slug": slug, "_key": None, **pr})
            plan.sources.append({
                "_slug": slug, "_key": None, "field_name": f"prices.{pr['price_type']}.{pr['audience'] or 'all'}",
                "source_type": "public_web", "source_url": sources[pr["_source"]]["url"],
                "retrieved_on": sources[pr["_source"]]["retrieved_on"],
            })
        # The programs table needs a town; fall back to the first offering's (still sourced).
        if "city" not in values:
            for o in offering_rows:
                if o.get("city") and o.get("state"):
                    values["city"], values["state"] = o["city"], o["state"]
                    break
        if "city" not in values or "state" not in values:
            problems.append(f"{where}: needs a city and state (program or an offering)")
        add_sources(provenance, slug, None)
        plan.programs.append({
            "slug": slug, "kind": p.get("kind"), "categories": list(p.get("categories") or []),
            "verification_status": "unverified", "source_dataset": dataset,
            "geo_precision": "city", "is_active": True, **values,
        })
        plan.offerings += offering_rows
    if problems:
        raise DatasetError(problems)
    return plan


# ---------------------------------------------------------------------------
# Summary (dry run) and apply
# ---------------------------------------------------------------------------

def summarize(plan: Plan, samples: int = 3) -> str:
    lines = [f"Dataset {plan.dataset}: {len(plan.programs)} programs, {len(plan.offerings)} offerings, "
             f"{len(plan.prices)} prices, {len(plan.sources)} sourced facts. All marked unverified."]
    by_provider = Counter(p.get("provider_name", "(provider unknown)") for p in plan.programs)
    offerings_by_slug = Counter(o["_slug"] for o in plan.offerings)
    lines.append("\nBy provider:")
    for provider, n in by_provider.most_common():
        slugs = [p["slug"] for p in plan.programs if p.get("provider_name", "(provider unknown)") == provider]
        lines.append(f"  {provider}: {n} program(s), {sum(offerings_by_slug[s] for s in slugs)} offering(s)")
    lines.append("\nMissing facts (left blank):")
    for name in ("age_min", "age_max", "registration_url", "provider_phone", "street_address", "skill_levels"):
        missing = sum(1 for p in plan.programs if name not in p)
        lines.append(f"  programs without {name}: {missing}/{len(plan.programs)}")
    for name in ("start_date", "end_date", "rrule", "start_time", "end_time", "enrollment_opens", "availability"):
        missing = sum(1 for o in plan.offerings if name not in o)
        lines.append(f"  offerings without {name}: {missing}/{len(plan.offerings)}")
    priced = {(p["_slug"], p["_key"]) for p in plan.prices}
    lines.append(f"  offerings without a price of their own: "
                 f"{sum(1 for o in plan.offerings if (o['_slug'], o['external_key']) not in priced)}/{len(plan.offerings)}")
    lines.append("\nSamples:")
    for o in plan.offerings[:samples]:
        program = next(p for p in plan.programs if p["slug"] == o["_slug"])
        from campfinder.activity.schedule import rrule_days
        when = describe(rrule_days(o.get("rrule")), parse_time(o.get("start_time")), parse_time(o.get("end_time")))
        prices = ", ".join(f"${p['amount']:.0f} {p['price_type']}{' (' + p['audience'] + ')' if p.get('audience') else ''}"
                           for p in plan.prices if p["_slug"] == o["_slug"] and p["_key"] in (o["external_key"], None))
        lines.append(f"  {program['name']} – {o.get('name') or o['external_key']}: "
                     f"{when or 'time not published'}, {o.get('start_date', '?')} to {o.get('end_date', '?')}"
                     f"{', ' + prices if prices else ''}")
    return "\n".join(lines)


def _clean(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if not k.startswith("_")}


def apply_plan(client: Any, plan: Plan) -> dict[str, int]:
    """Upsert the dataset. Programs by slug, offerings by (program, key); prices and
    provenance for these programs are replaced, and offerings dropped from the file removed.

    Rows are sent with `missing=default`: a fact absent from the file falls back to the
    column default (usually NULL), so a value removed from the dataset is cleared too."""
    if not plan.programs:
        return {"programs": 0, "offerings": 0, "prices": 0, "sources": 0}
    rows = client.table("programs").upsert([_clean(p) for p in plan.programs], on_conflict="slug", default_to_null=False).execute().data or []
    program_ids = {r["slug"]: r["id"] for r in rows}
    ids = list(program_ids.values())

    offering_rows = [{**_clean(o), "program_id": program_ids[o["_slug"]]} for o in plan.offerings]
    offering_ids: dict[tuple[str, str], str] = {}
    if offering_rows:
        saved = client.table("program_offerings").upsert(offering_rows, on_conflict="program_id,external_key", default_to_null=False).execute().data or []
        slug_by_id = {v: k for k, v in program_ids.items()}
        offering_ids = {(slug_by_id[r["program_id"]], r["external_key"]): r["id"] for r in saved}
    existing = client.table("program_offerings").select("id,program_id,external_key").in_("program_id", ids).execute().data or []
    stale = [r["id"] for r in existing if r["id"] not in set(offering_ids.values())]
    if stale:
        client.table("program_offerings").delete().in_("id", stale).execute()

    client.table("program_prices").delete().in_("program_id", ids).execute()
    client.table("program_field_sources").delete().in_("program_id", ids).execute()

    def link(row: dict[str, Any]) -> dict[str, Any]:
        out = {**_clean(row), "program_id": program_ids[row["_slug"]]}
        out["offering_id"] = offering_ids[(row["_slug"], row["_key"])] if row.get("_key") else None
        return out

    if plan.prices:
        client.table("program_prices").insert([link(p) for p in plan.prices], default_to_null=False).execute()
    if plan.sources:
        client.table("program_field_sources").insert([link(s) for s in plan.sources], default_to_null=False).execute()
    return {"programs": len(rows), "offerings": len(offering_rows), "prices": len(plan.prices),
            "sources": len(plan.sources), "removed_offerings": len(stale)}


def load_dataset(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import a curated activities dataset.")
    parser.add_argument("path")
    parser.add_argument("--apply", action="store_true", help="Write to Supabase (default is a dry run).")
    args = parser.parse_args(argv)
    try:
        plan = plan_dataset(load_dataset(args.path))
    except DatasetError as e:
        print(f"{len(e.problems)} problem(s):", *e.problems, sep="\n  ", file=sys.stderr)
        return 1
    print(summarize(plan))
    if args.apply:
        from campfinder.database import get_supabase
        print("\nApplied:", apply_plan(get_supabase(), plan))
    else:
        print("\nDry run. Re-run with --apply to write to the database.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
