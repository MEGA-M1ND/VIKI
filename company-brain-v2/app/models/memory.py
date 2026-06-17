"""The :class:`MemoryRecord` — what actually lives in the memory store.

A memory record is the persisted, retrievable representation of one or more
extracted facts. It is intentionally storage-agnostic: an embedding is optional
because some backends compute and own it internally.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.common import DomainModel, FactType, SourceType
from app.utils.ids import new_id, utcnow


class MemoryRecord(DomainModel):
    """A retrievable unit of memory.

    Attributes:
        id: Internal unique id (stable across updates).
        tenant_id: Owning tenant — the partition key for all retrieval.
        content: Canonical text used for retrieval/synthesis.
        record_type: Category mirroring the originating fact type.
        source: Origin system, if traceable to a single source.
        source_refs: Ids of the documents/facts that produced this record.
        embedding: Optional precomputed embedding vector.
        metadata: Arbitrary structured attributes (tags, entities, scores).
        created_at: First persisted.
        updated_at: Last mutated.
    """

    id: str = Field(default_factory=lambda: new_id("mem"))
    tenant_id: str = Field(default="default")
    content: str
    record_type: FactType = FactType.FACT
    source: SourceType | None = None
    source_refs: list[str] = Field(default_factory=list)
    embedding: list[float] | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def touch(self) -> None:
        """Update ``updated_at`` to now (call on mutation)."""
        self.updated_at = utcnow()
