"""The :class:`ExtractedFact` — durable knowledge mined from a document.

Extraction turns one :class:`~app.models.documents.RawDocument` into zero or
more facts. A fact is the smallest unit of memory worth persisting.

The optional triple (``subject``, ``predicate``, ``object_``) encodes the fact
as a structured relation. ``natural_language`` holds the preferred human-readable
form, which may differ from ``statement``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.common import DomainModel, EntityType, FactType, SourceType, ValidityKind
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
        statement: Canonical statement of the fact (used for storage/retrieval).
        subject: Triple subject — who or what the fact is about.
        predicate: Triple predicate — the relation or action.
        object_: Triple object — the target or value (named with trailing underscore
            to avoid shadowing the built-in ``object``).
        natural_language: Preferred human-readable form of the statement.
        tags: Free-form labels for grouping/filtering.
        validity_kind: Temporal validity of this fact.
        entities: Named entities referenced by the statement.
        confidence: Extractor confidence in ``[0, 1]``.
        created_at: When the fact was extracted.
    """

    id: str = Field(default_factory=lambda: new_id("fact"))
    tenant_id: str = Field(default="default")
    document_id: str
    source: SourceType
    fact_type: FactType = FactType.FACT
    statement: str
    # Structured triple (all optional — populated when LLM can parse them)
    subject: str | None = None
    predicate: str | None = None
    object_: str | None = Field(default=None, alias="object")
    natural_language: str | None = None
    tags: list[str] = Field(default_factory=list)
    validity_kind: ValidityKind = ValidityKind.CURRENT
    entities: list[EntityRef] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=utcnow)

    model_config = {
        **DomainModel.model_config,
        "populate_by_name": True,  # allow both object_ and object as keys
    }
