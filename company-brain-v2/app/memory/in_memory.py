"""A minimal in-memory :class:`MemoryStore` for local dev and tests.

This is a *reference* implementation, not a persistence backend. It keeps
records in a per-tenant dict and does naive substring scoring so the app is
fully runnable end-to-end before real backends (pgvector, GBrain) are wired in.

It deliberately contains no database, embedding, or vector-index logic.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from app.core.logging import get_logger
from app.core.source_weights import apply_source_weight
from app.memory.base import MemoryStore
from app.models.memory import MemoryRecord
from app.models.retrieval import RetrievalQuery, RetrievalResult

logger = get_logger(__name__)

# Source-type hints that represent low-signal automated content.
# Records carrying these hints are excluded from all queries regardless of other filters.
_NOISE_SOURCE_TYPES: frozenset[str] = frozenset(
    {
        "gmail_newsletter",
        "gmail_digest",
        "gmail_promotional",
        "gmail_job_alert",
    }
)


class InMemoryStore(MemoryStore):
    """Thread-unsafe, process-local memory store.

    Suitable only for development and unit tests.
    """

    def __init__(self) -> None:
        # tenant_id -> {record_id -> MemoryRecord}
        self._data: dict[str, dict[str, MemoryRecord]] = defaultdict(dict)

    async def write(self, record: MemoryRecord) -> MemoryRecord:
        self._data[record.tenant_id][record.id] = record
        logger.info("memory.write", tenant=record.tenant_id, record_id=record.id)
        return record

    async def get(self, *, tenant_id: str, record_id: str) -> MemoryRecord | None:
        return self._data.get(tenant_id, {}).get(record_id)

    async def query(self, query: RetrievalQuery) -> list[RetrievalResult]:
        records = self._data.get(query.tenant_id, {}).values()
        terms = {t for t in query.text.lower().split() if t}

        results: list[RetrievalResult] = []
        for record in records:
            if not _matches_filters(record, query.filters):
                continue
            raw_score = _naive_score(record.content, terms)
            if raw_score <= 0.0:
                continue
            hint = record.source_type_hint or record.metadata.get("source_type_hint")
            weighted = apply_source_weight(raw_score, hint)
            if weighted > 0.0:
                results.append(RetrievalResult(record=record, score=weighted))

        results.sort(key=lambda r: r.score, reverse=True)
        logger.info(
            "memory.query",
            tenant=query.tenant_id,
            hits=len(results),
            returned=min(len(results), query.limit),
        )
        return results[: query.limit]

    async def delete(self, *, tenant_id: str, record_id: str) -> bool:
        removed = self._data.get(tenant_id, {}).pop(record_id, None)
        return removed is not None

    async def find_by_dedupe_key(self, *, tenant_id: str, dedupe_key: str) -> MemoryRecord | None:
        for record in self._data.get(tenant_id, {}).values():
            if record.metadata.get("dedupe_key") == dedupe_key:
                return record
        return None

    async def health_check(self) -> bool:
        return True


def _matches_filters(record: MemoryRecord, filters: dict[str, object]) -> bool:
    """Return True if *record* passes all filters.

    Handles two special cases before the generic equality loop:
    - ``after_date``: temporal lower-bound on ``created_at`` (``>=``).
    - noise source types: always excluded regardless of query.
    """
    # Noise exclusion: drop low-signal automated content unconditionally.
    if record.source_type_hint in _NOISE_SOURCE_TYPES:
        return False

    # Temporal filter: record must be at least as recent as after_date.
    after_date = filters.get("after_date")
    if after_date is not None and isinstance(after_date, datetime) and record.created_at < after_date:
        return False

    # Generic equality filters (skip after_date already handled above).
    for key, expected in filters.items():
        if key == "after_date":
            continue
        actual = getattr(record, key, None)
        if actual is None:
            actual = record.metadata.get(key)
        if actual != expected:
            return False

    return True


def _naive_score(content: str, terms: set[str]) -> float:
    """Fraction of query terms present in the content (``0..1``)."""
    if not terms:
        return 0.0
    haystack = content.lower()
    hits = sum(1 for term in terms if term in haystack)
    return hits / len(terms)
