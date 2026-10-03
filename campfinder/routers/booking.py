"""
Registration day: track registrations, the register-now checklist, info kit packages
for a camp's form, reminders, and (behind a flag, sandbox only) quote-then-book.

Nothing here registers, pays or shares on its own. Sharing a package needs the signed-in
parent to confirm the exact fields; the agent can only propose.
"""

from __future__ import annotations

import hmac
import os
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response

from campfinder.auth import authorize_family, optional_user, required_user
from campfinder.booking import bookings, forms, reminders, service
from campfinder.booking.models import (
    PackageConfirm, PackagePreview, PackageRequest, RegisterChecklist, Registration, RegistrationCreate,
    RegistrationFormView, RegistrationUpdate, ReminderPreview, ReminderPrefs,
)
from campfinder.config import get_settings

router = APIRouter()


# ---------------------------------------------------------------------------
# Public: when registration opens and what the form asks
# ---------------------------------------------------------------------------

@router.get("/camps/{camp_id}/registration", summary="When registration opens and what the form asks for")
async def camp_registration(camp_id: UUID, session_id: UUID | None = None) -> dict:
    camp = service.get_camp_row(str(camp_id))
    window = service.camp_window(str(camp_id), str(session_id) if session_id else None)
    form: RegistrationFormView = forms.form_view(str(camp_id), None, [])
    return {
        "camp_id": str(camp_id),
        "registration_url": camp.get("registration_url"),
        "opens_at": window.get("opens_at") if window else None,
        "closes_at": window.get("closes_at") if window else None,
        "verified": bool(window and window.get("verified")),
        "source_url": window.get("source_url") if window else None,
        "form": form.model_dump(mode="json"),
    }


# ---------------------------------------------------------------------------
# Tracked registrations (guest families too: the calendar works for them)
# ---------------------------------------------------------------------------

@router.get("/families/{family_id}/registrations", response_model=list[Registration], summary="Registrations")
async def list_registrations(family_id: UUID, user_id: str | None = Depends(optional_user)) -> list[Registration]:
    authorize_family(family_id, user_id)
    return service.list_registrations(str(family_id))


@router.post("/families/{family_id}/registrations", response_model=Registration, status_code=201,
             summary="Watch a camp or session for registration")
async def create_registration(family_id: UUID, req: RegistrationCreate,
                              user_id: str | None = Depends(optional_user)) -> Registration:
    authorize_family(family_id, user_id)
    return service.create_registration(str(family_id), req)


@router.patch("/families/{family_id}/registrations/{registration_id}", response_model=Registration,
              summary="Record registered, waitlisted or paid")
async def update_registration(family_id: UUID, registration_id: UUID, req: RegistrationUpdate,
                              user_id: str | None = Depends(optional_user)) -> Registration:
    authorize_family(family_id, user_id)
    return service.update_registration(str(family_id), str(registration_id), req)


@router.delete("/families/{family_id}/registrations/{registration_id}", status_code=204, summary="Stop tracking")
async def delete_registration(family_id: UUID, registration_id: UUID,
                              user_id: str | None = Depends(optional_user)) -> Response:
    authorize_family(family_id, user_id)
    service.delete_registration(str(family_id), str(registration_id))
    return Response(status_code=204)


@router.get("/families/{family_id}/register-checklist", response_model=RegisterChecklist,
            summary="Register-now checklist for a camp or session")
async def register_checklist(
    family_id: UUID,
    camp_id: UUID | None = None,
    session_id: UUID | None = None,
    child: str | None = Query(default=None, max_length=80),
    registration_id: UUID | None = None,
    user_id: str | None = Depends(optional_user),
) -> RegisterChecklist:
    family = authorize_family(family_id, user_id)
    if camp_id is None and registration_id is None:
        raise HTTPException(status_code=422, detail="Pass camp_id or registration_id")
    return service.checklist(family, str(camp_id) if camp_id else "", str(session_id) if session_id else None,
                             child, str(registration_id) if registration_id else None)


# ---------------------------------------------------------------------------
# Info kit package for a camp's form (account required, parent confirms)
# ---------------------------------------------------------------------------

@router.post("/families/{family_id}/registration-package/preview", response_model=PackagePreview,
             summary="Preview the package this camp's form needs (shares nothing)")
async def preview_package(family_id: UUID, req: PackageRequest, user_id: str = Depends(required_user)) -> PackagePreview:
    family = authorize_family(family_id, user_id, require_owner=True)
    return service.preview_package(family, str(req.camp_id), req.children,
                                   str(req.registration_id) if req.registration_id else None)


@router.post("/families/{family_id}/registration-package", status_code=201,
             summary="Share the package the parent approved")
async def confirm_package(family_id: UUID, req: PackageConfirm, user_id: str = Depends(required_user)) -> dict:
    family = authorize_family(family_id, user_id, require_owner=True)
    share, token = service.confirm_package(family, req)
    return {"share": share, "url": f"{get_settings().frontend_url.rstrip('/')}/share/{token}"}


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------

@router.get("/families/{family_id}/registration-reminders", response_model=ReminderPrefs, summary="Reminder settings")
async def get_reminder_prefs(family_id: UUID, user_id: str = Depends(required_user)) -> ReminderPrefs:
    family = authorize_family(family_id, user_id, require_owner=True)
    prefs = reminders.load_prefs(str(family_id))
    if not prefs.email:
        prefs.email = reminders.account_email(family)
    return prefs


@router.put("/families/{family_id}/registration-reminders", response_model=ReminderPrefs, summary="Change reminder settings")
async def put_reminder_prefs(family_id: UUID, prefs: ReminderPrefs, user_id: str = Depends(required_user)) -> ReminderPrefs:
    authorize_family(family_id, user_id, require_owner=True)
    return reminders.save_prefs(str(family_id), prefs)


@router.get("/families/{family_id}/registration-reminders/preview", response_model=list[ReminderPreview],
            summary="Reminders that would go out on a day (sends nothing)")
async def preview_reminders(family_id: UUID, on: date | None = None,
                            user_id: str = Depends(required_user)) -> list[ReminderPreview]:
    authorize_family(family_id, user_id, require_owner=True)
    return reminders.preview_for_family(str(family_id), on)


@router.post("/internal/registration-reminders/run", summary="Cron: send today's registration reminders")
async def run_reminders(dry_run: bool = False, on: date | None = None,
                        x_cron_secret: str | None = Header(default=None)) -> dict:
    secret = os.environ.get("BOOKING_CRON_SECRET", "")
    if not secret or not x_cron_secret or not hmac.compare_digest(secret, x_cron_secret):
        raise HTTPException(status_code=404, detail="Not found")
    return await reminders.run(on, dry_run)


# ---------------------------------------------------------------------------
# Quote-then-book prototype: off unless BOOKING_PROVIDERS is set; sandbox only
# ---------------------------------------------------------------------------

@router.get("/booking/status", summary="Is booking through CampFinder switched on (sandbox)?")
async def booking_status() -> dict:
    return {"enabled": bookings.is_enabled(), "environment": "sandbox"}


@router.post("/families/{family_id}/bookings/quote", response_model=bookings.QuoteView,
             summary="Price and hold a session (sends no personal data)")
async def booking_quote(family_id: UUID, req: bookings.QuoteRequest,
                        user_id: str = Depends(required_user)) -> bookings.QuoteView:
    family = authorize_family(family_id, user_id, require_owner=True)
    return await bookings.quote(family, req)


@router.post("/families/{family_id}/bookings/{attempt_id}/confirm", summary="Book, after the parent confirms the quote")
async def booking_confirm(family_id: UUID, attempt_id: UUID, req: bookings.ConfirmRequest,
                          user_id: str = Depends(required_user)) -> dict:
    family = authorize_family(family_id, user_id, require_owner=True)
    return await bookings.confirm(family, user_id, str(attempt_id), req)
