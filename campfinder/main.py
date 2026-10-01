"""CampFinder FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from campfinder.config import get_settings
from campfinder.database import check_connection, close_pool, init_pool
from campfinder.mcp_server import mcp
from campfinder.routers import activity, agent, camps, compare, freshness, leads, planner, search, sessions, stripe

# Streamable HTTP MCP endpoint, mounted at /mcp. Stateless JSON responses so it
# works behind Railway's proxy and across restarts. host="0.0.0.0" disables the
# localhost-only DNS-rebinding guard, which would reject the public hostname.
mcp_app = mcp.streamable_http_app(
    streamable_http_path="/", stateless_http=True, json_response=True, host="0.0.0.0"
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage database pool lifecycle."""
    await init_pool()
    async with mcp.session_manager.run():
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
        allow_credentials=True,
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
    app.include_router(activity.router)

    app.mount("/mcp", mcp_app)

    @app.get("/health", tags=["Health"], summary="Health check")
    async def health() -> dict[str, str]:
        """Return API status and database connectivity."""
        db_ok = await check_connection()
        return {
            "status": "ok",
            "database": "connected" if db_ok else "unreachable",
        }

    return app


def _mcp_exact_path(asgi_app):
    """Serve /mcp as /mcp/ so MCP clients don't have to follow a redirect."""
    async def wrapped(scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/mcp":
            scope = {**scope, "path": "/mcp/", "raw_path": b"/mcp/"}
        await asgi_app(scope, receive, send)
    return wrapped


app = _mcp_exact_path(create_app())
