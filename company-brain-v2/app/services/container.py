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
        logger.info(
            "container.built",
            env=settings.app_env,
            memory_backend=settings.memory_backend,
        )
        return cls(
            settings=settings,
            memory_store=store,
            context_provider=provider,
            retrieval_service=retrieval,
        )
