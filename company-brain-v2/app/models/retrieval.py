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


class ScoredFact(DomainModel):
    """A single scored fact from hybrid retrieval, with deduplication metadata.

    Used as an intermediate type in the retrieval pipeline (before clamping).
    Scores are unbounded (reranker produces logit-scale values > 1.0 or < 0.0).

    Attributes:
        record: The underlying memory record.
        score: Final relevance score after RRF + reranking + source weights.
        source_doc_id: Source document ID used for deduplication.
        rationale: Optional explanation.
    """

    record: MemoryRecord
    score: float = Field(ge=0.0)  # not capped at 1.0 — reranker scores are unbounded
    source_doc_id: str | None = None
    rationale: str | None = None

    def to_retrieval_result(self) -> RetrievalResult:
        """Convert to the standard RetrievalResult interface.

        Clamps the score to [0, 1] since RetrievalResult enforces le=1.0.

        Returns:
            A RetrievalResult with score clamped to [0, 1].
        """
        clamped = min(1.0, max(0.0, self.score))
        return RetrievalResult(record=self.record, score=clamped, rationale=self.rationale)
