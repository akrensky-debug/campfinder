"""CampFinder API application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from campfinder.config import get_settings
from campfinder.database import check_connection, close_pool, init_pool
from campfinder.routers import (
    alerts,
    camps,
    compare,
    events,
    families,
    operators,
    planner,
    search,
    spot_requests,
)

logger = logging.getLogger("campfinder")

MAX_BODY_BYTES = 256 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_pool()
    try:
        yield
    finally:
        await close_pool()


def create_app(*, manage_pool: bool = True) -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="CampFinder API",
        description="Parents plan and book the summer. Camps get found without learning software.",
        version="2.0.0",
        lifespan=lifespan if manage_pool else None,
    )

    # Explicit origins only. Credentials plus a wildcard is how tokens leak.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )

    @app.middleware("http")
    async def guard_and_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith(f"{settings.api_prefix}/me") else "no-cache"
        return response

    prefix = settings.api_prefix
    app.include_router(search.router, prefix=prefix, tags=["Search"])
    app.include_router(camps.router, prefix=prefix, tags=["Camps"])
    app.include_router(compare.router, prefix=prefix, tags=["Compare"])
    app.include_router(planner.router, prefix=prefix, tags=["Planner"])
    app.include_router(alerts.router, prefix=prefix, tags=["Alerts"])
    app.include_router(families.router, prefix=prefix, tags=["Family"])
    app.include_router(spot_requests.router, prefix=prefix, tags=["Spot requests"])
    app.include_router(operators.router, prefix=prefix, tags=["Operators"])
    app.include_router(events.router, prefix=prefix, tags=["Analytics"])

    @app.get("/health", tags=["Health"], summary="Health check")
    async def health() -> dict[str, str]:
        db_ok = await check_connection()
        return {"status": "ok" if db_ok else "degraded", "database": "connected" if db_ok else "unreachable"}

    return app


app = create_app()
