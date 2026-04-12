"""CampFinder FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from campfinder.config import get_settings
from campfinder.database import check_connection, close_pool, init_pool
from campfinder.routers import camps, compare, freshness, leads, planner, search, sessions, stripe


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage database pool lifecycle."""
    await init_pool()
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

    @app.get("/health", tags=["Health"], summary="Health check")
    async def health() -> dict[str, str]:
        """Return API status and database connectivity."""
        db_ok = await check_connection()
        return {
            "status": "ok",
            "database": "connected" if db_ok else "unreachable",
        }

    return app


app = create_app()
