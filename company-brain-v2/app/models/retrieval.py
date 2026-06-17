"""Retrieval request and result models.

These sit between the memory store and the context layer: a
:class:`RetrievalQuery` goes in, a ranked list of :class:`RetrievalResult`
comes out.
"""

from __future__ import annotations

from pydantic import Field

from app.models.common import DomainModel
from app.models.memory import MemoryRecord


class RetrievalQuery(DomainModel):
    """A request for relevant memory.

    Attributes:
        tenant_id: Tenant partition to search within.
        text: Natural-language query.
        limit: Maximum number of results to return.
        filters: Optional metadata equality filters (e.g. ``{"source": "gmail"}``).
    """

    tenant_id: str = Field(default="default")
    text: str
    limit: int = Field(default=5, ge=1, le=100)
    filters: dict[str, object] = Field(default_factory=dict)


class RetrievalResult(DomainModel):
    """A single scored hit from the memory store.

    Attributes:
        record: The matched memory record.
        score: Relevance score in ``[0, 1]`` (backend-normalized).
        rationale: Optional explanation of why this matched (for debugging/UX).
    """

    record: MemoryRecord
    score: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None
