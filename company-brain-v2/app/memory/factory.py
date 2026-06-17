"""Memory store selection.

Resolves the configured :class:`~app.core.config.MemoryBackend` into a concrete
:class:`MemoryStore`. Only the in-memory backend is available in the MVP; the
others raise a clear error until implemented.
"""

from __future__ import annotations

from app.core.config import MemoryBackend, Settings
from app.core.exceptions import ConfigurationError
from app.memory.base import MemoryStore
from app.memory.in_memory import InMemoryStore


def build_memory_store(settings: Settings) -> MemoryStore:
    """Construct the memory store for the configured backend.

    Args:
        settings: Application settings.

    Returns:
        A ready-to-use :class:`MemoryStore`.

    Raises:
        ConfigurationError: The configured backend is not yet implemented.
    """
    backend = settings.memory_backend
    if backend is MemoryBackend.IN_MEMORY:
        return InMemoryStore()

    raise ConfigurationError(
        f"Memory backend '{backend}' is not implemented yet.",
        details={"backend": backend, "available": [MemoryBackend.IN_MEMORY]},
    )
