"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _env_list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.environ.get("DATABASE_URL", ""))

    # Browser origins allowed to call the API. Never "*" once credentials are involved.
    cors_origins: list[str] = field(
        default_factory=lambda: _env_list("CORS_ORIGINS", "http://localhost:3000")
    )

    # Public site URL, used in emails and detail_url fields.
    site_url: str = field(default_factory=lambda: os.environ.get("SITE_URL", "http://localhost:3000"))

    # Parent auth: JWTs issued by the auth provider (Supabase Auth). Current
    # Supabase projects sign with an asymmetric key (ES256 or RS256) published
    # at AUTH_JWKS_URL, e.g. https://<ref>.supabase.co/auth/v1/.well-known/jwks.json.
    # Older projects use a shared HS256 secret, AUTH_JWT_SECRET. Either or both
    # may be set; with neither, auth is off and every family endpoint returns 401.
    auth_jwks_url: str = field(default_factory=lambda: os.environ.get("AUTH_JWKS_URL", ""))
    auth_jwt_secret: str = field(default_factory=lambda: os.environ.get("AUTH_JWT_SECRET", ""))
    auth_jwt_audience: str = field(default_factory=lambda: os.environ.get("AUTH_JWT_AUDIENCE", "authenticated"))
    # Expected "iss" claim, e.g. https://<ref>.supabase.co/auth/v1. Checked when set.
    auth_jwt_issuer: str = field(default_factory=lambda: os.environ.get("AUTH_JWT_ISSUER", ""))

    # Outbound email (Resend). Empty means emails are logged, not sent.
    resend_api_key: str = field(default_factory=lambda: os.environ.get("RESEND_API_KEY", ""))
    email_from: str = field(
        default_factory=lambda: os.environ.get("EMAIL_FROM", "CampFinder <hello@localhost>")
    )
    team_email: str = field(default_factory=lambda: os.environ.get("TEAM_EMAIL", ""))

    # Listing ingest (Claude). The SDK reads ANTHROPIC_API_KEY itself.
    ingest_model: str = field(default_factory=lambda: os.environ.get("INGEST_MODEL", "claude-opus-5-5"))

    # Requests per minute per client IP on write endpoints.
    rate_limit_per_minute: int = field(
        default_factory=lambda: int(os.environ.get("RATE_LIMIT_PER_MINUTE", "30"))
    )

    privacy_policy_version: str = field(
        default_factory=lambda: os.environ.get("PRIVACY_POLICY_VERSION", "2026-10")
    )

    api_prefix: str = "/api/v1"

    @property
    def asyncpg_dsn(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
