"""Application configuration loaded from environment variables."""

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings sourced from environment variables."""

    supabase_url: str = os.environ.get("SUPABASE_URL", "")
    supabase_anon_key: str = os.environ.get("SUPABASE_ANON_KEY", "")
    supabase_service_key: str = os.environ.get("SUPABASE_SERVICE_KEY", "")
    database_url: str = os.environ.get("DATABASE_URL", "")

    # Convert postgres:// to postgresql:// for asyncpg compatibility
    @property
    def asyncpg_dsn(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    resend_api_key: str = os.environ.get("RESEND_API_KEY", "")
    stripe_secret_key: str = os.environ.get("STRIPE_SECRET_KEY", "")
    stripe_webhook_secret: str = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    stripe_pro_price_id: str = os.environ.get("STRIPE_PRO_PRICE_ID", "")
    frontend_url: str = os.environ.get("FRONTEND_URL", "http://localhost:3000")

    cors_origins: list[str] = ["*"]  # Tighten in production
    api_prefix: str = "/api/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
