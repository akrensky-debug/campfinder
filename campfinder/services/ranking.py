"""
Scoring and ranking logic for camp search results.

Scoring factors (all additive on top of base 1.0):
  +0.20  age fit          — camp age range contains the requested age
  +0.15  date fit         — per matching session week (capped at 3 weeks × 0.15)
  +0.10  category fit     — per matching category (capped at 3 × 0.10)
  +0.20  distance fit     — <15 mi: +0.20 | <30 mi: +0.10
  +0.15  price fit        — price_per_week ≤ max_price_per_week
  +0.10  data completeness — has sessions, price, and description
  +0.10  verification     — camp_verified or team_verified
  +0.05  freshness        — updated within last 30 days
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any


def _weeks_from_dates(start_iso: str, end_iso: str) -> list[date]:
    """Return all Monday dates that fall within [start, end]."""
    start = date.fromisoformat(start_iso)
    end = date.fromisoformat(end_iso)
    weeks: list[date] = []
    # Find first Monday on or after start
    current = start + timedelta(days=(7 - start.weekday()) % 7)
    while current <= end:
        weeks.append(current)
        current += timedelta(weeks=1)
    return weeks


def score_camp(
    camp: dict[str, Any],
    sessions: list[dict[str, Any]],
    *,
    age: int | None = None,
    requested_weeks: list[str] | None = None,
    categories: list[str] | None = None,
    distance_miles: float | None = None,
    max_price_per_week: float | None = None,
) -> tuple[float, list[str]]:
    """
    Compute a relevance score and a list of human-readable match_reasons for one camp.

    Returns (score, reasons).
    """
    score = 1.0
    reasons: list[str] = []

    # --- Age fit ---
    age_min = camp.get("age_min")
    age_max = camp.get("age_max")
    if age is not None and age_min is not None and age_max is not None:
        if age_min <= age <= age_max:
            score += 0.20
            reasons.append(f"Matches age {age}")

    # --- Date / session week fit ---
    if requested_weeks and sessions:
        requested_dates = {date.fromisoformat(w) for w in requested_weeks}
        matched_weeks = 0
        for session in sessions:
            session_weeks = set(
                _weeks_from_dates(
                    str(session["start_date"]), str(session["end_date"])
                )
            )
            overlap = requested_dates & session_weeks
            matched_weeks += len(overlap)
        if matched_weeks > 0:
            bump = min(matched_weeks, 3) * 0.15
            score += bump
            month_names = {w.month for w in requested_dates}
            month_str = _format_months(list(month_names))
            reasons.append(f"Has {month_str} sessions")

    # --- Category fit ---
    if categories and camp.get("primary_categories"):
        camp_cats = [c.lower() for c in (camp["primary_categories"] or [])]
        req_cats = [c.lower() for c in categories]
        matched_cats = [c for c in req_cats if c in camp_cats]
        if matched_cats:
            bump = min(len(matched_cats), 3) * 0.10
            score += bump
            reasons.append(f"Offers {_oxford_join(matched_cats)} programs")

    # --- Distance fit ---
    if distance_miles is not None:
        if distance_miles < 15:
            score += 0.20
            reasons.append(f"Within {distance_miles:.0f} miles")
        elif distance_miles < 30:
            score += 0.10
            reasons.append(f"Within {distance_miles:.0f} miles")

    # --- Price fit ---
    ppw = camp.get("price_per_week")
    if max_price_per_week is not None and ppw is not None:
        if float(ppw) <= max_price_per_week:
            score += 0.15
            reasons.append(f"Under ${max_price_per_week:.0f}/week")

    # --- Data completeness ---
    has_sessions = len(sessions) > 0
    has_price = camp.get("price_per_week") is not None or camp.get("price_min") is not None
    has_description = bool(camp.get("description_short") or camp.get("description_full"))
    if has_sessions and has_price and has_description:
        score += 0.10

    # --- Verification quality ---
    vstatus = camp.get("verification_status", "")
    if vstatus in ("camp_verified", "team_verified"):
        score += 0.10
        reasons.append("Verified listing")

    # --- ACA accreditation (bonus reason, no score impact beyond verification) ---
    if camp.get("aca_accredited"):
        reasons.append("ACA accredited")

    # --- Freshness ---
    last_updated = camp.get("last_updated_date") or camp.get("updated_at")
    if last_updated is not None:
        if isinstance(last_updated, str):
            try:
                last_updated = datetime.fromisoformat(last_updated)
            except ValueError:
                last_updated = None
        if last_updated is not None:
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=timezone.utc)
            days_old = (datetime.now(timezone.utc) - last_updated).days
            if days_old <= 30:
                score += 0.05

    return score, reasons


def _format_months(month_numbers: list[int]) -> str:
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return _oxford_join([names[m - 1] for m in sorted(set(month_numbers))])


def _oxford_join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"
