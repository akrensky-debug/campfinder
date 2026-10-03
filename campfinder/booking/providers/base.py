"""
The interface a registration platform adapter implements: quote, then book.

Modelled on the OpenActive Open Booking API: a quote carries no personal data (C1);
the booking sends only the fields the seller says it needs, after the parent has seen
the price, the seller, the terms and the exact fields, and confirmed (C2 + B). The
camp is the seller and merchant of record; CampFinder is the parent's tool (an
OpenActive "AgentBroker"), never the seller.

A Pike13 adapter would map: quote -> GET enrollment_eligibilities + POST /bookings with
complete_booking=false (a hold of up to 20 minutes); book -> create or find the person,
put them on the lease, PUT complete_booking=true; cancel -> DELETE the booking or visit.
Not built: Pike13 has no self-serve sandbox (see docs/booking-strategy.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


class ProviderError(Exception):
    """The platform refused or failed. `code` is stable; the message is shown to the parent."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class Quote:
    provider_quote_id: str
    seller: str                       # the camp, which is the merchant of record
    item: str                         # what is being booked, as the seller names it
    price_cents: int
    currency: str
    expires_at: datetime              # hold expiry; the price is guaranteed until then
    required_fields: list[str]        # kit fields the seller needs: 'child.name', 'household.parents', ...
    terms_url: str | None = None      # the seller's own terms, shown to the parent, never accepted for her
    payment: str = "pay_camp"         # pay_camp: the camp collects payment on its own system
    availability: str = "available"   # available | waitlist
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Booked:
    provider_ref: str
    status: str                       # registered | waitlisted
    amount_due_cents: int
    payment_url: str | None = None


class BookingProvider(Protocol):
    name: str
    environment: str                  # only 'sandbox' is ever served

    async def quote(self, session_ref: str, attendees: int) -> Quote:
        """Price and availability for a session. No personal data is sent."""
        ...

    async def book(self, quote: Quote, attendee: dict[str, Any], idempotency_key: str) -> Booked:
        """Complete the held booking with only the fields in quote.required_fields."""
        ...

    async def cancel(self, provider_ref: str) -> None:
        ...
