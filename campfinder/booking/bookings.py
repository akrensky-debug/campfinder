"""
Quote-then-book prototype (feature flag BOOKING_PROVIDERS, sandbox providers only).

1. quote: the platform prices and holds the session. Nothing about the family is sent.
2. The parent sees the seller (the camp), item, price, hold expiry, the camp's terms,
   and the exact info kit fields that will be sent, then presses Confirm.
3. confirm: only those fields go to the platform; the consent record keeps what she
   saw and the field names (never values). The camp collects payment itself.

The agent has no tool for any of this. Waivers and the camp's terms are never accepted
on the parent's behalf; she reads them on the camp's own pages.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

from campfinder.booking import forms, service
from campfinder.booking.models import RegistrationUpdate
from campfinder.booking.providers import ProviderError, enabled_names, get_provider
from campfinder.booking.providers.base import Quote
from campfinder.database import get_supabase
from campfinder.kit import service as kit_service
from campfinder.kit.models import InfoKit


class QuoteRequest(BaseModel):
    registration_id: str


class QuoteView(BaseModel):
    attempt_id: str
    provider: str
    environment: str
    seller: str
    item: str
    child_name: str | None
    price: float
    currency: str
    availability: str
    expires_at: datetime
    terms_url: str | None
    payment: str
    fields_to_send: list[str] = Field(description="Labels of the info kit fields that will be sent on confirm.")
    missing: list[str] = Field(description="Fields the kit can't fill yet; booking is blocked until they're added.")


class ConfirmRequest(BaseModel):
    confirm: bool = Field(description="Must be true: the parent pressed Confirm on the quote.")
    price_shown_cents: int = Field(description="The price on the screen she confirmed; must match the quote.")
    read_camp_terms: bool = Field(description="She opened and read the camp's terms herself.")


def is_enabled() -> bool:
    return bool(enabled_names())


def _require_enabled() -> None:
    if not is_enabled():
        raise HTTPException(status_code=404, detail="Booking through CampFinder isn't available yet")


def _bookable(camp_id: str, session_id: str | None) -> tuple[Any, str]:
    _, form_row = forms.load_form(camp_id)
    provider = get_provider((form_row or {}).get("platform"))
    ref = ((form_row or {}).get("provider_refs") or {}).get(str(session_id)) if session_id else None
    if provider is None or not ref:
        raise HTTPException(status_code=409, detail="This camp takes registrations on its own site only")
    return provider, ref


def _attendee(kit: InfoKit, child_name: str, fields: list[str]) -> tuple[dict[str, Any], list[str]]:
    """Exactly the requested kit fields for one child. Returns (attendee, missing labels)."""
    kid = next((c for c in kit.children if c.name.lower() == child_name.lower()), None)
    out: dict[str, Any] = {}
    missing: list[str] = []
    household = kit.household.model_dump(mode="json")
    for f in fields:
        scope, _, name = f.partition(".")
        if scope == "child":
            value = None if kid is None else (kid.name if name == "name" else kid.model_dump(mode="json").get(name))
        elif scope == "household":
            value = household.get(name)
        else:
            value = None
        if value in (None, "", []):
            # "None" is a real answer for allergies and medications; empty is not.
            missing.append(forms.KIT_LABELS.get(f, f))
        else:
            out[f] = value
    return out, missing


def _attempt(family_id: str, attempt_id: str) -> dict[str, Any]:
    rows = get_supabase().table("booking_attempts").select("*").eq("id", attempt_id).eq("family_id", family_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Quote not found")
    return rows[0]


def _quote_from_row(row: dict[str, Any]) -> Quote:
    q = dict(row["quote"])
    q["expires_at"] = datetime.fromisoformat(str(q["expires_at"]).replace("Z", "+00:00"))
    return Quote(**{k: v for k, v in q.items() if k in Quote.__dataclass_fields__})


async def quote(family: dict[str, Any], req: QuoteRequest) -> QuoteView:
    _require_enabled()
    family_id = str(family["id"])
    reg = service._row(family_id, req.registration_id)
    if not reg.get("child_name"):
        raise HTTPException(status_code=422, detail="Say which child this registration is for first")
    provider, ref = _bookable(str(reg["camp_id"]), reg.get("session_id"))
    try:
        q = await provider.quote(ref, attendees=1)
    except ProviderError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    kit = kit_service.load_kit(family_id)
    _, missing = _attendee(kit, reg["child_name"], q.required_fields)
    stored = {**q.__dict__, "expires_at": q.expires_at.isoformat()}
    row = get_supabase().table("booking_attempts").insert({
        "family_id": family_id, "registration_id": req.registration_id, "provider": provider.name,
        "environment": provider.environment, "status": "quoted", "quote": stored,
        "expires_at": q.expires_at.isoformat(), "updated_at": service._now(),
    }).execute().data[0]
    return QuoteView(
        attempt_id=str(row["id"]), provider=provider.name, environment=provider.environment, seller=q.seller,
        item=q.item, child_name=reg["child_name"], price=q.price_cents / 100, currency=q.currency,
        availability=q.availability, expires_at=q.expires_at, terms_url=q.terms_url, payment=q.payment,
        fields_to_send=[forms.KIT_LABELS.get(f, f) for f in q.required_fields], missing=missing,
    )


async def confirm(family: dict[str, Any], user_id: str, attempt_id: str, req: ConfirmRequest) -> dict[str, Any]:
    _require_enabled()
    family_id = str(family["id"])
    if req.confirm is not True or req.read_camp_terms is not True:
        raise HTTPException(status_code=422, detail="Confirm, and read the camp's terms, to book")
    row = _attempt(family_id, attempt_id)
    if row["status"] != "quoted":
        raise HTTPException(status_code=409, detail=f"This quote is already {row['status']}")
    q = _quote_from_row(row)
    sb = get_supabase()
    if q.expires_at < datetime.now(timezone.utc):
        sb.table("booking_attempts").update({"status": "expired", "updated_at": service._now()}).eq("id", attempt_id).execute()
        raise HTTPException(status_code=409, detail="The hold expired. Get a new quote.")
    if req.price_shown_cents != q.price_cents:
        raise HTTPException(status_code=409, detail="The price changed. Review the new quote.")
    provider = get_provider(row["provider"])
    if provider is None:
        raise HTTPException(status_code=409, detail="Booking with this camp is switched off")
    reg = service._row(family_id, str(row["registration_id"]))
    attendee, missing = _attendee(kit_service.load_kit(family_id), reg["child_name"], q.required_fields)
    if missing:
        raise HTTPException(status_code=422, detail=f"Add these to your info kit first: {', '.join(missing)}")

    consent = {
        "confirmed_by": user_id, "confirmed_at": service._now(), "read_camp_terms": True,
        "summary_shown": {"seller": q.seller, "item": q.item, "price_cents": q.price_cents, "currency": q.currency,
                          "child": reg["child_name"], "terms_url": q.terms_url, "payment": q.payment},
        "fields_shared": sorted(attendee),  # names only
    }
    try:
        booked = await provider.book(q, attendee, idempotency_key=attempt_id)
    except ProviderError as e:
        sb.table("booking_attempts").update({"status": "failed", "error": e.code, "consent": consent,
                                             "updated_at": service._now()}).eq("id", attempt_id).execute()
        raise HTTPException(status_code=409, detail=str(e)) from e
    sb.table("booking_attempts").update({"status": "confirmed", "consent": consent, "provider_ref": booked.provider_ref,
                                         "updated_at": service._now()}).eq("id", attempt_id).execute()
    registration = service.update_registration(family_id, str(reg["id"]), RegistrationUpdate(
        status=booked.status, confirmation_number=booked.provider_ref,
        balance_due=booked.amount_due_cents / 100 if booked.amount_due_cents else None,
    ))
    return {"status": booked.status, "provider_ref": booked.provider_ref, "payment_url": booked.payment_url,
            "amount_due": booked.amount_due_cents / 100, "registration": registration.model_dump(mode="json")}
