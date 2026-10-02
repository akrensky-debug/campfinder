"""In-memory stand-ins for the Supabase client and the Anthropic streaming API."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any


class _Result:
    def __init__(self, data: list[dict[str, Any]]):
        self.data = data


class _Query:
    def __init__(self, db: "FakeSupabase", table: str):
        self.db, self.table = db, table
        self.filters: list[Any] = []
        self.op = "select"
        self.payload: Any = None
        self.on_conflict = ""
        self.order_key: str | None = None
        self.limit_n: int | None = None

    # filters
    def select(self, *_a: Any, **_k: Any) -> "_Query":
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self.filters.append(lambda r: str(r.get(col)) == str(val) if not isinstance(val, bool) else r.get(col) is val)
        return self

    def in_(self, col: str, vals: list[Any]) -> "_Query":
        s = {str(v) for v in vals}
        self.filters.append(lambda r: str(r.get(col)) in s)
        return self

    def order(self, col: str, **_k: Any) -> "_Query":
        self.order_key = col
        return self

    def limit(self, n: int) -> "_Query":
        self.limit_n = n
        return self

    # writes
    def insert(self, payload: Any, **_k: Any) -> "_Query":
        self.op, self.payload = "insert", payload
        return self

    def upsert(self, payload: Any, on_conflict: str = "", **_k: Any) -> "_Query":
        self.op, self.payload, self.on_conflict = "upsert", payload, on_conflict
        return self

    def update(self, payload: dict[str, Any]) -> "_Query":
        self.op, self.payload = "update", payload
        return self

    def delete(self) -> "_Query":
        self.op = "delete"
        return self

    def _match(self, r: dict[str, Any]) -> bool:
        return all(f(r) for f in self.filters)

    def execute(self) -> _Result:
        rows = self.db.tables.setdefault(self.table, [])
        if self.op == "select":
            out = [dict(r) for r in rows if self._match(r)]
            if self.order_key:
                out.sort(key=lambda r: str(r.get(self.order_key) or ""))
            return _Result(out[: self.limit_n] if self.limit_n else out)
        if self.op in ("insert", "upsert"):
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            out = []
            keys = [k for k in self.on_conflict.split(",") if k]
            for item in items:
                existing = next((r for r in rows if keys and all(str(r.get(k)) == str(item.get(k)) for k in keys)), None)
                if existing is not None and self.op == "upsert":
                    existing.update(item)
                    out.append(dict(existing))
                    continue
                row = {"id": str(uuid.uuid4()), **self.db.defaults.get(self.table, {}), **item}
                rows.append(row)
                out.append(dict(row))
            return _Result(out)
        if self.op == "update":
            out = []
            for r in rows:
                if self._match(r):
                    r.update(self.payload)
                    out.append(dict(r))
            return _Result(out)
        if self.op == "delete":
            gone = [r for r in rows if self._match(r)]
            self.db.tables[self.table] = [r for r in rows if not self._match(r)]
            return _Result(gone)
        raise AssertionError(self.op)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.defaults: dict[str, dict[str, Any]] = {
            "families": {"profile": {}, "calendar_token": "t" * 32, "owner_user_id": None},
            "agent_conversations": {"messages": []},
        }

    def table(self, name: str) -> _Query:
        return _Query(self, name)


# ---------------------------------------------------------------------------
# Anthropic: a scripted stream of responses
# ---------------------------------------------------------------------------

class _Block(SimpleNamespace):
    def model_dump(self, **_k: Any) -> dict[str, Any]:
        return {k: v for k, v in vars(self).items() if v is not None}


def text_block(text: str) -> _Block:
    return _Block(type="text", text=text)


def tool_use_block(name: str, inp: dict[str, Any]) -> _Block:
    return _Block(type="tool_use", id=f"toolu_{uuid.uuid4().hex[:8]}", name=name, input=inp)


class _Stream:
    def __init__(self, content: list[_Block], stop_reason: str):
        self.message = SimpleNamespace(content=content, stop_reason=stop_reason)

    async def __aenter__(self) -> "_Stream":
        return self

    async def __aexit__(self, *_a: Any) -> None:
        return None

    def __aiter__(self):
        async def gen():
            for b in self.message.content:
                if b.type == "text":
                    yield SimpleNamespace(type="text", text=b.text)
                else:
                    yield SimpleNamespace(type="content_block_start", content_block=b)
        return gen()

    async def get_final_message(self) -> Any:
        return self.message


class FakeAnthropic:
    """Returns the scripted responses in order and records every request."""

    def __init__(self, responses: list[tuple[list[_Block], str]]):
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs: Any) -> _Stream:
        self.requests.append(kwargs)
        content, stop = self.responses.pop(0)
        return _Stream(content, stop)
