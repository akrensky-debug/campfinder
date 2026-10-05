"""
What a camp's registration form asks for, mapped onto the family info kit.

A mapping is a list of the form's questions, each pointing at a kit field
('household.<field>', 'child.<field>' or 'child.name') or at nothing when the kit
can't answer it. Camps we haven't mapped get TYPICAL_FORM, labelled as typical.

Readiness is computed here, server-side, from the decrypted kit; only booleans and
kid names leave this module. Kit values never reach the AI model.
"""

from __future__ import annotations

from typing import Any

from campfinder.booking.models import FormField, FormFieldStatus, PackagePreview, RegistrationFormView
from campfinder.database import get_supabase
from campfinder.kit.models import CHILD_FIELDS, HOUSEHOLD_FIELDS, InfoKit

KIT_LABELS: dict[str, str] = {
    "household.parents": "Parents / guardians",
    "household.home_address": "Home address",
    "household.emergency_contacts": "Emergency contacts",
    "household.authorized_pickups": "Authorized pickups",
    "household.insurance_provider": "Insurance provider",
    "household.insurance_member_id": "Insurance member ID",
    "household.insurance_group_number": "Insurance group number",
    "household.pediatrician_name": "Pediatrician",
    "household.pediatrician_phone": "Pediatrician phone",
    "child.name": "Child's name",
    "child.date_of_birth": "Date of birth",
    "child.grade": "Grade",
    "child.allergies": "Allergies",
    "child.medications": "Medications",
    "child.medical_conditions": "Medical conditions",
    "child.dietary_needs": "Dietary needs",
    "child.swim_ability": "Swim ability",
    "child.tshirt_size": "T-shirt size",
    "child.notes": "Notes for staff",
}

# What most US day-camp registration forms ask (CampMinder, UltraCamp, CampBrain and
# custom forms share this core). Used until a camp's own form is mapped.
TYPICAL_FORM: list[FormField] = [
    FormField(question="Camper's legal name", kit_field="child.name"),
    FormField(question="Camper's date of birth", kit_field="child.date_of_birth"),
    FormField(question="Grade in the fall", kit_field="child.grade"),
    FormField(question="Parent / guardian names, phone and email", kit_field="household.parents"),
    FormField(question="Home address", kit_field="household.home_address"),
    FormField(question="Emergency contacts (other than parents)", kit_field="household.emergency_contacts"),
    FormField(question="People allowed to pick up", kit_field="household.authorized_pickups"),
    FormField(question="Allergies", kit_field="child.allergies"),
    FormField(question="Medications", kit_field="child.medications"),
    FormField(question="Medical conditions", kit_field="child.medical_conditions", required=False),
    FormField(question="Dietary restrictions", kit_field="child.dietary_needs", required=False),
    FormField(question="Health insurance carrier and policy number", kit_field="household.insurance_provider"),
    FormField(question="Insurance member ID", kit_field="household.insurance_member_id"),
    FormField(question="Physician name and phone", kit_field="household.pediatrician_name"),
    FormField(question="T-shirt size", kit_field="child.tshirt_size", required=False),
    FormField(question="Swim level", kit_field="child.swim_ability", required=False),
    FormField(question="Signed waiver and photo release", kit_field=None),
    FormField(question="Payment (deposit or full)", kit_field=None),
]


def valid_kit_field(kit_field: str | None) -> bool:
    if kit_field is None or kit_field == "child.name":
        return True
    scope, _, name = kit_field.partition(".")
    return (scope == "household" and name in HOUSEHOLD_FIELDS) or (scope == "child" and name in CHILD_FIELDS)


def load_form(camp_id: str) -> tuple[list[FormField], dict[str, Any] | None]:
    """The camp's mapped form, or the typical one. Returns (fields, row or None)."""
    rows = get_supabase().table("registration_forms").select("*").eq("camp_id", camp_id).execute().data
    if not rows:
        return list(TYPICAL_FORM), None
    fields = [FormField.model_validate(f) for f in rows[0].get("fields") or []]
    return [f for f in fields if valid_kit_field(f.kit_field)], rows[0]


def _has(value: Any) -> bool:
    return value not in (None, "", [], {})


def field_ready(kit: InfoKit, kit_field: str, children: list[str]) -> tuple[bool, list[str]]:
    """Does the kit answer this field (for each chosen kid)? Returns (ready, kids missing it)."""
    scope, _, name = kit_field.partition(".")
    if scope == "household":
        return _has(getattr(kit.household, name, None)), []
    wanted = {c.lower() for c in children}
    kids = [c for c in kit.children if c.name.lower() in wanted] if wanted else []
    if not kids:
        return False, list(children)
    missing = [c.name for c in kids if not _has(getattr(c, name, None))]
    return not missing, missing


def form_view(camp_id: str, kit: InfoKit | None, children: list[str]) -> RegistrationFormView:
    fields, row = load_form(camp_id)
    out = []
    for f in fields:
        status = FormFieldStatus(**f.model_dump(), label=KIT_LABELS.get(f.kit_field or ""))
        if f.kit_field and kit is not None:
            status.ready, status.missing_for = field_ready(kit, f.kit_field, children)
        out.append(status)
    return RegistrationFormView(
        camp_id=camp_id, typical=row is None, fields=out,
        platform=(row or {}).get("platform"), form_url=(row or {}).get("form_url"),
        verified_at=(row or {}).get("verified_at"),
    )


def propose_package(camp_id: str, camp_name: str, kit: InfoKit | None, children: list[str]) -> PackagePreview:
    """The fields this camp's form needs, as an info kit package. Nothing is shared here."""
    view = form_view(camp_id, kit, children)
    household, child, missing, outside = [], [], [], []
    for f in view.fields:
        if f.kit_field is None:
            outside.append(f.question)
            continue
        scope, _, name = f.kit_field.partition(".")
        if scope == "household" and name not in household:
            household.append(name)
        elif scope == "child" and name != "name" and name not in child:
            child.append(name)
        if f.ready is False and f.required:
            missing.append(f.question + (f" ({', '.join(f.missing_for)})" if f.missing_for and scope == "child" else ""))
    return PackagePreview(
        recipient=camp_name, camp_id=camp_id, children=children,
        household_fields=household, child_fields=child if children else [],
        labels={k.split(".", 1)[1]: v for k, v in KIT_LABELS.items() if k != "child.name"},
        missing=missing, not_in_kit=outside, typical=view.typical,
    )
