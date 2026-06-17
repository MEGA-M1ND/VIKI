"""The :class:`RawDocument` — unit of ingestion.

A ``RawDocument`` is the normalized output of a connector: source-agnostic
enough for the extraction stage to consume, while preserving source-specific
metadata for provenance and debugging.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.common import DomainModel, SourceType
from app.utils.ids import new_id, utcnow


class RawDocument(DomainModel):
    """A single piece of raw content fetched from a source system.

    Attributes:
        id: Internal unique id.
        tenant_id: Owning tenant (single-tenant MVP uses the default).
        source: Origin system (Gmail, Notion, Slack, ...).
        source_id: Native identifier in the source system (e.g. Gmail message id).
        content: Plain-text content, ready for extraction.
        title: Optional subject/title.
        author: Optional author/sender identifier.
        uri: Optional canonical link back to the source object.
        metadata: Source-specific fields preserved verbatim.
        fetched_at: When this document was fetched.
        created_at: When this record was constructed.
    """

    id: str = Field(default_factory=lambda: new_id("doc"))
    tenant_id: str = Field(default="default")
    source: SourceType
    source_id: str
    content: str
    title: str | None = None
    author: str | None = None
    uri: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=utcnow)
    created_at: datetime = Field(default_factory=utcnow)
