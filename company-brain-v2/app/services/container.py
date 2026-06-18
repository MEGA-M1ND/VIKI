"""Composition root.

The :class:`ServiceContainer` wires concrete implementations together once, at
startup, and hands them to the API layer. This is intentionally a tiny,
explicit container rather than a DI framework — dependencies are few and the
wiring should be obvious.

Connectors and the extractor are optional — the app boots and serves the
context/memory APIs without them. They are only required for ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.connectors.base import BaseConnector
from app.context.base import ContextProvider
from app.context.provider import MemoryContextProvider
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.ingestion.base import BaseExtractor
from app.llm.base import LLMProvider
from app.memory.base import MemoryStore
from app.memory.factory import build_memory_store
from app.services.retrieval import RetrievalService

logger = get_logger(__name__)


@dataclass(slots=True)
class ServiceContainer:
    """Holds the application's wired collaborators."""

    settings: Settings
    memory_store: MemoryStore
    context_provider: ContextProvider
    retrieval_service: RetrievalService
    connectors: list[BaseConnector] = field(default_factory=list)
    extractor: BaseExtractor | None = None
    llm: LLMProvider | None = None

    @classmethod
    def build(cls, settings: Settings | None = None) -> ServiceContainer:
        """Construct the container from settings.

        Args:
            settings: Optional override (tests pass a custom instance);
                defaults to :func:`get_settings`.
        """
        settings = settings or get_settings()
        store = build_memory_store(settings)
        provider = MemoryContextProvider(store)
        retrieval = RetrievalService(
            store,
            default_limit=settings.retrieval_default_limit,
            max_limit=settings.retrieval_max_limit,
        )

        connectors: list[BaseConnector] = []
        if settings.gmail_client_id and settings.gmail_client_secret:
            from app.connectors.gmail import GmailConnector
            connectors.append(
                GmailConnector(
                    client_id=settings.gmail_client_id,
                    client_secret=settings.gmail_client_secret,
                )
            )

        notion_token = settings.notion_api_key or settings.notion_token
        notion_db_ids = [i.strip() for i in settings.notion_database_ids.split(",") if i.strip()]
        if notion_token and notion_db_ids:
            from app.connectors.notion import NotionConnector
            connectors.append(NotionConnector(token=notion_token, database_ids=notion_db_ids))

        from app.ingestion.passthrough import PassthroughExtractor
        extractor: BaseExtractor = PassthroughExtractor()

        llm: LLMProvider | None = None
        if settings.llm_api_key:
            from app.llm.openai import OpenAIProvider
            llm = OpenAIProvider(model=settings.llm_model, api_key=settings.llm_api_key)

        logger.info(
            "container.built",
            env=settings.app_env,
            memory_backend=settings.memory_backend,
            connectors=[type(c).__name__ for c in connectors],
            llm_configured=llm is not None,
        )
        return cls(
            settings=settings,
            memory_store=store,
            context_provider=provider,
            retrieval_service=retrieval,
            connectors=connectors,
            extractor=extractor,
            llm=llm,
        )
