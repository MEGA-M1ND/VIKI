"""Memory store selection.

Resolves the configured :class:`~app.core.config.MemoryBackend` into a concrete
:class:`MemoryStore`. Use :func:`build_memory_store_with_llm` for backends that
require an LLM provider (pgvector needs it for embedding generation).
"""

from __future__ import annotations

from app.core.config import MemoryBackend, Settings
from app.core.exceptions import ConfigurationError
from app.llm.base import LLMProvider
from app.memory.base import MemoryStore
from app.memory.in_memory import InMemoryStore


def build_memory_store(settings: Settings) -> MemoryStore:
    """Construct the memory store for the configured backend.

    For backends that require an LLM provider (e.g. pgvector), use
    :func:`build_memory_store_with_llm` instead.

    Args:
        settings: Application settings.

    Returns:
        A ready-to-use :class:`MemoryStore`.

    Raises:
        ConfigurationError: The configured backend requires an LLM or is not implemented.
    """
    backend = settings.memory_backend
    if backend is MemoryBackend.IN_MEMORY:
        return InMemoryStore()

    if backend is MemoryBackend.PGVECTOR:
        raise ConfigurationError(
            "Use build_memory_store_with_llm() for the pgvector backend.",
            details={"backend": backend},
        )

    raise ConfigurationError(
        f"Memory backend '{backend}' is not implemented yet.",
        details={"backend": backend, "available": [MemoryBackend.IN_MEMORY, MemoryBackend.PGVECTOR]},
    )


def build_memory_store_with_llm(settings: Settings, llm: LLMProvider | None) -> MemoryStore:
    """Construct the memory store, accepting an optional LLM provider.

    Supports all backends including pgvector (which requires the LLM for embeddings).

    Args:
        settings: Application settings.
        llm: LLM provider for embedding generation (required for pgvector backend).

    Returns:
        A ready-to-use :class:`MemoryStore`.

    Raises:
        ConfigurationError: Missing required config or unsupported backend.
    """
    backend = settings.memory_backend

    if backend is MemoryBackend.IN_MEMORY:
        return InMemoryStore()

    if backend is MemoryBackend.PGVECTOR:
        if not settings.memory_dsn:
            raise ConfigurationError(
                "CB_MEMORY_DSN must be set when CB_MEMORY_BACKEND=pgvector",
                details={"backend": backend},
            )
        if llm is None:
            raise ConfigurationError(
                "LLM provider required for pgvector backend (embeddings)",
                details={"backend": backend},
            )
        from app.memory.pgvector import PgVectorMemoryStore

        return PgVectorMemoryStore(dsn=settings.memory_dsn, llm=llm)

    raise ConfigurationError(
        f"Memory backend '{backend}' is not implemented yet.",
        details={"backend": backend, "available": [MemoryBackend.IN_MEMORY, MemoryBackend.PGVECTOR]},
    )
