"""Memory store interface.

The memory store is the persistence + retrieval boundary. Keeping it abstract
lets us start with an in-memory implementation and later swap in pgvector,
GBrain, or another backend without touching the rest of the system.

All operations are tenant-scoped to make multi-tenancy a first-class concern.
Persistence internals are intentionally omitted in the MVP scaffold.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.memory import MemoryRecord
from app.models.retrieval import RetrievalQuery, RetrievalResult


class MemoryStore(ABC):
    """Abstract base for memory backends."""

    @abstractmethod
    async def write(self, record: MemoryRecord) -> MemoryRecord:
        """Persist (insert or update) a memory record.

        Args:
            record: The record to store.

        Returns:
            The stored record (with any backend-populated fields).

        Raises:
            MemoryWriteError: The write failed.
        """
        raise NotImplementedError

    @abstractmethod
    async def get(self, *, tenant_id: str, record_id: str) -> MemoryRecord | None:
        """Fetch a record by id, or ``None`` if it does not exist."""
        raise NotImplementedError

    @abstractmethod
    async def query(self, query: RetrievalQuery) -> list[RetrievalResult]:
        """Return relevant records ranked by score.

        Args:
            query: The retrieval request (tenant-scoped).

        Returns:
            Ranked results, best first.

        Raises:
            MemoryQueryError: The query failed.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(self, *, tenant_id: str, record_id: str) -> bool:
        """Delete a record. Returns ``True`` if a record was removed."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Return ``True`` if the backend is reachable and ready."""
        raise NotImplementedError
