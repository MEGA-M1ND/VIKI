"""Typed application settings, loaded from environment / `.env`.

All configuration flows through :func:`get_settings`. Nothing else in the
codebase should read ``os.environ`` directly — this keeps configuration
testable and gives us one place to evolve toward per-tenant overrides.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    """Deployment environment."""

    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class MemoryBackend(StrEnum):
    """Selectable memory store implementation.

    Only the interface exists in the MVP; backends are wired in later.
    """

    IN_MEMORY = "in_memory"
    PGVECTOR = "pgvector"
    GBRAIN = "gbrain"


class Settings(BaseSettings):
    """Application settings.

    Values are read from environment variables prefixed with ``CB_`` (see
    ``.env.example``). Field defaults make the app boot with zero config for
    local development.
    """

    model_config = SettingsConfigDict(
        env_prefix="CB_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---------------------------------------------------------
    app_env: AppEnv = Field(default=AppEnv.LOCAL, description="Deployment environment.")
    app_name: str = Field(default="company-brain", description="Service name for logs/metrics.")
    app_host: str = Field(default="0.0.0.0", description="Bind host for the API server.")
    app_port: int = Field(default=8000, description="Bind port for the API server.")
    log_level: str = Field(default="INFO", description="Root log level.")
    log_json: bool = Field(default=False, description="Emit JSON logs instead of console output.")

    # --- Multi-tenancy -------------------------------------------------------
    default_tenant_id: str = Field(
        default="default",
        description="Tenant used when a request does not carry one (single-tenant MVP).",
    )

    # --- LLM (placeholders; provider logic added later) ----------------------
    llm_provider: str = Field(default="openai", description="LLM provider identifier.")
    llm_api_key: str = Field(default="", description="LLM API key.")
    llm_model: str = Field(default="gpt-4o", description="Chat/completion model.")
    llm_embedding_model: str = Field(
        default="text-embedding-3-small", description="Embedding model."
    )

    # --- Memory store --------------------------------------------------------
    memory_backend: MemoryBackend = Field(
        default=MemoryBackend.IN_MEMORY, description="Which memory store to use."
    )
    memory_dsn: str = Field(default="", description="Connection string for the memory backend.")

    # --- Connectors (credentials only; logic added later) --------------------
    gmail_client_id: str = Field(default="", description="Gmail OAuth client ID.")
    gmail_client_secret: str = Field(default="", description="Gmail OAuth client secret.")
    notion_api_key: str = Field(default="", description="Notion integration token.")
    slack_bot_token: str = Field(default="", description="Slack bot token.")

    # --- Ingestion -----------------------------------------------------------
    ingestion_lookback_hours: int = Field(
        default=24, description="Default look-back window for incremental ingestion."
    )
    ingestion_batch_size: int = Field(
        default=50, description="Max documents processed per ingestion batch."
    )

    @property
    def is_production(self) -> bool:
        """Whether the service is running in a production-like environment."""
        return self.app_env in (AppEnv.STAGING, AppEnv.PROD)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    Cached so the ``.env`` file is parsed once per process. Call
    ``get_settings.cache_clear()`` in tests to force a reload.
    """
    return Settings()
