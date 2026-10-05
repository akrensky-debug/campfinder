"""
An in-memory sandbox platform for the quote-then-book prototype. Talks to nothing;
every booking it makes is fake. Session refs of the form 'full:...' are full (waitlist
only) and 'gone:...' are unknown, so the failure paths can be exercised.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from campfinder.booking.providers.base import Booked, ProviderError, Quote

REQUIRED = ["child.name", "child.date_of_birth", "child.allergies", "child.medications",
            "household.parents", "household.emergency_contacts"]


class SandboxProvider:
    name = "sandbox"
    environment = "sandbox"

    def __init__(self, price_cents: int = 42500, hold_minutes: int = 15):
        self.price_cents, self.hold_minutes = price_cents, hold_minutes
        self.bookings: dict[str, dict[str, Any]] = {}
        self.received: list[dict[str, Any]] = []  # what each book() call was sent, for tests

    async def quote(self, session_ref: str, attendees: int) -> Quote:
        if session_ref.startswith("gone:"):
            raise ProviderError("not_found", "The camp's system no longer lists this session.")
        return Quote(
            provider_quote_id=f"sbx_q_{uuid.uuid4().hex[:12]}", seller="Sandbox Camp Co.", item=session_ref,
            price_cents=self.price_cents * attendees, currency="usd",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=self.hold_minutes),
            required_fields=list(REQUIRED), terms_url="https://sandbox.example/terms",
            availability="waitlist" if session_ref.startswith("full:") else "available",
        )

    async def book(self, quote: Quote, attendee: dict[str, Any], idempotency_key: str) -> Booked:
        extra = set(attendee) - set(quote.required_fields)
        if extra:
            raise ProviderError("unexpected_fields", f"Sent fields the camp didn't ask for: {sorted(extra)}")
        if idempotency_key in self.bookings:
            return self.bookings[idempotency_key]["booked"]
        if quote.expires_at < datetime.now(timezone.utc):
            raise ProviderError("hold_expired", "The hold on this spot expired. Get a new quote.")
        self.received.append(dict(attendee))
        booked = Booked(provider_ref=f"sbx_b_{uuid.uuid4().hex[:12]}",
                        status="waitlisted" if quote.availability == "waitlist" else "registered",
                        amount_due_cents=0 if quote.availability == "waitlist" else quote.price_cents,
                        payment_url="https://sandbox.example/pay")
        self.bookings[idempotency_key] = {"booked": booked, "attendee": attendee}
        return booked

    async def cancel(self, provider_ref: str) -> None:
        for key, b in list(self.bookings.items()):
            if b["booked"].provider_ref == provider_ref:
                del self.bookings[key]
                return
        raise ProviderError("not_found", "No such booking")
