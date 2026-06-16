from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # LLM
    openai_api_key: str = Field(..., description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o", description="LLM model name")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", description="Embedding model name"
    )

    # GBrain MCP Server
    gbrain_mcp_url: str = Field(
        default="http://localhost:3721/mcp", description="GBrain MCP HTTP endpoint"
    )
    gbrain_token: str = Field(default="", description="GBrain bearer token")

    # Gmail OAuth
    gmail_client_id: str = Field(default="", description="Gmail OAuth client ID")
    gmail_client_secret: str = Field(default="", description="Gmail OAuth client secret")
    gmail_redirect_uri: str = Field(
        default="http://localhost:8000/auth/gmail/callback",
        description="Gmail OAuth redirect URI",
    )

    # Notion
    notion_api_key: str = Field(default="", description="Notion integration API key")
    notion_database_ids: str = Field(
        default="", description="Comma-separated Notion database IDs"
    )

    # Ingestion
    ingestion_lookback_hours: int = Field(
        default=24, description="Hours to look back when fetching documents"
    )
    ingestion_batch_size: int = Field(
        default=50, description="Max documents per ingestion batch"
    )
    classifier_confidence_threshold: float = Field(
        default=0.7, description="Minimum confidence to mark document worth remembering"
    )

    # App
    app_host: str = Field(default="0.0.0.0", description="FastAPI host")
    app_port: int = Field(default=8000, description="FastAPI port")
    log_level: str = Field(default="INFO", description="Logging level")

    @property
    def notion_database_id_list(self) -> list[str]:
        if not self.notion_database_ids:
            return []
        return [db_id.strip() for db_id in self.notion_database_ids.split(",") if db_id.strip()]


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
