"""
Registration platforms CampFinder could book through, behind a feature flag.

Only sandbox providers exist. BOOKING_PROVIDERS lists the enabled ones (default: none),
and get_provider refuses anything whose environment isn't 'sandbox'; the database
also rejects non-sandbox booking attempts. A live adapter needs a signed partner
agreement, the platform's approval and legal review first (docs/booking-strategy.md).
"""

from __future__ import annotations

import os

from campfinder.booking.providers.base import BookingProvider, ProviderError
from campfinder.booking.providers.sandbox import SandboxProvider

_REGISTRY: dict[str, BookingProvider] = {}


def enabled_names() -> set[str]:
    return {n.strip().lower() for n in os.environ.get("BOOKING_PROVIDERS", "").split(",") if n.strip()}


def get_provider(name: str | None) -> BookingProvider | None:
    """The provider for a camp's platform, if booking through it is switched on."""
    if not name or name.lower() not in enabled_names():
        return None
    provider = _REGISTRY.get(name.lower())
    if provider is None and name.lower() == "sandbox":
        provider = _REGISTRY.setdefault("sandbox", SandboxProvider())
    if provider is None or provider.environment != "sandbox":
        return None
    return provider


def register(provider: BookingProvider) -> None:
    """Tests install fakes here. Non-sandbox providers are never served."""
    _REGISTRY[provider.name] = provider


def reset() -> None:
    _REGISTRY.clear()


__all__ = ["BookingProvider", "ProviderError", "get_provider", "register", "reset", "enabled_names"]
