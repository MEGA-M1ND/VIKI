"""Composition root.

The :class:`ServiceContainer` wires concrete implementations together once, at
startup, and hands them to the API layer. This is intentionally a tiny,
explicit container rather than a DI framework — dependencies are few and the
wiring should be obvious.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.context.base import ContextProvider
from app.context.provider import MemoryContextProvider
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.memory.base import MemoryStore
from app.memory.factory import build_memory_store

logger = get_logger(__name__)


@dataclass(slots=True)
class ServiceContainer:
    """Holds the application's wired collaborators."""

    settings: Settings
    memory_store: MemoryStore
    context_provider: ContextProvider

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
        logger.info(
            "container.built",
            env=settings.app_env,
            memory_backend=settings.memory_backend,
        )
        return cls(settings=settings, memory_store=store, context_provider=provider)
