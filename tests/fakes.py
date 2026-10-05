"""In-memory stand-ins for the Supabase client and the Anthropic streaming API."""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------


def _token() -> str:
    return uuid.uuid4().hex


DEFAULTS: dict[str, dict[str, Any]] = {
    "families": {"profile": {}, "owner_user_id": None, "calendar_token": _token},
    "family_events": {"notes": None, "child_name": None, "camp_id": None, "session_id": None},
    "family_members": {
        "user_id": None, "status": "invited", "kit_access": False, "invite_token_hash": None, "invite_expires_at": None,
        "invited_by": None, "calendar_token": _token, "reminder_pref": "day_before", "weekly_summary": True,
        "accepted_at": None,
    },
    "family_tasks": {
        "notes": None, "child_name": None, "due_time": None, "assignee_id": None, "status": "open", "event_id": None,
        "camp_id": None, "checklist": [], "created_by": None, "completed_by": None, "completed_at": None,
    },
    "family_audit_log": {"via": "app", "target_type": None, "target_id": None, "detail": {}},
    "agent_conversations": {"messages": []},
    "reminder_sends": {"task_count": 0},
    "family_registrations": {
        "session_id": None, "child_name": None, "status": "watching", "payment_status": "unpaid", "amount_paid": None,
        "paid_on": None, "balance_due": None, "payment_due_date": None, "forms_due_date": None, "opens_at": None,
        "confirmation_number": None, "notes": None, "remind": True, "event_ids": {}, "registered_at": None,
    },
    "registration_windows": {"session_id": None, "closes_at": None, "source_url": None, "verified": False, "notes": None},
    "registration_alerts": {"session_id": None, "confirm_sent_at": None, "confirmed_at": None, "unsubscribed_at": None},
    "booking_attempts": {"registration_id": None, "consent": None, "provider_ref": None, "error": None,
                         "status": "quoted", "environment": "sandbox"},
}
UNIQUE = {
    "registration_reminder_sends": [("registration_id", "kind", "due_on", "days_before")],
    "registration_alerts": [("camp_id", "session_id", "email"), ("token",)],
    "registration_alert_sends": [("alert_id", "kind", "opens_at")],
    "family_members": [("family_id", "email")],
    "reminder_sends": [("member_id", "kind", "period")],
}
SERIAL = {"family_audit_log", "reminder_sends", "kit_share_events", "activity_demand", "registration_reminder_sends",
          "registration_alert_sends"}


class Result:
    def __init__(self, data: list[dict[str, Any]]):
        self.data = data


class Query:
    def __init__(self, db: "FakeSupabase", table: str):
        self.db, self.table = db, table
        self.filters: list[tuple[str, str, Any]] = []
        self.op = "select"
        self.payload: Any = None
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self.on_conflict: list[str] = []

    # builders
    def select(self, *_a: Any, **_k: Any) -> "Query":
        self.op = "select"
        return self

    def insert(self, rows: Any, **_k: Any) -> "Query":
        self.op, self.payload = "insert", rows
        return self

    def upsert(self, rows: Any, on_conflict: str = "", **_k: Any) -> "Query":
        self.op, self.payload = "upsert", rows
        self.on_conflict = [c.strip() for c in on_conflict.split(",") if c.strip()]
        return self

    def update(self, values: dict[str, Any]) -> "Query":
        self.op, self.payload = "update", values
        return self

    def delete(self) -> "Query":
        self.op = "delete"
        return self

    def eq(self, col: str, v: Any) -> "Query":
        self.filters.append(("eq", col, v))
        return self

    def neq(self, col: str, v: Any) -> "Query":
        self.filters.append(("neq", col, v))
        return self

    def in_(self, col: str, vs: list[Any]) -> "Query":
        self.filters.append(("in", col, [str(v) for v in vs]))
        return self

    def gte(self, col: str, v: Any) -> "Query":
        self.filters.append(("gte", col, v))
        return self

    def lte(self, col: str, v: Any) -> "Query":
        self.filters.append(("lte", col, v))
        return self

    def order(self, col: str, desc: bool = False) -> "Query":
        self._order = (col, desc)
        return self

    def limit(self, n: int) -> "Query":
        self._limit = n
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        for op, col, v in self.filters:
            have = row.get(col)
            if op == "eq" and (have is None or str(have) != str(v)):
                return False
            if op == "neq" and str(have) == str(v):
                return False
            if op == "in" and str(have) not in v:
                return False
            if op == "gte" and (have is None or str(have) < str(v)):
                return False
            if op == "lte" and (have is None or str(have) > str(v)):
                return False
        return True

    def execute(self) -> Result:
        rows = self.db.tables.setdefault(self.table, [])
        if self.op in ("insert", "upsert"):
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            out = []
            for item in items:
                if self.op == "upsert" and self.on_conflict:
                    existing = next((r for r in rows if all(str(r.get(k)) == str(item.get(k)) for k in self.on_conflict)), None)
                    if existing is not None:
                        existing.update(copy.deepcopy(item))
                        out.append(copy.deepcopy(existing))
                        continue
                row = {}
                for k, v in DEFAULTS.get(self.table, {}).items():
                    row[k] = v() if callable(v) else copy.deepcopy(v)
                row.update(copy.deepcopy(item))
                if self.table in SERIAL:
                    row.setdefault("id", len(rows) + 1)
                else:
                    row.setdefault("id", str(uuid.uuid4()))
                row.setdefault("created_at", datetime.now(timezone.utc).isoformat())
                for cols in UNIQUE.get(self.table, []):
                    key = tuple(str(row.get(c)).lower() for c in cols)
                    if any(tuple(str(r.get(c)).lower() for c in cols) == key for r in rows):
                        raise Exception(f"duplicate key value violates unique constraint on {self.table}{cols}")
                rows.append(row)
                out.append(copy.deepcopy(row))
            return Result(out)
        matched = [r for r in rows if self._match(r)]
        if self.op == "update":
            for r in matched:
                r.update(copy.deepcopy(self.payload))
            return Result(copy.deepcopy(matched))
        if self.op == "delete":
            for r in matched:
                rows.remove(r)
                self.db.cascade(self.table, r)
            return Result(copy.deepcopy(matched))
        if self._order:
            col, desc = self._order
            matched = sorted(matched, key=lambda r: str(r.get(col) or ""), reverse=desc)
        if self._limit is not None:
            matched = matched[: self._limit]
        return Result(copy.deepcopy(matched))


@dataclass
class FakeAuth:
    tokens: dict[str, str] = field(default_factory=dict)   # access token -> user id
    emails: dict[str, str] = field(default_factory=dict)   # user id -> email

    def get_user(self, token: str) -> Any:
        uid = self.tokens.get(token)
        return SimpleNamespace(user=SimpleNamespace(id=uid, email=self.emails.get(uid))) if uid else None

    @property
    def admin(self) -> Any:
        return SimpleNamespace(get_user_by_id=lambda uid: SimpleNamespace(
            user=SimpleNamespace(id=uid, email=self.emails.get(str(uid)))))


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.auth = FakeAuth()

    def table(self, name: str) -> Query:
        return Query(self, name)

    def cascade(self, table: str, row: dict[str, Any]) -> None:
        if table == "families":
            for t, rows in self.tables.items():
                self.tables[t] = [r for r in rows if str(r.get("family_id")) != str(row["id"])]
        if table == "family_members":
            for t in self.tables.get("family_tasks", []):
                for col in ("assignee_id", "created_by", "completed_by"):
                    if str(t.get(col)) == str(row["id"]):
                        t[col] = None
            self.tables["reminder_sends"] = [r for r in self.tables.get("reminder_sends", [])
                                             if str(r["member_id"]) != str(row["id"])]
            self.tables["agent_conversations"] = [r for r in self.tables.get("agent_conversations", [])
                                                  if str(r.get("started_by")) != str(row["id"])]
        if table == "family_events":
            for t in self.tables.get("family_tasks", []):
                if str(t.get("event_id")) == str(row["id"]):
                    t["event_id"] = None

    def add_user(self, user_id: str, email: str, token: str) -> None:
        self.auth.tokens[token] = user_id
        self.auth.emails[user_id] = email


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


@dataclass
class Block:
    type: str
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None

    def model_dump(self, **_k: Any) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


class FakeStream:
    def __init__(self, response: Any):
        self.response = response

    async def __aenter__(self) -> "FakeStream":
        return self

    async def __aexit__(self, *a: Any) -> None:
        return None

    def __aiter__(self) -> Any:
        async def gen() -> Any:
            for b in self.response.content:
                if b.type == "text":
                    yield SimpleNamespace(type="text", text=b.text)
                elif b.type == "tool_use":
                    yield SimpleNamespace(type="content_block_start", content_block=b)
        return gen()

    async def get_final_message(self) -> Any:
        return self.response


def text_block(text: str) -> Block:
    return Block("text", text=text)


def tool_use_block(name: str, inp: dict[str, Any]) -> Block:
    return Block("tool_use", id=f"toolu_{uuid.uuid4().hex[:8]}", name=name, input=inp)


class FakeAnthropic:
    """Replays scripted turns. A turn is a list of Blocks (tool_use turns stop with
    'tool_use') or a (blocks, stop_reason) pair. Every request is recorded in `calls`
    (also available as `requests`)."""

    def __init__(self, turns: list[Any]):
        self.turns = list(turns)
        self.calls: list[dict[str, Any]] = []
        self.requests = self.calls
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs: Any) -> FakeStream:
        self.calls.append(copy.deepcopy(kwargs))
        turn = self.turns.pop(0)
        if isinstance(turn, tuple):
            content, stop = turn
        else:
            content = turn
            stop = "tool_use" if any(b.type == "tool_use" for b in content) else "end_turn"
        return FakeStream(SimpleNamespace(content=content, stop_reason=stop))
