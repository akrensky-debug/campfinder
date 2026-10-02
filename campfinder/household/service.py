"""
The shared plan: household members, invites, tasks, and the audit log.

Every change goes through here with an Actor, so the audit log records who did what,
from the app or through the assistant. Callers check access with campfinder.auth first;
the functions here enforce the per-role rules that depend on the row being touched
(a caregiver may only complete their own tasks, only the owner manages members).
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable

from fastapi import HTTPException

from campfinder.auth import FULL_PLAN, FamilyAccess
from campfinder.database import get_supabase
from campfinder.household.models import (
    ROLE_HELP, AuditEntry, ChecklistItem, GenerateRequest, InviteCreate, InvitePreview, Member,
    MemberUpdate, MyPrefs, Task, TaskCreate, TaskUpdate,
)

INVITE_DAYS = 7
DEFAULT_PACKING = [
    "Water bottle", "Sunscreen", "Lunch and snacks", "Hat", "Swimsuit and towel",
    "Change of clothes", "Labels on everything",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _parse_ts(v: Any) -> datetime | None:
    if v is None or isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# Actors and the audit log
# ---------------------------------------------------------------------------

@dataclass
class Actor:
    family_id: str
    member_id: str | None
    name: str
    role: str
    via: str = "app"

    @property
    def full_plan(self) -> bool:
        return self.role in FULL_PLAN


def user_email(user_id: str) -> str | None:
    try:
        res = get_supabase().auth.admin.get_user_by_id(user_id)
        return res.user.email if res and res.user else None
    except Exception:
        return None


def ensure_owner_member(family: dict[str, Any]) -> dict[str, Any] | None:
    """The owner's own member row, created the first time it's needed. None for guest families."""
    owner = family.get("owner_user_id")
    if owner is None:
        return None
    sb = get_supabase()
    rows = sb.table("family_members").select("*").eq("family_id", family["id"]).eq("user_id", str(owner)).execute().data
    if rows:
        return rows[0]
    email = user_email(str(owner)) or ""
    name = email.split("@")[0].replace(".", " ").title() if email else "Parent"
    return sb.table("family_members").insert({
        "family_id": family["id"], "user_id": str(owner), "email": email, "display_name": name or "Parent",
        "role": "owner", "status": "active", "accepted_at": _now().isoformat(),
    }).execute().data[0]


def actor_for(access: FamilyAccess, via: str = "app") -> Actor:
    member = access.member
    if access.role == "owner" and member is None:
        member = ensure_owner_member(access.family)
        access.member = member
    if member is None:
        return Actor(str(access.family["id"]), None, "You", access.role, via)
    return Actor(str(access.family["id"]), member["id"], member["display_name"], access.role, via)


def audit(actor: Actor, action: str, target_type: str | None = None, target_id: Any = None,
          detail: dict[str, Any] | None = None) -> None:
    get_supabase().table("family_audit_log").insert({
        "family_id": actor.family_id, "actor_id": actor.member_id, "actor_name": actor.name, "via": actor.via,
        "action": action, "target_type": target_type, "target_id": str(target_id) if target_id else None,
        "detail": detail or {},
    }).execute()


def list_audit(family_id: str, limit: int = 100) -> list[AuditEntry]:
    rows = (
        get_supabase().table("family_audit_log").select("*").eq("family_id", family_id)
        .order("created_at", desc=True).limit(limit).execute().data or []
    )
    return [AuditEntry(**{k: r.get(k) for k in AuditEntry.model_fields}) for r in rows]


# ---------------------------------------------------------------------------
# Members and invites
# ---------------------------------------------------------------------------

def list_member_rows(family_id: str) -> list[dict[str, Any]]:
    rows = get_supabase().table("family_members").select("*").eq("family_id", family_id).execute().data or []
    order = {"owner": 0, "co_parent": 1, "caregiver": 2, "viewer": 3}
    return sorted(rows, key=lambda r: (order.get(r["role"], 9), r["display_name"].lower()))


def member_view(row: dict[str, Any], viewer: Actor) -> Member:
    """Least data: emails and settings only for the owner and the member themselves."""
    is_you = viewer.member_id is not None and str(row["id"]) == str(viewer.member_id)
    private = is_you or viewer.role == "owner"
    return Member(
        id=row["id"], display_name=row["display_name"], role=row["role"], status=row["status"],
        email=row["email"] if private else None,
        kit_access=bool(row.get("kit_access")) if private or row["role"] == "owner" else False,
        invite_expires_at=_parse_ts(row.get("invite_expires_at")) if row["status"] == "invited" and private else None,
        reminder_pref=row.get("reminder_pref") if private else None,
        weekly_summary=row.get("weekly_summary") if private else None,
        is_you=is_you,
    )


def visible_members(actor: Actor) -> list[Member]:
    rows = list_member_rows(actor.family_id)
    if not actor.full_plan:
        rows = [r for r in rows if str(r["id"]) == str(actor.member_id)]
    return [member_view(r, actor) for r in rows]


def get_member_row(family_id: str, member_id: Any) -> dict[str, Any]:
    rows = (
        get_supabase().table("family_members").select("*")
        .eq("id", str(member_id)).eq("family_id", family_id).execute().data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No such person in this household")
    return rows[0]


def _require_owner(actor: Actor) -> None:
    if actor.role != "owner" or actor.member_id is None:
        raise HTTPException(status_code=403, detail="Only the family's owner can manage the household")


def create_invite(actor: Actor, req: InviteCreate) -> tuple[dict[str, Any], str]:
    """Add (or re-invite) a person. Returns the member row and the one-time invite token."""
    _require_owner(actor)
    sb = get_supabase()
    email = req.email.strip().lower()
    existing = [r for r in list_member_rows(actor.family_id) if r["email"].lower() == email]
    token = secrets.token_urlsafe(24)
    fields = {
        "display_name": req.display_name.strip(), "role": req.role,
        "invite_token_hash": _hash(token),
        "invite_expires_at": (_now() + timedelta(days=INVITE_DAYS)).isoformat(),
        "invited_by": actor.member_id,
    }
    if existing:
        row = existing[0]
        if row["status"] == "active":
            raise HTTPException(status_code=409, detail=f"{row['display_name']} is already in your household")
        sb.table("family_members").update(fields).eq("id", row["id"]).execute()
        row = {**row, **fields}
        action = "invite_renewed"
    else:
        row = sb.table("family_members").insert({
            "family_id": actor.family_id, "email": email, "status": "invited", **fields,
        }).execute().data[0]
        action = "invited"
    audit(actor, action, "member", row["id"], {"name": row["display_name"], "role": req.role})
    return row, token


def invite_email(inviter: str, row: dict[str, Any], url: str) -> tuple[str, str, str]:
    """Subject, HTML and text. No kid names or plan details: just who, what role, and the link."""
    help_text = ROLE_HELP.get(row["role"], "")
    subject = f"{inviter} invited you to help with the family plan on CampFinder"
    text = (
        f"Hi {row['display_name']},\n\n{inviter} invited you to join their family on CampFinder. "
        f"You'll see {help_text}.\n\nAccept: {url}\n\nThe link works for {INVITE_DAYS} days. "
        "Sign in with this email address to accept. If you weren't expecting this, ignore it."
    )
    html = (
        f"<p>Hi {_esc(row['display_name'])},</p><p>{_esc(inviter)} invited you to join their family on "
        f"CampFinder. You'll see {_esc(help_text)}.</p>"
        f'<p><a href="{_esc(url)}" style="background:#1d4ed8;color:white;padding:12px 20px;border-radius:8px;'
        'text-decoration:none;">Accept the invite</a></p>'
        f"<p style=\"color:#666\">The link works for {INVITE_DAYS} days. Sign in with this email address to accept. "
        "If you weren't expecting this, ignore it.</p>"
    )
    return subject, html, text


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _mask(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}{'•' * max(len(local) - 1, 2)}@{domain}"


def _invite_row(token: str) -> dict[str, Any]:
    rows = get_supabase().table("family_members").select("*").eq("invite_token_hash", _hash(token)).execute().data
    if not rows or rows[0]["status"] != "invited":
        raise HTTPException(status_code=404, detail="This invite isn't valid any more. Ask for a new one.")
    return rows[0]


def preview_invite(token: str) -> InvitePreview:
    row = _invite_row(token)
    inviter = "A parent"
    if row.get("invited_by"):
        inv = get_supabase().table("family_members").select("display_name").eq("id", row["invited_by"]).execute().data
        if inv:
            inviter = inv[0]["display_name"]
    expires = _parse_ts(row["invite_expires_at"])
    return InvitePreview(
        invited_by=inviter, display_name=row["display_name"], role=row["role"], role_help=ROLE_HELP.get(row["role"], ""),
        email_hint=_mask(row["email"]), expires_at=expires, expired=expires is None or expires < _now(),
    )


def accept_invite(token: str, user_id: str) -> dict[str, Any]:
    """Join the family. The signed-in email must match the invited one, so a forwarded link is useless."""
    row = _invite_row(token)
    expires = _parse_ts(row["invite_expires_at"])
    if expires is None or expires < _now():
        raise HTTPException(status_code=410, detail="This invite has expired. Ask for a new one.")
    email = (user_email(user_id) or "").lower()
    if email != row["email"].lower():
        raise HTTPException(
            status_code=403,
            detail=f"This invite was sent to {_mask(row['email'])}. Sign in with that address to accept it.",
        )
    sb = get_supabase()
    family = sb.table("families").select("id, owner_user_id").eq("id", row["family_id"]).execute().data
    if family and str(family[0].get("owner_user_id")) == user_id:
        raise HTTPException(status_code=409, detail="You already own this family")
    if sb.table("family_members").select("id").eq("family_id", row["family_id"]).eq("user_id", user_id).execute().data:
        raise HTTPException(status_code=409, detail="You're already in this family")
    sb.table("family_members").update({
        "user_id": user_id, "status": "active", "accepted_at": _now().isoformat(),
        "invite_token_hash": None, "invite_expires_at": None,
    }).eq("id", row["id"]).execute()
    row.update(user_id=user_id, status="active")
    audit(Actor(row["family_id"], row["id"], row["display_name"], row["role"]), "joined", "member", row["id"],
          {"role": row["role"]})
    return row


def update_member(actor: Actor, member_id: str, req: MemberUpdate) -> dict[str, Any]:
    _require_owner(actor)
    row = get_member_row(actor.family_id, member_id)
    changes = req.model_dump(exclude_none=True)
    if row["role"] == "owner" and ({"role", "kit_access"} & changes.keys()):
        raise HTTPException(status_code=422, detail="The owner's role and kit access can't change")
    role = changes.get("role", row["role"])
    if changes.get("kit_access") and role != "co_parent":
        raise HTTPException(status_code=422, detail="Only co-parents can be given the info kit")
    if role != "co_parent":
        changes["kit_access"] = False  # moving someone off co-parent always closes the kit
    if not changes:
        return row
    get_supabase().table("family_members").update(changes).eq("id", row["id"]).execute()
    detail = {k: v for k, v in changes.items() if k != "display_name" or v != row["display_name"]}
    if "kit_access" in detail and detail["kit_access"] == bool(row.get("kit_access")):
        detail.pop("kit_access")
    if detail:
        audit(actor, "member_updated", "member", row["id"], {"name": row["display_name"], **detail})
    return {**row, **changes}


def update_my_prefs(actor: Actor, req: MyPrefs) -> dict[str, Any]:
    if actor.member_id is None:
        raise HTTPException(status_code=403, detail="Save your family to an account first")
    changes = req.model_dump(exclude_none=True)
    row = get_member_row(actor.family_id, actor.member_id)
    if changes:
        get_supabase().table("family_members").update(changes).eq("id", actor.member_id).execute()
    return {**row, **changes}


def remove_member(actor: Actor, member_id: str) -> None:
    _require_owner(actor)
    row = get_member_row(actor.family_id, member_id)
    if row["role"] == "owner":
        raise HTTPException(status_code=422, detail="The owner can't be removed")
    open_tasks = _open_task_count(actor.family_id, row["id"])
    get_supabase().table("family_members").delete().eq("id", row["id"]).execute()
    audit(actor, "member_removed", "member", row["id"], {"name": row["display_name"], "unassigned_tasks": open_tasks})


def leave_family(actor: Actor) -> None:
    if actor.role == "owner":
        raise HTTPException(status_code=422, detail="The owner can't leave; delete the family instead")
    open_tasks = _open_task_count(actor.family_id, actor.member_id)
    audit(actor, "left", "member", actor.member_id, {"unassigned_tasks": open_tasks})
    get_supabase().table("family_members").delete().eq("id", actor.member_id).execute()


def reset_member_calendar(actor: Actor) -> dict[str, Any]:
    if actor.member_id is None:
        raise HTTPException(status_code=403, detail="Save your family to an account first")
    token = secrets.token_hex(16)
    get_supabase().table("family_members").update({"calendar_token": token}).eq("id", actor.member_id).execute()
    return {**get_member_row(actor.family_id, actor.member_id), "calendar_token": token}


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def _open_task_count(family_id: str, member_id: Any) -> int:
    rows = (
        get_supabase().table("family_tasks").select("id").eq("family_id", family_id)
        .eq("assignee_id", str(member_id)).eq("status", "open").execute().data or []
    )
    return len(rows)


def task_rows(family_id: str, *, assignee_id: str | None = None, start: date | None = None,
              end: date | None = None, status: str | None = None) -> list[dict[str, Any]]:
    q = get_supabase().table("family_tasks").select("*").eq("family_id", family_id)
    if assignee_id:
        q = q.eq("assignee_id", assignee_id)
    if status:
        q = q.eq("status", status)
    if start:
        q = q.gte("due_date", start.isoformat())
    if end:
        q = q.lte("due_date", end.isoformat())
    rows = q.order("due_date").execute().data or []
    return sorted(rows, key=lambda r: (str(r["due_date"]), str(r.get("due_time") or "99")))


def to_task(row: dict[str, Any], names: dict[str, str]) -> Task:
    return Task(
        **{k: row.get(k) for k in Task.model_fields if k not in ("assignee_name", "completed_by_name", "checklist")},
        checklist=[ChecklistItem(**c) for c in row.get("checklist") or []],
        assignee_name=names.get(str(row.get("assignee_id"))) if row.get("assignee_id") else None,
        completed_by_name=names.get(str(row.get("completed_by"))) if row.get("completed_by") else None,
    )


def member_names(family_id: str) -> dict[str, str]:
    return {str(r["id"]): r["display_name"] for r in list_member_rows(family_id)}


def visible_tasks(actor: Actor, **filters: Any) -> list[Task]:
    """Co-parents and the owner see every task; a caregiver sees their own; a viewer none."""
    if actor.role == "viewer":
        return []
    if not actor.full_plan:
        filters["assignee_id"] = actor.member_id
    names = member_names(actor.family_id)
    return [to_task(r, names) for r in task_rows(actor.family_id, **filters)]


def _get_task(family_id: str, task_id: Any) -> dict[str, Any]:
    rows = get_supabase().table("family_tasks").select("*").eq("id", str(task_id)).eq("family_id", family_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Task not found")
    return rows[0]


def _require_full_plan(actor: Actor) -> None:
    if not actor.full_plan:
        raise HTTPException(status_code=403, detail="Only parents can change the plan")


def _check_assignee(family_id: str, member_id: Any) -> dict[str, Any] | None:
    if member_id is None:
        return None
    row = get_member_row(family_id, member_id)
    if row["role"] == "viewer":
        raise HTTPException(status_code=422, detail=f"{row['display_name']} can only view the calendar; make them a caregiver first")
    return row


def _task_row(family_id: str, t: TaskCreate, actor: Actor) -> dict[str, Any]:
    return {
        "family_id": family_id, "kind": t.kind, "title": t.title, "notes": t.notes, "child_name": t.child_name,
        "due_date": t.due_date.isoformat(), "due_time": t.due_time.isoformat() if t.due_time else None,
        "assignee_id": str(t.assignee_id) if t.assignee_id else None,
        "event_id": str(t.event_id) if t.event_id else None, "camp_id": str(t.camp_id) if t.camp_id else None,
        "checklist": [c.model_dump() for c in t.checklist], "status": "open", "created_by": actor.member_id,
    }


def create_tasks(actor: Actor, tasks: list[TaskCreate]) -> list[dict[str, Any]]:
    _require_full_plan(actor)
    for t in tasks:
        _check_assignee(actor.family_id, t.assignee_id)
    if not tasks:
        return []
    rows = get_supabase().table("family_tasks").insert([_task_row(actor.family_id, t, actor) for t in tasks]).execute().data
    audit(actor, "tasks_created", "task", rows[0]["id"] if len(rows) == 1 else None,
          {"count": len(rows), "titles": [r["title"] for r in rows[:5]]})
    return rows


def update_task(actor: Actor, task_id: str, req: TaskUpdate) -> dict[str, Any]:
    row = _get_task(actor.family_id, task_id)
    changes = req.model_dump(mode="json", exclude_unset=True)
    if not actor.full_plan:
        if actor.role == "viewer" or str(row.get("assignee_id")) != str(actor.member_id):
            raise HTTPException(status_code=403, detail="You can only update jobs assigned to you")
        if set(changes) - {"status", "checklist"}:
            raise HTTPException(status_code=403, detail="You can mark your jobs done or tick off the list; a parent changes the details")
    if "status" in changes:
        if changes["status"] == "open":
            changes.update(completed_at=None, completed_by=None)
        elif row["status"] == "open":
            changes.update(completed_at=_now().isoformat(), completed_by=actor.member_id)
    changes["updated_at"] = _now().isoformat()
    get_supabase().table("family_tasks").update(changes).eq("id", row["id"]).execute()
    action = {"done": "task_completed", "skipped": "task_skipped", "open": "task_reopened"}.get(
        changes.get("status") if "status" in changes and changes["status"] != row["status"] else "", "task_updated")
    fields = sorted(k for k in changes if k not in ("updated_at", "completed_at", "completed_by", "status"))
    if action != "task_updated" or fields:
        audit(actor, action, "task", row["id"], {"title": row["title"], "due_date": str(row["due_date"]),
                                                  **({"fields": fields} if fields else {})})
    return {**row, **changes}


def delete_tasks(actor: Actor, task_ids: Iterable[Any]) -> int:
    _require_full_plan(actor)
    ids = [str(t) for t in task_ids]
    rows = [r for r in task_rows(actor.family_id) if str(r["id"]) in ids]
    if not rows:
        return 0
    get_supabase().table("family_tasks").delete().eq("family_id", actor.family_id).in_("id", [r["id"] for r in rows]).execute()
    audit(actor, "tasks_deleted", "task", None, {"count": len(rows), "titles": [r["title"] for r in rows[:5]]})
    return len(rows)


def assign_tasks(actor: Actor, task_ids: Iterable[Any], member_id: Any) -> list[dict[str, Any]]:
    _require_full_plan(actor)
    member = _check_assignee(actor.family_id, member_id)
    ids = {str(t) for t in task_ids}
    rows = [r for r in task_rows(actor.family_id) if str(r["id"]) in ids]
    if len(rows) != len(ids):
        raise HTTPException(status_code=404, detail="Some of those tasks aren't in this family's plan")
    new_id = member["id"] if member else None
    get_supabase().table("family_tasks").update({"assignee_id": new_id, "updated_at": _now().isoformat()}) \
        .eq("family_id", actor.family_id).in_("id", [r["id"] for r in rows]).execute()
    audit(actor, "tasks_assigned" if member else "tasks_unassigned", "task", rows[0]["id"] if len(rows) == 1 else None, {
        "count": len(rows), "to": member["display_name"] if member else None,
        "titles": [r["title"] for r in rows[:5]],
    })
    return [{**r, "assignee_id": new_id} for r in rows]


def select_tasks(family_id: str, *, kinds: list[str] | None = None, weekdays: list[int] | None = None,
                 start: date | None = None, end: date | None = None, child_name: str | None = None,
                 assignee_id: str | None = None, unassigned_only: bool = False, status: str | None = "open",
                 camp_id: str | None = None) -> list[dict[str, Any]]:
    """Find tasks by description, e.g. pickups on Tuesdays in July."""
    out = []
    for r in task_rows(family_id, start=start, end=end, status=status, assignee_id=assignee_id):
        due = date.fromisoformat(str(r["due_date"]))
        if kinds and r["kind"] not in kinds:
            continue
        if weekdays is not None and due.weekday() not in weekdays:
            continue
        if child_name and (r.get("child_name") or "").lower() != child_name.lower():
            continue
        if unassigned_only and r.get("assignee_id"):
            continue
        if camp_id and str(r.get("camp_id")) != camp_id:
            continue
        out.append(r)
    return out


def _camp_label(event: dict[str, Any]) -> str:
    title = event["title"]
    child = event.get("child_name")
    if child and title.lower().startswith(child.lower()):
        title = title[len(child):].lstrip(" :-–·")
    return title or event["title"]


def generate_plan_tasks(actor: Actor, req: GenerateRequest) -> list[dict[str, Any]]:
    """Drop-off and pickup tasks for each camp day, and a packing list before each camp starts.
    Skips anything that already exists, so it's safe to run again after the plan changes."""
    _require_full_plan(actor)
    from campfinder.agent.tools import list_family_events

    events = list_family_events(actor.family_id)
    if req.event_ids:
        wanted = {str(e) for e in req.event_ids}
        events = [e for e in events if str(e["id"]) in wanted]
    else:
        events = [e for e in events if e.get("camp_id") or e.get("session_id")]
    if not events:
        raise HTTPException(status_code=422, detail="No camp sessions on the family calendar yet")

    existing = {(str(r.get("event_id")), r["kind"], str(r["due_date"])) for r in task_rows(actor.family_id)}
    new: list[TaskCreate] = []

    def add(t: TaskCreate) -> None:
        key = (str(t.event_id), t.kind, t.due_date.isoformat())
        if key not in existing:
            existing.add(key)
            new.append(t)

    for e in events:
        start, end = date.fromisoformat(str(e["start_date"])), date.fromisoformat(str(e["end_date"]))
        child, camp = e.get("child_name"), _camp_label(e)
        who = f"{child} " if child else ""
        common = dict(child_name=child, event_id=e["id"], camp_id=e.get("camp_id"))
        if req.include_packing:
            add(TaskCreate(
                kind="packing", title=f"Pack for {camp}" + (f" ({child})" if child else ""),
                due_date=start - timedelta(days=1), **common,
                checklist=[ChecklistItem(item=i) for i in (req.packing_items or DEFAULT_PACKING)],
            ))
        if req.include_rides:
            d = start
            while d <= end:
                if d.weekday() in req.weekdays:
                    add(TaskCreate(kind="dropoff", title=f"Drop off {who}at {camp}", due_date=d, due_time=req.dropoff_time, **common))
                    add(TaskCreate(kind="pickup", title=f"Pick up {who}from {camp}", due_date=d, due_time=req.pickup_time, **common))
                d += timedelta(days=1)
    return create_tasks(actor, new) if new else []


# ---------------------------------------------------------------------------
# Per-member calendar feed
# ---------------------------------------------------------------------------

def member_by_calendar_token(token: str) -> dict[str, Any] | None:
    rows = get_supabase().table("family_members").select("*").eq("calendar_token", token).execute().data
    return rows[0] if rows else None


def build_member_ics(member: dict[str, Any], events: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> str:
    """The family calendar plus this person's own jobs."""
    from campfinder.routers.agent import _ics_escape, _ics_fold

    stamp = _now().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//CampFinder//Household Calendar//EN", "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_ics_escape(member['display_name'])}: family plans (CampFinder)",
        "REFRESH-INTERVAL;VALUE=DURATION:PT3H",
    ]
    for e in events:
        start = date.fromisoformat(str(e["start_date"]))
        end = date.fromisoformat(str(e["end_date"])) + timedelta(days=1)
        lines += ["BEGIN:VEVENT", f"UID:{e['id']}@campfinder", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{start:%Y%m%d}", f"DTEND;VALUE=DATE:{end:%Y%m%d}",
                  f"SUMMARY:{_ics_escape(e['title'])}", "TRANSP:TRANSPARENT", "END:VEVENT"]
    for t in tasks:
        if t["status"] == "skipped":
            continue
        due = date.fromisoformat(str(t["due_date"]))
        mark = "✓ " if t["status"] == "done" else ""
        lines += ["BEGIN:VEVENT", f"UID:task-{t['id']}@campfinder", f"DTSTAMP:{stamp}"]
        if t.get("due_time"):
            at = datetime.combine(due, time.fromisoformat(str(t["due_time"])))
            lines += [f"DTSTART:{at:%Y%m%dT%H%M%S}", f"DTEND:{at + timedelta(minutes=30):%Y%m%dT%H%M%S}"]
        else:
            lines += [f"DTSTART;VALUE=DATE:{due:%Y%m%d}", f"DTEND;VALUE=DATE:{due + timedelta(days=1):%Y%m%d}"]
        lines.append(f"SUMMARY:{_ics_escape(mark + t['title'])}")
        if t.get("notes"):
            lines.append(f"DESCRIPTION:{_ics_escape(t['notes'])}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_ics_fold(line) for line in lines) + "\r\n"
