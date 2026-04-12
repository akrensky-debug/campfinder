"""
Programmatic difference generation for the camp comparison endpoint.
All observations are built from field comparisons — no hardcoding.
"""

from __future__ import annotations

from typing import Any


def generate_differences(camps: list[dict[str, Any]]) -> list[str]:
    """
    Compare a list of camp records and return plain-language observations
    about how they differ.
    """
    diffs: list[str] = []
    names = [c["name"] for c in camps]

    # Helper: label for a camp
    def label(c: dict[str, Any]) -> str:
        return c["name"]

    # --- Price ---
    _diff_price(camps, diffs)

    # --- Transportation ---
    _diff_boolean_field(camps, "transportation", "offers transportation", "does not offer transportation", diffs)

    # --- Extended care ---
    _diff_boolean_field(camps, "extended_care", "offers extended care", "does not offer extended care", diffs)

    # --- Meals ---
    _diff_boolean_field(camps, "meals_included", "includes meals", "does not include meals", diffs)

    # --- ACA accreditation ---
    _diff_aca(camps, diffs)

    # --- Age ranges ---
    _diff_age_ranges(camps, diffs)

    # --- Session count ---
    _diff_session_count(camps, diffs)

    # --- Camp type ---
    _diff_text_field(camps, "camp_type", "camp type", diffs)

    # --- Verification status ---
    _diff_verification(camps, diffs)

    return diffs


def _diff_price(camps: list[dict[str, Any]], diffs: list[str]) -> None:
    summaries = []
    for c in camps:
        ppw = c.get("price_per_week")
        pmin = c.get("price_min")
        pmax = c.get("price_max")
        if ppw:
            summaries.append((c["name"], f"${ppw:.0f}/week"))
        elif pmin and pmax:
            summaries.append((c["name"], f"${pmin:.0f}–${pmax:.0f}/week"))
        elif pmin:
            summaries.append((c["name"], f"from ${pmin:.0f}/week"))
        else:
            summaries.append((c["name"], None))

    known = [(n, v) for n, v in summaries if v is not None]
    if len({v for _, v in known}) > 1:
        parts = ", ".join(f"{n} is {v}" for n, v in known)
        diffs.append(f"Price ranges differ: {parts}")

    missing = [n for n, v in summaries if v is None]
    if missing:
        diffs.append(f"Price not available for: {', '.join(missing)}")


def _diff_boolean_field(
    camps: list[dict[str, Any]],
    field: str,
    yes_label: str,
    no_label: str,
    diffs: list[str],
) -> None:
    yes = [c["name"] for c in camps if c.get(field)]
    no = [c["name"] for c in camps if not c.get(field)]
    if yes and no:
        if len(yes) == 1:
            diffs.append(f"{yes[0]} {yes_label}, {_join_names(no)} {no_label}")
        else:
            diffs.append(f"{_join_names(yes)} {yes_label}; {_join_names(no)} {no_label}")


def _diff_aca(camps: list[dict[str, Any]], diffs: list[str]) -> None:
    accredited = [c["name"] for c in camps if c.get("aca_accredited") is True]
    not_confirmed = [c["name"] for c in camps if not c.get("aca_accredited")]
    if accredited and not_confirmed:
        if len(accredited) == 1:
            diffs.append(
                f"{accredited[0]} is ACA accredited, "
                f"{'the other is' if len(not_confirmed) == 1 else 'the others are'} not confirmed"
            )
        else:
            diffs.append(
                f"{_join_names(accredited)} are ACA accredited; "
                f"{_join_names(not_confirmed)} are not confirmed"
            )


def _diff_age_ranges(camps: list[dict[str, Any]], diffs: list[str]) -> None:
    ranges = []
    for c in camps:
        mn, mx = c.get("age_min"), c.get("age_max")
        if mn is not None and mx is not None:
            ranges.append((c["name"], mn, mx))

    if len(ranges) < 2:
        return

    # Overall overlap
    overlap_min = max(r[1] for r in ranges)
    overlap_max = min(r[2] for r in ranges)

    if overlap_min <= overlap_max:
        parts = []
        for name, mn, mx in ranges:
            if mn < overlap_min or mx > overlap_max:
                parts.append(f"{name} also accepts ages {mn}–{mx}")
        if parts:
            diffs.append(
                f"Age ranges overlap for ages {overlap_min}–{overlap_max}; "
                + "; ".join(parts)
            )
    else:
        parts = [f"{name} accepts ages {mn}–{mx}" for name, mn, mx in ranges]
        diffs.append("Age ranges do not overlap: " + ", ".join(parts))


def _diff_session_count(camps: list[dict[str, Any]], diffs: list[str]) -> None:
    counts = [(c["name"], len(c.get("sessions", []))) for c in camps]
    if len({v for _, v in counts}) > 1:
        parts = [f"{n} has {v} session{'s' if v != 1 else ''}" for n, v in counts]
        diffs.append("Session counts differ: " + ", ".join(parts))


def _diff_text_field(
    camps: list[dict[str, Any]], field: str, label: str, diffs: list[str]
) -> None:
    values = {c.get(field) for c in camps}
    if len(values) > 1:
        parts = [f"{c['name']} is {c.get(field, 'unknown')}" for c in camps]
        diffs.append(f"Differ on {label}: " + ", ".join(parts))


def _diff_verification(camps: list[dict[str, Any]], diffs: list[str]) -> None:
    statuses = {c.get("verification_status") for c in camps}
    if len(statuses) > 1:
        parts = [f"{c['name']} is {c.get('verification_status', 'unknown')}" for c in camps]
        diffs.append("Verification levels differ: " + ", ".join(parts))


def _join_names(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"
