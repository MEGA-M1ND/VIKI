"""Deduplication node.

Filters out facts that are already captured in memory. Uses a pluggable
similarity hook; the default is a naive key-based exact-match deduper that
computes a canonical hash of the fact's statement.

A semantic deduper (embedding cosine similarity) can be swapped in by passing
a custom ``deduper`` to :func:`make_dedupe_node`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.logging import get_logger
from app.graphs.state import PipelineState
from app.memory.base import MemoryStore
from app.models.facts import ExtractedFact
from app.models.memory import MemoryRecord
from app.models.retrieval import RetrievalQuery

logger = get_logger(__name__)

_SIMILARITY_THRESHOLD = 0.92


def _dedupe_key(fact: ExtractedFact) -> str:
    """Deterministic key for a fact — used as a quick exact-match check."""
    payload = f"{fact.tenant_id}:{fact.source}:{fact.statement.strip().lower()}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


async def _default_find_duplicate(
    fact: ExtractedFact, store: MemoryStore
) -> MemoryRecord | None:
    """Check for an existing record with the same content.

    First tries a direct dedupe_key lookup (O(1) SQL for pgvector, O(n) scan
    for in-memory). Falls back to vector similarity for near-duplicate detection.
    """
    key = _dedupe_key(fact)

    # Fast path: exact hash match via direct metadata lookup
    existing = await store.find_by_dedupe_key(tenant_id=fact.tenant_id, dedupe_key=key)
    if existing:
        return existing

    # Slow path: semantic similarity for near-duplicates
    query = RetrievalQuery(
        tenant_id=fact.tenant_id,
        text=fact.statement,
        limit=5,
        filters={},
    )
    results = await store.query(query)
    for result in results:
        if result.score >= _SIMILARITY_THRESHOLD:
            return result.record
    return None


def make_dedupe_node(store: MemoryStore) -> Callable[[PipelineState], Awaitable[Any]]:
    """Return a dedupe node that checks *store* for existing records."""

    async def dedupe_node(state: PipelineState) -> dict:
        facts = state.get("facts") or []
        new_facts: list[ExtractedFact] = []

        for fact in facts:
            existing = await _default_find_duplicate(fact, store)
            if existing:
                logger.info(
                    "dedupe.duplicate_skipped",
                    fact_id=fact.id,
                    existing_id=existing.id,
                )
            else:
                new_facts.append(fact)

        logger.info(
            "dedupe.done",
            total=len(facts),
            new=len(new_facts),
            skipped=len(facts) - len(new_facts),
        )
        return {**state, "new_facts": new_facts}

    return dedupe_node
