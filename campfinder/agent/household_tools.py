"""
Household tools for the in-app agent: tasks, assignments, invites and messages.

The agent may create, update and complete tasks itself once the parent has agreed, the
same as the calendar. Anything that reaches another person (assigning jobs to someone,
inviting them, messaging them) is only proposed: the tool returns a card, and nothing
happens until the parent presses Confirm in the app. These tools are site-only; they
are never served over MCP. The model sees names and roles, never email addresses.
"""

from __future__ import annotations

from datetime import date, time
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from campfinder.auth import FamilyAccess
from campfinder.agent.tools import ToolError, ToolOutput, ToolSpec
from campfinder.database import get_supabase
from campfinder.household import service
from campfinder.household.context import current_access
from campfinder.household.models import ROLE_LABELS, ChecklistItem, GenerateRequest, TaskCreate, TaskUpdate

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAYS: list[str] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _actor(family_id: str) -> service.Actor:
    access = current_access()
    if access is None or str(access.family["id"]) != family_id:
        rows = get_supabase().table("families").select("*").eq("id", family_id).execute().data
        if not rows or rows[0].get("owner_user_id") is not None:
            raise ToolError("I can't tell who is asking; please reload the page.")
        access = FamilyAccess(rows[0], "owner", None)  # guest family
    return service.actor_for(access, via="assistant")


def _compact_task(t: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    out = {
        "id": t["id"], "kind": t["kind"], "title": t["title"], "due": str(t["due_date"]),
        "time": str(t["due_time"])[:5] if t.get("due_time") else None, "status": t["status"],
        "child": t.get("child_name"),
        "owner": names.get(str(t.get("assignee_id"))) if t.get("assignee_id") else "unassigned",
    }
    return {k: v for k, v in out.items() if v is not None}


def _tasks_ui(actor: service.Actor, rows: list[dict[str, Any]], title: str | None = None) -> dict[str, Any]:
    names = service.member_names(actor.family_id)
    return {"type": "tasks", "title": title,
            "tasks": [service.to_task(r, names).model_dump(mode="json") for r in rows]}


def _members_brief(family_id: str) -> list[dict[str, Any]]:
    return [{"id": r["id"], "name": r["display_name"], "role": r["role"], "status": r["status"]}
            for r in service.list_member_rows(family_id)]


def household_context(family_id: str) -> str:
    """One line for the agent's context block: who is in the household and what's open."""
    members = _members_brief(family_id)
    open_rows = service.task_rows(family_id, status="open")
    names = service.member_names(family_id)
    counts: dict[str, int] = {}
    for t in open_rows:
        who = names.get(str(t.get("assignee_id")), "unassigned") if t.get("assignee_id") else "unassigned"
        counts[who] = counts.get(who, 0) + 1
    people = ", ".join(f"{m['name']} ({ROLE_LABELS[m['role']].lower()}{', invited' if m['status'] == 'invited' else ''})"
                       for m in members) or "just this parent (no one invited yet)"
    access = current_access()
    you = f"You are talking with {access.member['display_name']} ({access.role}). " if access and access.member else ""
    return f"{you}Household: {people}. Open tasks by person: {counts or 'none'}."


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

class ListHouseholdInput(BaseModel):
    pass


class ListTasksInput(BaseModel):
    start: date | None = None
    end: date | None = None
    member_id: UUID | None = Field(default=None, description="Only this person's tasks.")
    unassigned_only: bool = False
    kinds: list[Literal["dropoff", "pickup", "form", "payment", "packing", "deadline", "other"]] | None = None
    status: Literal["open", "done", "skipped", "any"] = "open"


class NewTask(BaseModel):
    kind: Literal["dropoff", "pickup", "form", "payment", "packing", "deadline", "other"] = "other"
    title: str = Field(max_length=160, description="Short and specific, e.g. 'Pay Riverside deposit' or 'Registration opens: Lakeside'.")
    due_date: date
    due_time: time | None = Field(default=None, description="Local time, if it matters.")
    child_name: str | None = None
    notes: str | None = Field(default=None, max_length=500, description="Logistics only. Never medical or insurance details.")
    event_id: UUID | None = Field(default=None, description="Calendar event this belongs to, if any.")
    camp_id: UUID | None = None
    checklist: list[str] | None = Field(default=None, description="Items, for packing lists.")


class CreateTasksInput(BaseModel):
    tasks: list[NewTask] = Field(min_length=1, max_length=40)


class GenerateTasksInput(BaseModel):
    event_ids: list[UUID] | None = Field(default=None, description="Calendar events to cover; every camp on the calendar if omitted.")
    dropoff_time: time | None = None
    pickup_time: time | None = None
    weekdays: list[Weekday] = Field(default=["mon", "tue", "wed", "thu", "fri"])
    include_rides: bool = True
    include_packing: bool = True
    packing_items: list[str] | None = Field(default=None, description="Camp-specific packing list; a sensible default otherwise.")


class TaskSelector(BaseModel):
    task_ids: list[UUID] | None = Field(default=None, description="Exact tasks. Or describe them with the filters below.")
    kinds: list[Literal["dropoff", "pickup", "form", "payment", "packing", "deadline", "other"]] | None = None
    weekdays: list[Weekday] | None = None
    start: date | None = None
    end: date | None = None
    child_name: str | None = None
    camp_id: UUID | None = None
    currently_assigned_to: UUID | None = None
    unassigned_only: bool = False


class ProposeAssignmentInput(TaskSelector):
    member_id: UUID | None = Field(description="Who should do them (from list_household). Null to unassign.")


class UpdateTasksInput(BaseModel):
    task_ids: list[UUID] = Field(min_length=1, max_length=100)
    status: Literal["open", "done", "skipped"] | None = None
    due_date: date | None = None
    due_time: time | None = None
    notes: str | None = Field(default=None, max_length=500)


class DeleteTasksInput(BaseModel):
    task_ids: list[UUID] = Field(min_length=1, max_length=200)


class ProposeInviteInput(BaseModel):
    display_name: str = Field(max_length=60, description="What the family calls them: 'Grandma', 'Dan', 'Ms. Rosa'.")
    role: Literal["co_parent", "caregiver", "viewer"]
    email: str | None = Field(default=None, description="Only if the parent typed it; otherwise they fill it in on the card.")


class DraftMessageInput(BaseModel):
    to: list[UUID] | Literal["everyone"] = Field(description="Member ids, or 'everyone'.")
    subject: str = Field(max_length=120)
    body: str = Field(max_length=3000, description="Plain text, warm and short. No medical, insurance or other kit details.")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

async def list_household_tool(inp: ListHouseholdInput, family_id: str) -> ToolOutput:
    actor = _actor(family_id)
    members = _members_brief(family_id)
    note = None if members else "No one else yet. The parent can save the family to an account and invite people."
    return ToolOutput(content={"members": members, "you": actor.name, "note": note},
                      ui={"type": "household", "members": members})


async def list_tasks_tool(inp: ListTasksInput, family_id: str) -> ToolOutput:
    actor = _actor(family_id)
    rows = service.task_rows(family_id, start=inp.start, end=inp.end,
                             assignee_id=str(inp.member_id) if inp.member_id else None,
                             status=None if inp.status == "any" else inp.status)
    if inp.unassigned_only:
        rows = [r for r in rows if not r.get("assignee_id")]
    if inp.kinds:
        rows = [r for r in rows if r["kind"] in inp.kinds]
    names = service.member_names(family_id)
    by_person: dict[str, int] = {}
    for r in rows:
        who = names.get(str(r.get("assignee_id")), "unassigned") if r.get("assignee_id") else "unassigned"
        by_person[who] = by_person.get(who, 0) + 1
    return ToolOutput(
        content={"count": len(rows), "by_person": by_person, "tasks": [_compact_task(r, names) for r in rows[:80]],
                 "truncated": len(rows) > 80},
        ui=_tasks_ui(actor, rows[:200]),
    )


async def create_tasks_tool(inp: CreateTasksInput, family_id: str) -> ToolOutput:
    actor = _actor(family_id)
    rows = service.create_tasks(actor, [
        TaskCreate(**t.model_dump(exclude={"checklist"}), checklist=[ChecklistItem(item=i) for i in t.checklist or []])
        for t in inp.tasks
    ])
    names = service.member_names(family_id)
    return ToolOutput(content={"created": len(rows), "tasks": [_compact_task(r, names) for r in rows]},
                      ui=_tasks_ui(actor, rows, "Added to the plan"))


async def generate_tasks_tool(inp: GenerateTasksInput, family_id: str) -> ToolOutput:
    actor = _actor(family_id)
    rows = service.generate_plan_tasks(actor, GenerateRequest(
        **inp.model_dump(exclude={"weekdays"}), weekdays=[WEEKDAYS.index(d) for d in inp.weekdays],
    ))
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    return ToolOutput(
        content={"created": len(rows), "by_kind": counts,
                 "note": None if rows else "Those tasks already exist; nothing new to add."},
        ui=_tasks_ui(actor, rows, "Added to the plan") if rows else None,
    )


def _select(family_id: str, s: TaskSelector) -> list[dict[str, Any]]:
    if s.task_ids:
        ids = {str(t) for t in s.task_ids}
        return [r for r in service.task_rows(family_id) if str(r["id"]) in ids]
    return service.select_tasks(
        family_id, kinds=s.kinds, weekdays=[WEEKDAYS.index(d) for d in s.weekdays] if s.weekdays else None,
        start=s.start, end=s.end, child_name=s.child_name, camp_id=str(s.camp_id) if s.camp_id else None,
        assignee_id=str(s.currently_assigned_to) if s.currently_assigned_to else None,
        unassigned_only=s.unassigned_only,
    )


async def propose_assignment_tool(inp: ProposeAssignmentInput, family_id: str) -> ToolOutput:
    actor = _actor(family_id)
    if not actor.full_plan:
        raise ToolError("Only parents can assign jobs.")
    member = None
    if inp.member_id:
        try:
            member = service.get_member_row(family_id, inp.member_id)
        except Exception as e:
            raise ToolError("No such person in this household; call list_household for ids.") from e
        if member["role"] == "viewer":
            raise ToolError(f"{member['display_name']} is a viewer (calendar only). Suggest making them a caregiver first.")
    rows = _select(family_id, inp)
    if not rows:
        raise ToolError("No open tasks match that. Check list_tasks, or generate the ride tasks first.")
    names = service.member_names(family_id)
    who = member["display_name"] if member else "nobody (unassign)"
    summary = f"Assign {len(rows)} task{'s' if len(rows) != 1 else ''} to {who}"
    return ToolOutput(
        content={"proposed": True, "summary": summary, "count": len(rows),
                 "tasks": [_compact_task(r, names) for r in rows[:30]],
                 "note": "Nothing is assigned yet. The parent confirms on the card; don't say it's done."},
        ui={"type": "assign_proposal", "summary": summary,
            "member": {"id": member["id"], "name": member["display_name"], "status": member["status"]} if member else None,
            "task_ids": [r["id"] for r in rows],
            "tasks": [service.to_task(r, names).model_dump(mode="json") for r in rows]},
    )


async def update_tasks_tool(inp: UpdateTasksInput, family_id: str) -> ToolOutput:
    actor = _actor(family_id)
    changes = TaskUpdate(**inp.model_dump(exclude={"task_ids"}, exclude_none=True))
    rows = [service.update_task(actor, str(t), changes) for t in inp.task_ids]
    return ToolOutput(content={"updated": len(rows)}, ui=_tasks_ui(actor, rows, "Updated"))


async def delete_tasks_tool(inp: DeleteTasksInput, family_id: str) -> ToolOutput:
    actor = _actor(family_id)
    return ToolOutput(content={"deleted": service.delete_tasks(actor, inp.task_ids)})


async def propose_invite_tool(inp: ProposeInviteInput, family_id: str) -> ToolOutput:
    actor = _actor(family_id)
    if actor.member_id is None:
        raise ToolError("The family isn't saved to an account yet. Ask the parent to sign in first (the Save to an account link).")
    if actor.role != "owner":
        raise ToolError("Only the family's owner can invite people.")
    return ToolOutput(
        content={"proposed": True, "note": "Nothing is sent yet. The parent checks the email address and presses Send invite on the card."},
        ui={"type": "invite_proposal", "display_name": inp.display_name, "role": inp.role, "email": inp.email or ""},
    )


async def draft_message_tool(inp: DraftMessageInput, family_id: str) -> ToolOutput:
    actor = _actor(family_id)
    rows = [r for r in service.list_member_rows(family_id) if str(r["id"]) != str(actor.member_id)]
    if inp.to != "everyone":
        wanted = {str(i) for i in inp.to}
        rows = [r for r in rows if str(r["id"]) in wanted]
    if not rows:
        raise ToolError("Nobody to send to. Invite people first, or check list_household.")
    show_email = actor.role == "owner"
    return ToolOutput(
        content={"drafted": True, "to": [r["display_name"] for r in rows],
                 "note": "Shown to the parent as a draft to copy or open in their email app. Nothing was sent."},
        ui={"type": "message_draft", "subject": inp.subject, "body": inp.body,
            "recipients": [{"name": r["display_name"], "email": r["email"] if show_email else None} for r in rows]},
    )


HOUSEHOLD_TOOLS: list[ToolSpec] = [
    ToolSpec("list_household",
             "Who shares this family's plan (owner, co-parents, caregivers like a grandparent or nanny, viewers), with "
             "member ids for assigning.", ListHouseholdInput, list_household_tool, family=True, status="Checking your household"),
    ToolSpec("list_tasks",
             "The family's tasks (drop-offs, pickups, forms, payments, packing lists, deadlines) with who owns each. "
             "Filter by dates, person, kind or status. Use it for 'what's still open' and 'who has what'.",
             ListTasksInput, list_tasks_tool, family=True, status="Checking the jobs"),
    ToolSpec("create_tasks",
             "Add tasks to the plan, unassigned: forms, payments, deadlines such as 'registration opens', custom "
             "packing lists. Add only what the parent agreed to. Assign with propose_assignment.",
             CreateTasksInput, create_tasks_tool, family=True, status="Adding to the plan"),
    ToolSpec("generate_plan_tasks",
             "From the camp sessions on the family calendar, create a drop-off and a pickup task for each camp day and a "
             "packing list due the day before each camp starts. Skips tasks that already exist. Ask for drop-off and "
             "pickup times first if you don't know them.",
             GenerateTasksInput, generate_tasks_tool, family=True, status="Building the job list"),
    ToolSpec("propose_assignment",
             "Propose giving tasks to a household member, chosen by id or described (e.g. kinds=['pickup'], "
             "weekdays=['tue'], start=July 1, end=July 31 for 'the Tuesday pickups in July'). Shows the parent a card "
             "with a Confirm button; nothing changes until they confirm. Also used to reassign or unassign.",
             ProposeAssignmentInput, propose_assignment_tool, family=True, status="Lining up the handoff"),
    ToolSpec("update_tasks",
             "Mark tasks done, skipped or open again, or move their date or time.",
             UpdateTasksInput, update_tasks_tool, family=True, status="Updating the jobs"),
    ToolSpec("delete_tasks", "Remove tasks from the plan by id.",
             DeleteTasksInput, delete_tasks_tool, family=True, status="Updating the jobs"),
    ToolSpec("propose_invite",
             "Propose inviting someone to the household: co_parent (the full plan), caregiver (only their jobs plus the "
             "calendar; right for grandparents, nannies, carpool parents) or viewer (calendar only). Shows a card where the "
             "parent checks the email and sends; nothing is sent by this tool. Owner only.",
             ProposeInviteInput, propose_invite_tool, family=True, status="Preparing an invite"),
    ToolSpec("draft_household_message",
             "Draft a message to household members (e.g. the week's pickup schedule for Grandma). The parent sees it as a "
             "draft to copy or open in their email; it is never sent by you.",
             DraftMessageInput, draft_message_tool, family=True, status="Drafting a message"),
]

HOUSEHOLD_PROMPT = """

Sharing the load:
- The plan is shared. The household can include a co-parent, grandparents, a nanny or a \
carpool parent. Use list_household to see who is in it, and list_tasks for who owns what.
- Turn decisions into jobs. Once camps are on the calendar, offer to set up the drop-offs, \
pickups and a packing list (generate_plan_tasks), and add forms, payments and deadlines like \
"registration opens" with create_tasks. Ask once for drop-off and pickup times.
- To hand jobs to someone ("give the Tuesday pickups in July to Grandma"), use \
propose_assignment. To bring someone in, use propose_invite. Both show the parent a card to \
confirm; never say a job was assigned or an invite sent until they confirm.
- Caregivers see only the jobs assigned to them and the calendar. The info kit stays with \
the owner. Keep task notes to logistics; never put medical or insurance details in them.\
"""


def _register() -> None:
    """Household tools are family tools: offered to the in-app agent only, never over MCP."""
    from campfinder.agent import tools

    for spec in HOUSEHOLD_TOOLS:
        if spec.name not in tools.ALL_TOOLS:
            tools.FAMILY_TOOLS.append(spec)
            tools.ALL_TOOLS[spec.name] = spec


_register()
