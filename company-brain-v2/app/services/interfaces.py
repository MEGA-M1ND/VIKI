"""Service-layer Protocol interfaces.

These Protocols define the structural contracts for the major service roles.
Any class that implements the required methods satisfies the Protocol — no
inheritance required. This keeps dependencies shallow and makes testing easy
(swap in any matching fake).

Roles:
    MemoryWriter    — persist a MemoryRecord
    MemoryRetriever — query MemoryRecords by relevance
    MemoryDeduper   — find existing records similar to a new fact
    FactExtractor   — turn a RawDocument into ExtractedFacts
    ContextAssembler — render RetrievalResults as an injectable context block
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.documents import RawDocument
from app.models.facts import ExtractedFact
from app.models.memory import MemoryRecord
from app.models.retrieval import RetrievalQuery, RetrievalResult


@runtime_checkable
class MemoryWriter(Protocol):
    """Write a single memory record to the backing store."""

    async def write(self, record: MemoryRecord) -> MemoryRecord:
        """Persist (insert or update) *record* and return the stored copy."""
        ...


@runtime_checkable
class MemoryRetriever(Protocol):
    """Query memory records by relevance to a text query."""

    async def query(self, query: RetrievalQuery) -> list[RetrievalResult]:
        """Return relevant records ranked by score (best first)."""
        ...


@runtime_checkable
class MemoryDeduper(Protocol):
    """Detect whether a new fact is already captured in memory."""

    async def find_duplicate(
        self,
        fact: ExtractedFact,
        *,
        tenant_id: str,
    ) -> MemoryRecord | None:
        """Return an existing record that semantically matches *fact*, or ``None``."""
        ...


@runtime_checkable
class FactExtractor(Protocol):
    """Extract durable facts from a raw document."""

    async def extract(self, document: RawDocument) -> list[ExtractedFact]:
        """Return zero or more facts extracted from *document*."""
        ...


@runtime_checkable
class ContextAssembler(Protocol):
    """Render ranked retrieval results as an injectable context string."""

    def assemble(
        self,
        results: list[RetrievalResult],
        *,
        max_chars: int = 4000,
    ) -> str:
        """Format *results* into a context block within the *max_chars* budget."""
        ...
