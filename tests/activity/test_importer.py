import copy

import pytest

from campfinder.activity.importer import DatasetError, apply_plan, plan_dataset, summarize
from tests.activity.conftest import make_dataset


def test_plan_flattens_facts_and_keeps_provenance():
    plan = plan_dataset(make_dataset())
    assert len(plan.programs) == 3 and len(plan.offerings) == 3
    y = next(p for p in plan.programs if p["slug"] == "test-y-swim")
    assert y["verification_status"] == "unverified" and y["age_min"] == 3
    tue = next(o for o in plan.offerings if o["external_key"] == "stage2-tue-1600")
    assert tue["rrule"] == "FREQ=WEEKLY;BYDAY=TU" and tue["start_time"] == "16:00"
    fields = {(s["_key"], s["field_name"]) for s in plan.sources if s["_slug"] == "test-y-swim"}
    assert ("stage2-tue-1600", "rrule") in fields and (None, "age_min") in fields
    assert ("stage2-tue-1600", "prices.full_term.member") in fields
    assert all(s["source_url"] == "https://example.org/swim" for s in plan.sources)


def test_unknown_facts_stay_blank():
    plan = plan_dataset(make_dataset())
    school = next(p for p in plan.programs if p["slug"] == "test-swim-school")
    assert "registration_url" not in school and "street_address" not in school


def test_validation_reports_every_problem():
    data = make_dataset()
    data["programs"][0]["age_min"] = {"value": 3}  # no source
    data["programs"][0]["offerings"][0]["start_time"] = {"value": "late", "source": "s1"}
    data["programs"][1]["prices"][0]["type"] = "weekly"
    data["programs"][2]["name"]["source"] = "nope"
    with pytest.raises(DatasetError) as e:
        plan_dataset(data)
    text = "\n".join(e.value.problems)
    assert "age_min" in text and "start_time" in text and "prices[0].type" in text and "unknown source" in text


def test_apply_is_idempotent_and_removes_dropped_offerings(db):
    data = make_dataset()
    apply_plan(db, plan_dataset(data))
    apply_plan(db, plan_dataset(data))
    assert len(db.tables["programs"]) == 3 and len(db.tables["program_offerings"]) == 3
    n_prices = len(db.tables["program_prices"])
    smaller = copy.deepcopy(data)
    smaller["programs"][0]["offerings"].pop()
    result = apply_plan(db, plan_dataset(smaller))
    assert result["removed_offerings"] == 1
    assert len(db.tables["program_offerings"]) == 2
    assert len(db.tables["program_prices"]) == n_prices - 1


def test_summary_mentions_counts_and_samples():
    text = summarize(plan_dataset(make_dataset()))
    assert "3 programs, 3 offerings" in text and "Tuesdays 4–4:30pm" in text


def test_pilot_dataset_provenance_is_unique():
    """program_field_sources has a unique index on (program, offering, field); two prices of the
    same type and audience must not collide (Postgres rejects the whole import if they do)."""
    from collections import Counter
    from pathlib import Path

    from campfinder.activity.importer import load_dataset, plan_dataset

    path = Path(__file__).resolve().parents[2] / "data" / "pilots" / "providence-swim-2026.json"
    plan = plan_dataset(load_dataset(path))
    keys = Counter((s["_slug"], s.get("_key"), s["field_name"]) for s in plan.sources)
    assert [k for k, n in keys.items() if n > 1] == []
    assert any(s["field_name"].endswith(".2") for s in plan.sources)
