"""Who the assistant is acting for in the current chat turn, for permissions and the audit log."""

from __future__ import annotations

from contextvars import ContextVar

from campfinder.auth import FamilyAccess

_current: ContextVar[FamilyAccess | None] = ContextVar("household_actor", default=None)


def acting_as(access: FamilyAccess | None) -> None:
    _current.set(access)


def current_access() -> FamilyAccess | None:
    return _current.get()
