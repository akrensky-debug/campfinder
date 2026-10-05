"""CampFinder FastAPI application entry point."""

from __future__ import annotations

import json
import time
from collections import deque
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from campfinder.config import get_settings
from campfinder.database import check_connection, close_pool, init_pool
from campfinder.mcp_server import VERSION as MCP_VERSION, servers as mcp_servers
from campfinder.routers import activities, activity, agent, camps, household, kit, owners, compare, freshness, leads, planner, search, sessions, stripe
from campfinder.routers import alerts, booking

# Streamable HTTP MCP endpoints, one per host (see mcp_server.py). Stateless JSON
# responses so they work behind Railway's proxy and across restarts. host="0.0.0.0"
# disables the localhost-only DNS-rebinding guard, which would reject the public hostname.
mcp_apps = {
    path: server.streamable_http_app(
        streamable_http_path="/", stateless_http=True, json_response=True, host="0.0.0.0"
    )
    for path, server in mcp_servers.items()
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage database pool and MCP session manager lifecycles."""
    await init_pool()
    async with AsyncExitStack() as stack:
        for server in mcp_servers.values():
            await stack.enter_async_context(server.session_manager.run())
        yield
    await close_pool()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="CampFinder API",
        description=(
            "Agent-first camp discovery platform. "
            "Verified camp data served through a structured API."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    prefix = settings.api_prefix

    app.include_router(search.router, prefix=prefix, tags=["Search"])
    app.include_router(camps.router, prefix=prefix, tags=["Camps"])
    app.include_router(compare.router, prefix=prefix, tags=["Compare"])
    app.include_router(sessions.router, prefix=prefix, tags=["Sessions"])
    app.include_router(planner.router, prefix=prefix, tags=["Planner"])
    app.include_router(freshness.router, prefix=prefix, tags=["Freshness"])
    app.include_router(leads.router, prefix=prefix, tags=["Leads"])
    app.include_router(stripe.router, prefix=prefix, tags=["Stripe"])
    app.include_router(agent.router, prefix=prefix, tags=["Agent"])
    app.include_router(kit.router, prefix=prefix, tags=["Info kit"])
    app.include_router(activities.router, prefix=prefix, tags=["Activities"])
    app.include_router(household.router, prefix=prefix, tags=["Household"])
    app.include_router(owners.router, prefix=prefix, tags=["Camp owners"])
    app.include_router(booking.router, prefix=prefix, tags=["Registration"])
    app.include_router(alerts.router, prefix=prefix, tags=["Registration alerts"])
    app.include_router(activity.router)

    for path, mcp_app in mcp_apps.items():
        app.mount(path, mcp_app)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

    @app.get("/.well-known/openai-apps-challenge", include_in_schema=False)
    async def openai_apps_challenge() -> PlainTextResponse:
        """Domain verification for the ChatGPT app: the token from the OpenAI dashboard."""
        if not settings.openai_apps_challenge:
            raise HTTPException(status_code=404)
        return PlainTextResponse(settings.openai_apps_challenge)

    @app.get("/health", tags=["Health"], summary="Health check")
    async def health() -> dict[str, object]:
        """Return API status, database connectivity and the MCP endpoints."""
        db_ok = await check_connection()
        return {
            "status": "ok",
            "database": "connected" if db_ok else "unreachable",
            "mcp": {"version": MCP_VERSION, "endpoints": list(mcp_servers)},
        }

    return app


def _rate_limited(asgi_app, per_minute: int):
    """Per-IP sliding window on the MCP endpoints, answered as JSON-RPC errors.

    Assistants call from shared IP ranges (Claude from 160.79.104.0/21), so the limit is a
    backstop against abuse and runaway loops, set well above normal traffic."""
    windows: dict[str, deque[float]] = {}

    async def wrapped(scope, receive, send):
        if scope["type"] != "http" or not any(scope["path"].startswith(p) for p in mcp_servers):
            return await asgi_app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        forwarded = headers.get(b"x-forwarded-for", b"").decode().split(",")[0].strip()
        ip = forwarded or (scope.get("client") or ("unknown",))[0]
        now = time.monotonic()
        window = windows.setdefault(ip, deque())
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= per_minute:
            body = json.dumps({
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32000, "message": "Too many requests to CampFinder. Try again in a minute."},
            }).encode()
            await send({"type": "http.response.start", "status": 429, "headers": [
                (b"content-type", b"application/json"), (b"retry-after", b"60"),
            ]})
            await send({"type": "http.response.body", "body": body})
            return
        window.append(now)
        if len(windows) > 10_000:  # drop idle clients so memory stays bounded
            for key in [k for k, w in windows.items() if not w or now - w[-1] > 60]:
                del windows[key]
        await asgi_app(scope, receive, send)
    return wrapped


def _mcp_exact_path(asgi_app):
    """Serve /mcp as /mcp/ (and each host's path likewise) so clients don't follow a redirect."""
    async def wrapped(scope, receive, send):
        if scope["type"] == "http" and scope["path"] in mcp_servers:
            path = scope["path"] + "/"
            scope = {**scope, "path": path, "raw_path": path.encode()}
        await asgi_app(scope, receive, send)
    return wrapped


app = _mcp_exact_path(_rate_limited(create_app(), get_settings().mcp_rate_per_minute))
