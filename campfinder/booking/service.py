"""
Registration day for one family: what they're watching or registered for, when
registration opens, the register-now checklist, and info kit packages for a camp's form.

The parent does the registering on the camp's own site. CampFinder tracks it, reminds
her, puts dates on the family calendar, and prepares an info kit package she can
share; nothing is registered, paid or shared without her doing it.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from campfinder.booking import forms
from campfinder.booking.models import (
    ChecklistStep, PackageConfirm, PackagePreview, RegisterChecklist, Registration,
    RegistrationCreate, RegistrationUpdate,
)
from campfinder.database import get_supabase
from campfinder.kit import service as kit_service
from campfinder.kit.models import InfoKit, ShareCreate

ACTIVE = ("watching", "registered", "waitlisted")


def local_tz() -> ZoneInfo:
    return ZoneInfo(os.environ.get("REMINDER_TZ", "America/New_York"))


def local_today() -> date:
    return datetime.now(local_tz()).date()


def _parse_ts(v: Any) -> datetime | None:
    if v is None or isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def _parse_date(v: Any) -> date | None:
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Camps, sessions and registration windows
# ---------------------------------------------------------------------------

def get_camp_row(camp_id: str) -> dict[str, Any]:
    rows = get_supabase().table("camps").select("*").eq("id", camp_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Camp not found")
    return rows[0]


def get_session_row(camp_id: str, session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None
    rows = get_supabase().table("sessions").select("*").eq("id", session_id).eq("camp_id", camp_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="That session isn't part of this camp")
    return rows[0]


def camp_window(camp_id: str, session_id: str | None) -> dict[str, Any] | None:
    """The registration window that applies: the session's own, else the camp's. Prefers
    the next upcoming opening, else the most recent one."""
    rows = get_supabase().table("registration_windows").select("*").eq("camp_id", camp_id).execute().data or []
    specific = [r for r in rows if session_id and str(r.get("session_id")) == str(session_id)]
    general = [r for r in rows if not r.get("session_id")]
    pool = specific or general
    if not pool:
        return None
    now = datetime.now(timezone.utc)
    upcoming = sorted((r for r in pool if _parse_ts(r["opens_at"]) >= now), key=lambda r: _parse_ts(r["opens_at"]))
    past = sorted((r for r in pool if _parse_ts(r["opens_at"]) < now), key=lambda r: _parse_ts(r["opens_at"]), reverse=True)
    return (upcoming or past)[0]


def resolve_opens(row: dict[str, Any]) -> tuple[datetime | None, str | None, datetime | None]:
    """(opens_at, source, closes_at). The family's own date wins: she may know better."""
    window = camp_window(str(row["camp_id"]), row.get("session_id"))
    closes = _parse_ts(window.get("closes_at")) if window else None
    if row.get("opens_at"):
        return _parse_ts(row["opens_at"]), "family", closes
    if window:
        return _parse_ts(window["opens_at"]), "camp", closes
    return None, None, None


# ---------------------------------------------------------------------------
# Next step, in one line
# ---------------------------------------------------------------------------

def _fmt_day(d: date) -> str:
    return f"{d:%a %b} {d.day}"


def _fmt_when(ts: datetime) -> str:
    local = ts.astimezone(local_tz())
    t = local.strftime("%I:%M %p").lstrip("0").lower()
    return f"{_fmt_day(local.date())} at {t}"


def next_step(r: dict[str, Any], opens_at: datetime | None, today: date | None = None) -> str:
    today = today or local_today()
    status, pay = r["status"], r.get("payment_status") or "unpaid"
    if status == "cancelled":
        return "Cancelled. Check the camp's refund policy if you paid."
    if status == "watching":
        if opens_at is None:
            return "Registration date not known yet. Add it if the camp has announced it."
        opens_day = opens_at.astimezone(local_tz()).date()
        if opens_day > today:
            days = (opens_day - today).days
            return f"Registration opens {_fmt_when(opens_at)} ({'tomorrow' if days == 1 else f'in {days} days'})."
        return "Registration is open. Register on the camp's site, then mark it here."
    steps = []
    if status == "waitlisted":
        steps.append("On the waitlist. Mark it registered if a spot opens.")
    due = _parse_date(r.get("payment_due_date"))
    if pay in ("unpaid", "deposit") and due:
        late = " (overdue)" if due < today else ""
        bal = f"${float(r['balance_due']):,.0f} " if r.get("balance_due") else ""
        steps.append(f"Pay {bal}by {_fmt_day(due)}{late}.")
    forms_due = _parse_date(r.get("forms_due_date"))
    if forms_due and forms_due >= today:
        steps.append(f"Forms due {_fmt_day(forms_due)}.")
    if not steps:
        return "All set." if pay == "paid" or status == "registered" else "Nothing due."
    return " ".join(steps)


# ---------------------------------------------------------------------------
# Registrations
# ---------------------------------------------------------------------------

def _rows(family_id: str) -> list[dict[str, Any]]:
    return get_supabase().table("family_registrations").select("*").eq("family_id", family_id).execute().data or []


def _row(family_id: str, registration_id: str) -> dict[str, Any]:
    rows = (get_supabase().table("family_registrations").select("*")
            .eq("id", registration_id).eq("family_id", family_id).execute().data)
    if not rows:
        raise HTTPException(status_code=404, detail="Registration not found")
    return rows[0]


def to_model(r: dict[str, Any], camp: dict[str, Any] | None = None, session: dict[str, Any] | None = None,
             today: date | None = None) -> Registration:
    camp = camp or get_camp_row(str(r["camp_id"]))
    if session is None and r.get("session_id"):
        rows = get_supabase().table("sessions").select("*").eq("id", str(r["session_id"])).execute().data
        session = rows[0] if rows else None
    opens_at, source, closes_at = resolve_opens(r)
    return Registration(
        id=r["id"], camp_id=r["camp_id"], camp_name=camp["name"],
        session_id=r.get("session_id"), session_name=(session or {}).get("name"),
        start_date=_parse_date((session or {}).get("start_date")), end_date=_parse_date((session or {}).get("end_date")),
        child_name=r.get("child_name"), status=r["status"], payment_status=r.get("payment_status") or "unpaid",
        amount_paid=r.get("amount_paid"), paid_on=_parse_date(r.get("paid_on")),
        balance_due=r.get("balance_due"), payment_due_date=_parse_date(r.get("payment_due_date")),
        forms_due_date=_parse_date(r.get("forms_due_date")),
        opens_at=opens_at, opens_at_source=source, closes_at=closes_at,
        registration_url=camp.get("registration_url"), confirmation_number=r.get("confirmation_number"),
        notes=r.get("notes"), remind=r.get("remind", True),
        next_step=next_step(r, opens_at, today), created_at=_parse_ts(r["created_at"]),
    )


def list_registrations(family_id: str) -> list[Registration]:
    rows = _rows(family_id)
    order = {"registered": 0, "waitlisted": 1, "watching": 2, "cancelled": 3}
    out = [to_model(r) for r in rows]
    far = datetime.max.replace(tzinfo=timezone.utc)
    return sorted(out, key=lambda m: (order[m.status], m.opens_at or far, m.camp_name))


def create_registration(family_id: str, req: RegistrationCreate) -> Registration:
    camp = get_camp_row(str(req.camp_id))
    session = get_session_row(str(req.camp_id), str(req.session_id) if req.session_id else None)
    for r in _rows(family_id):
        same = (str(r["camp_id"]) == str(req.camp_id) and str(r.get("session_id") or "") == str(req.session_id or "")
                and (r.get("child_name") or "").lower() == (req.child_name or "").lower())
        if same and r["status"] != "cancelled":
            return to_model(r, camp, session)  # already tracked: idempotent
    row = get_supabase().table("family_registrations").insert({
        "family_id": family_id, "camp_id": str(req.camp_id),
        "session_id": str(req.session_id) if req.session_id else None,
        "child_name": req.child_name, "status": "watching", "payment_status": "unpaid",
        "opens_at": req.opens_at.isoformat() if req.opens_at else None, "notes": req.notes,
        "remind": True, "event_ids": {}, "updated_at": _now(),
    }).execute().data[0]
    row = sync_calendar(family_id, row, camp, session)
    return to_model(row, camp, session)


def update_registration(family_id: str, registration_id: str, req: RegistrationUpdate) -> Registration:
    row = _row(family_id, registration_id)
    changes = req.model_dump(mode="json", exclude_unset=True)
    camp = get_camp_row(str(row["camp_id"]))
    session_id = changes.get("session_id", row.get("session_id"))
    session = get_session_row(str(row["camp_id"]), str(session_id) if session_id else None)
    if changes.get("status") in ("registered", "waitlisted") and not row.get("registered_at"):
        changes["registered_at"] = _now()
    if changes.get("payment_status") == "paid":
        changes.setdefault("balance_due", None)
        if not changes.get("paid_on") and not row.get("paid_on"):
            changes["paid_on"] = local_today().isoformat()
    changes["updated_at"] = _now()
    get_supabase().table("family_registrations").update(changes).eq("id", registration_id).execute()
    row.update(changes)
    row = sync_calendar(family_id, row, camp, session)
    return to_model(row, camp, session)


def delete_registration(family_id: str, registration_id: str) -> None:
    row = _row(family_id, registration_id)
    _delete_events(family_id, list((row.get("event_ids") or {}).values()))
    get_supabase().table("family_registrations").delete().eq("id", registration_id).execute()


# ---------------------------------------------------------------------------
# Family calendar
# ---------------------------------------------------------------------------

def _delete_events(family_id: str, ids: list[str]) -> None:
    for eid in ids:
        get_supabase().table("family_events").delete().eq("id", str(eid)).eq("family_id", family_id).execute()


def desired_events(row: dict[str, Any], camp: dict[str, Any], session: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """The calendar entries this registration should have right now, by kind."""
    status, pay = row["status"], row.get("payment_status") or "unpaid"
    who = f"{row['child_name']}: " if row.get("child_name") else ""
    base = {"child_name": row.get("child_name"), "camp_id": str(row["camp_id"]),
            "session_id": str(session["id"]) if session else None}
    out: dict[str, dict[str, Any]] = {}
    if status == "cancelled":
        return out
    if status == "watching":
        opens_at, _, _ = resolve_opens(row)
        if opens_at:
            day = opens_at.astimezone(local_tz()).date().isoformat()
            out["opens"] = {**base, "title": f"Registration opens: {camp['name']}", "start_date": day, "end_date": day,
                            "notes": f"Opens {_fmt_when(opens_at)}." + (f"\nRegister: {camp['registration_url']}"
                                                                       if camp.get("registration_url") else "")}
    elif session:
        tag = " (waitlist)" if status == "waitlisted" else ""
        notes = [f"Confirmation {row['confirmation_number']}" if row.get("confirmation_number") else None,
                 "Paid" if pay == "paid" else ("Deposit paid" if pay == "deposit" else None)]
        out["session"] = {**base, "title": f"{who}{camp['name']}{tag}", "start_date": str(session["start_date"]),
                          "end_date": str(session["end_date"]), "notes": " · ".join(n for n in notes if n) or None}
    due = row.get("payment_due_date")
    if due and status != "watching" and pay in ("unpaid", "deposit"):
        amount = f" (${float(row['balance_due']):,.0f})" if row.get("balance_due") else ""
        out["payment_due"] = {**base, "title": f"Payment due: {camp['name']}{amount}", "start_date": str(due)[:10],
                              "end_date": str(due)[:10], "notes": None}
    forms_due = row.get("forms_due_date")
    if forms_due and status != "watching":
        out["forms_due"] = {**base, "title": f"{who}forms due for {camp['name']}", "start_date": str(forms_due)[:10],
                            "end_date": str(forms_due)[:10], "notes": "Your info kit package can fill most of it."}
    return out


def _adopt_session_event(family_id: str, row: dict[str, Any], session: dict[str, Any] | None) -> str | None:
    """If the agent already put this session on the calendar, update that entry instead of
    adding a second one."""
    if not session:
        return None
    events = (get_supabase().table("family_events").select("*").eq("family_id", family_id)
              .eq("session_id", str(session["id"])).execute().data or [])
    taken = {str(v) for r in _rows(family_id) for v in (r.get("event_ids") or {}).values()}
    for e in events:
        same_kid = (e.get("child_name") or "").lower() == (row.get("child_name") or "").lower() or not e.get("child_name")
        if same_kid and str(e["id"]) not in taken:
            return str(e["id"])
    return None


def sync_calendar(family_id: str, row: dict[str, Any], camp: dict[str, Any], session: dict[str, Any] | None) -> dict[str, Any]:
    """Make the family calendar match this registration. Only touches entries it owns."""
    sb = get_supabase()
    have: dict[str, str] = dict(row.get("event_ids") or {})
    want = desired_events(row, camp, session)
    if "session" in want and "session" not in have:
        adopted = _adopt_session_event(family_id, row, session)
        if adopted:
            have["session"] = adopted
    for kind, event in want.items():
        values = {k: v for k, v in event.items()}
        if kind in have:
            updated = sb.table("family_events").update(values).eq("id", have[kind]).eq("family_id", family_id).execute().data
            if updated:
                continue
        have[kind] = sb.table("family_events").insert({"family_id": family_id, **values}).execute().data[0]["id"]
    for kind in [k for k in have if k not in want]:
        _delete_events(family_id, [have.pop(kind)])
    if have != (row.get("event_ids") or {}):
        sb.table("family_registrations").update({"event_ids": have}).eq("id", str(row["id"])).execute()
        row["event_ids"] = have
    return row


# ---------------------------------------------------------------------------
# Info kit packages for a camp's form
# ---------------------------------------------------------------------------

def _kit_or_none(family: dict[str, Any]) -> InfoKit | None:
    """The decrypted kit, for readiness checks only. None for guests or if unavailable."""
    if family.get("owner_user_id") is None:
        return None
    try:
        return kit_service.load_kit(str(family["id"]))
    except HTTPException:
        return None


def _default_children(family_id: str, kit: InfoKit | None, registration_id: str | None, children: list[str]) -> list[str]:
    if children:
        return children
    if registration_id:
        kid = _row(family_id, registration_id).get("child_name")
        if kid:
            return [kid]
    if kit and len(kit.children) == 1:
        return [kit.children[0].name]
    return []


def preview_package(family: dict[str, Any], camp_id: str, children: list[str],
                    registration_id: str | None = None) -> PackagePreview:
    camp = get_camp_row(camp_id)
    kit = _kit_or_none(family)
    kids = _default_children(str(family["id"]), kit, registration_id, children)
    return forms.propose_package(camp_id, camp["name"], kit, kids)


def confirm_package(family: dict[str, Any], req: PackageConfirm) -> tuple[dict[str, Any], str]:
    """Create the share the parent approved on the preview. Never called by the agent."""
    if req.confirm is not True:
        raise HTTPException(status_code=422, detail="Confirm on the preview to share")
    camp = get_camp_row(str(req.camp_id))
    share, token = kit_service.create_share(str(family["id"]), ShareCreate(
        recipient=camp["name"], camp_id=req.camp_id, children=req.children,
        household_fields=req.household_fields, child_fields=req.child_fields if req.children else [],
        expires_in_days=req.expires_in_days,
    ))
    return share.model_dump(mode="json"), token


# ---------------------------------------------------------------------------
# Register-now checklist
# ---------------------------------------------------------------------------

def checklist(family: dict[str, Any], camp_id: str, session_id: str | None, child_name: str | None,
              registration_id: str | None = None) -> RegisterChecklist:
    family_id = str(family["id"])
    reg_row = _row(family_id, registration_id) if registration_id else None
    if reg_row:
        camp_id = str(reg_row["camp_id"])
        session_id = session_id or reg_row.get("session_id")
        child_name = child_name or reg_row.get("child_name")
    camp = get_camp_row(camp_id)
    session = get_session_row(camp_id, str(session_id) if session_id else None)
    kit = _kit_or_none(family)
    kids = _default_children(family_id, kit, None, [child_name] if child_name else [])
    form = forms.form_view(camp_id, kit, kids)

    probe = reg_row or {"camp_id": camp_id, "session_id": session_id}
    opens_at, source, closes_at = resolve_opens(probe)
    shares = []
    if family.get("owner_user_id") is not None:
        shares = [s.model_dump(mode="json") for s in kit_service.list_shares(family_id)
                  if s.active and str(s.camp_id or "") == camp_id]

    missing = [f.question for f in form.fields if f.required and f.ready is False]
    kit_ok = kit is not None
    steps = [
        ChecklistStep(key="kit", href="/kit",
                      text=("Info kit has everything this form asks for." if kit_ok and not missing else
                            f"Fill in your info kit: {', '.join(missing[:4])}{'…' if len(missing) > 4 else ''}." if kit_ok
                            else "Sign in and fill in your info kit so answers are ready to copy."),
                      done=kit_ok and not missing),
        ChecklistStep(key="package", text="Prepare a package of just what this camp asks for, ready to send or copy.",
                      done=bool(shares) if kit_ok else None),
        ChecklistStep(key="payment", text="Have a card ready. Many camps take a deposit at registration"
                      + (f"; this session is ${session['price']:,.0f}." if session and session.get("price") else ".")),
        ChecklistStep(key="other", text="Forms usually also ask for a signed waiver, a photo release and how you heard "
                      "about the camp. Those are yours to answer on the camp's site."),
        ChecklistStep(key="register", text="Register on the camp's site at opening time.",
                      href=camp.get("registration_url"),
                      done=reg_row["status"] in ("registered", "waitlisted") if reg_row else False),
        ChecklistStep(key="record", text="Come back and mark it registered, waitlisted or paid, so your calendar and "
                      "reminders update.", done=(reg_row or {}).get("payment_status") == "paid"),
    ]
    return RegisterChecklist(
        camp_id=camp_id, camp_name=camp["name"], session_id=session_id, session_name=(session or {}).get("name"),
        registration_url=camp.get("registration_url"), opens_at=opens_at, opens_at_source=source, closes_at=closes_at,
        price=float(session["price"]) if session and session.get("price") else None,
        availability=(session or {}).get("availability"), refund_policy=camp.get("refund_policy_summary"),
        form=form, kit_available=kit_ok, shares=shares, steps=steps,
        registration=to_model(reg_row, camp, session) if reg_row else None,
    )
