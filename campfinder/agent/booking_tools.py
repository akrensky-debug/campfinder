"""
Registration-day tools for the family agent.

The agent can watch camps for registration, record what the parent says happened
(registered, waitlisted, paid), read the register-now checklist, and propose an info
kit package. It cannot share a package, book or pay: proposals render as a card that
sends the parent to the Register page, where she reviews the fields and confirms
herself. Kit values never reach the model; only which fields are filled.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from campfinder.agent.tools import ALL_TOOLS, FAMILY_TOOLS, ToolError, ToolOutput, ToolSpec
from campfinder.booking import service
from campfinder.booking.models import Registration, RegistrationCreate, RegistrationUpdate
from campfinder.database import get_supabase


class WatchRegistrationInput(BaseModel):
    camp_id: UUID
    session_id: UUID | None = Field(default=None, description="A specific session, from get_camp_details.")
    child_name: str | None = Field(default=None, description="First name from the family profile.")
    opens_at: datetime | None = Field(
        default=None, description="Only if the parent told you when registration opens and we don't have it.")


class RecordRegistrationInput(BaseModel):
    registration_id: UUID = Field(description="From list_registrations or watch_registration.")
    status: Literal["registered", "waitlisted", "cancelled"] | None = None
    payment_status: Literal["unpaid", "deposit", "paid", "refunded"] | None = None
    amount_paid: float | None = Field(default=None, ge=0)
    paid_on: date | None = None
    balance_due: float | None = Field(default=None, ge=0)
    payment_due_date: date | None = None
    forms_due_date: date | None = None


class ListRegistrationsInput(BaseModel):
    pass


class RegistrationChecklistInput(BaseModel):
    registration_id: UUID | None = None
    camp_id: UUID | None = None
    session_id: UUID | None = None
    child_name: str | None = None


class ProposePackageInput(BaseModel):
    camp_id: UUID
    registration_id: UUID | None = None
    child_name: str | None = None


def _family(family_id: str) -> dict[str, Any]:
    rows = get_supabase().table("families").select("*").eq("id", family_id).execute().data
    if not rows:
        raise ToolError("Family not found")
    return rows[0]


def _compact(r: Registration) -> dict[str, Any]:
    keys = ("id", "camp_id", "camp_name", "session_id", "session_name", "start_date", "child_name", "status",
            "payment_status", "balance_due", "payment_due_date", "forms_due_date", "opens_at", "next_step")
    data = r.model_dump(mode="json")
    return {k: data[k] for k in keys if data.get(k) is not None}


def _ui(family_id: str) -> dict[str, Any]:
    return {"type": "registrations",
            "registrations": [r.model_dump(mode="json") for r in service.list_registrations(family_id)]}


async def watch_registration_tool(inp: WatchRegistrationInput, family_id: str) -> ToolOutput:
    r = service.create_registration(family_id, RegistrationCreate(**inp.model_dump()))
    return ToolOutput(content={"saved": True, "registration": _compact(r)}, ui=_ui(family_id))


async def record_registration_tool(inp: RecordRegistrationInput, family_id: str) -> ToolOutput:
    changes = inp.model_dump(exclude={"registration_id"}, exclude_none=True)
    if not changes:
        raise ToolError("Nothing to record")
    r = service.update_registration(family_id, str(inp.registration_id), RegistrationUpdate(**changes))
    return ToolOutput(content={"saved": True, "registration": _compact(r)}, ui=_ui(family_id))


async def list_registrations_tool(inp: ListRegistrationsInput, family_id: str) -> ToolOutput:
    regs = service.list_registrations(family_id)
    return ToolOutput(content={"registrations": [_compact(r) for r in regs]}, ui=_ui(family_id) if regs else None)


async def registration_checklist_tool(inp: RegistrationChecklistInput, family_id: str) -> ToolOutput:
    if not inp.registration_id and not inp.camp_id:
        raise ToolError("Pass registration_id or camp_id")
    c = service.checklist(_family(family_id), str(inp.camp_id or ""), str(inp.session_id) if inp.session_id else None,
                          inp.child_name, str(inp.registration_id) if inp.registration_id else None)
    content = {
        "camp": c.camp_name, "session": c.session_name, "registration_url": c.registration_url,
        "opens_at": c.opens_at, "price": c.price, "availability": c.availability,
        "form_is_typical": c.form.typical, "kit_available": c.kit_available,
        "kit_missing": [f.question for f in c.form.fields if f.required and f.ready is False],
        "answer_on_camp_site": [f.question for f in c.form.fields if f.kit_field is None],
        "package_already_shared": bool(c.shares),
    }
    return ToolOutput(content=content, ui={"type": "register_checklist", "checklist": c.model_dump(mode="json")})


async def propose_package_tool(inp: ProposePackageInput, family_id: str) -> ToolOutput:
    family = _family(family_id)
    if family.get("owner_user_id") is None:
        raise ToolError("The info kit needs an account. Suggest the parent signs in first.")
    kids = [inp.child_name] if inp.child_name else []
    p = service.preview_package(family, str(inp.camp_id), kids, str(inp.registration_id) if inp.registration_id else None)
    labels = {**p.labels}
    content = {
        "proposed": True, "shared": False,
        "note": "Nothing has been shared. The parent reviews the fields and presses Share on the card herself.",
        "camp": p.recipient, "children": p.children,
        "fields": [labels.get(f, f) for f in p.household_fields + p.child_fields],
        "kit_missing": p.missing, "answer_on_camp_site": p.not_in_kit,
    }
    ui = {"type": "registration_package", "package": p.model_dump(mode="json"),
          "registration_id": str(inp.registration_id) if inp.registration_id else None}
    return ToolOutput(content=content, ui=ui)


BOOKING_TOOLS: list[ToolSpec] = [
    ToolSpec(
        "watch_registration",
        "Track a camp or session the family wants, so CampFinder reminds the parent before registration opens "
        "and puts opening day on the calendar. Use when she picks a camp that isn't open yet, or asks to be "
        "reminded. Does not register anything.",
        WatchRegistrationInput, watch_registration_tool, family=True, status="Saving to your registrations",
    ),
    ToolSpec(
        "record_registration",
        "Record what the parent tells you she did on the camp's site: registered, waitlisted, cancelled, paid "
        "(with amount and date), and payment or form deadlines. Updates the family calendar and reminders. "
        "Only record what she says happened; never assume a registration or payment went through.",
        RecordRegistrationInput, record_registration_tool, family=True, status="Updating your registrations",
    ),
    ToolSpec(
        "list_registrations",
        "Camps the family is watching or registered for, with status, payments, deadlines and the next step.",
        ListRegistrationsInput, list_registrations_tool, family=True, status="Checking your registrations",
    ),
    ToolSpec(
        "registration_checklist",
        "Register-now checklist for a camp or session: the registration link, when it opens, price, what the "
        "form asks, which answers the info kit is missing (names of fields only), and what she must answer on "
        "the camp's site (waivers, payment).",
        RegistrationChecklistInput, registration_checklist_tool, family=True, status="Preparing the checklist",
    ),
    ToolSpec(
        "propose_registration_package",
        "Propose an info kit package with just the fields this camp's registration form asks for. Shows the "
        "parent a card to review and share; you cannot share it, and nothing is sent until she presses Share.",
        ProposePackageInput, propose_package_tool, family=True, status="Preparing a package for review",
    ),
]

FAMILY_TOOLS.extend(BOOKING_TOOLS)
ALL_TOOLS.update({t.name: t for t in BOOKING_TOOLS})

BOOKING_PROMPT = """

Registration day:
- When the parent settles on a camp, offer to watch it for registration (watch_registration) so she gets \
a reminder and opening day lands on the calendar. When it's open or opening soon, use \
registration_checklist and give her the link and the one or two things she still needs.
- She registers and pays on the camp's own site. You never register, pay, sign waivers or accept a \
camp's terms for her, and you can't share her info kit: propose_registration_package only shows her a \
card to review and confirm herself. Say so plainly if she asks you to do it for her.
- When she tells you she registered, joined a waitlist or paid, record it with record_registration, \
including amounts and any payment or form deadlines she mentions.\
"""


def registrations_context(family_id: str) -> str:
    """One context line for the agent's first turn. Never fails the turn."""
    try:
        regs = service.list_registrations(family_id)
    except Exception:
        return ""
    if not regs:
        return ""
    return f"Registrations: {[_compact(r) for r in regs if r.status != 'cancelled']}\n"
