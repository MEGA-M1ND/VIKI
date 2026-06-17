"""The :class:`ExtractedFact` — durable knowledge mined from a document.

Extraction turns one :class:`~app.models.documents.RawDocument` into zero or
more facts. A fact is the smallest unit of memory worth persisting.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.common import DomainModel, EntityType, FactType, SourceType
from app.utils.ids import new_id, utcnow


class EntityRef(DomainModel):
    """A named entity referenced by a fact.

    Attributes:
        name: Display name of the entity.
        type: Coarse entity category.
    """

    name: str
    type: EntityType = EntityType.OTHER


class ExtractedFact(DomainModel):
    """A durable fact, preference, or entity extracted from a document.

    Attributes:
        id: Internal unique id.
        tenant_id: Owning tenant.
        document_id: Source ``RawDocument.id`` this fact was derived from.
        source: Origin system, copied for convenient filtering.
        fact_type: Category of the fact.
        statement: Natural-language statement of the fact.
        entities: Entities the statement refers to.
        confidence: Extractor confidence in ``[0, 1]``.
        created_at: When the fact was extracted.
    """

    id: str = Field(default_factory=lambda: new_id("fact"))
    tenant_id: str = Field(default="default")
    document_id: str
    source: SourceType
    fact_type: FactType = FactType.FACT
    statement: str
    entities: list[EntityRef] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=utcnow)
