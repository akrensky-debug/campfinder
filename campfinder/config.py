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
    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    # Model the listing tool (python -m campfinder.ingest) uses to read camp websites.
    ingest_model: str = os.environ.get("INGEST_MODEL", "claude-opus-5-5")
    # 32 random bytes, base64: python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
    kit_encryption_key: str = os.environ.get("KIT_ENCRYPTION_KEY", "")
    frontend_url: str = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    # Public origin of this API, used for server icons in MCP metadata.
    public_api_url: str = os.environ.get("PUBLIC_API_URL", "http://localhost:8000")
    # ChatGPT app review: the token from the OpenAI dashboard, served at
    # /.well-known/openai-apps-challenge, and the widget's origin (unique per app).
    openai_apps_challenge: str = os.environ.get("OPENAI_APPS_CHALLENGE", "")
    chatgpt_widget_domain: str = os.environ.get("CHATGPT_WIDGET_DOMAIN", "")
    # Requests per minute per client IP on the MCP endpoints. ChatGPT and Claude call
    # from shared IP ranges, so this guards against abuse, not per-parent use.
    mcp_rate_per_minute: int = int(os.environ.get("MCP_RATE_PER_MINUTE", "600"))

    cors_origins: list[str] = ["*"]  # Tighten in production
    api_prefix: str = "/api/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
