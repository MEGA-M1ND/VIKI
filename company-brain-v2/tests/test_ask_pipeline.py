"""Tests for the /ask pipeline: rrf_merge purity and backend-agnostic dedup."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.core.dedup import deduplicate_by_source
from app.db.retriever import rrf_merge
from app.memory.in_memory import InMemoryStore
from app.models.memory import MemoryRecord
from app.models.retrieval import RetrievalQuery, ScoredFact

# ---------------------------------------------------------------------------
# Task 2a: rrf_merge pure-function unit tests (no DB, no network)
# ---------------------------------------------------------------------------


def test_rrf_merge_combines_both_arms() -> None:
    """rrf_merge gives a higher score to IDs that appear in both ranked lists."""
    vec_ids = ["a", "b", "c"]
    bm25_ids = ["c", "d", "e"]
    scores = rrf_merge(vec_ids, bm25_ids)

    # "c" appears in both → higher combined score than single-arm IDs
    assert scores["c"] > scores["a"], "c appears in both arms; a only in vector"
    assert scores["c"] > scores["d"], "c appears in both arms; d only in BM25"

    # All five IDs must appear in the output
    for rec_id in ["a", "b", "c", "d", "e"]:
        assert rec_id in scores


def test_rrf_merge_rank_0_beats_rank_1() -> None:
    """Rank 0 (best) produces a higher RRF contribution than rank 1."""
    scores = rrf_merge(["best", "second"], [])
    assert scores["best"] > scores["second"]


def test_rrf_merge_empty_arms() -> None:
    """Empty input lists produce an empty mapping, not an error."""
    assert rrf_merge([], []) == {}
    assert rrf_merge(["x"], []) == {"x": pytest.approx(1 / 60)}
    assert rrf_merge([], ["x"]) == {"x": pytest.approx(1 / 60)}


def test_rrf_merge_custom_k() -> None:
    """Custom k smoothing constant is respected."""
    scores_60 = rrf_merge(["a"], [], k=60)
    scores_10 = rrf_merge(["a"], [], k=10)
    # Smaller k → higher score at rank 0 (1/(10+0) > 1/(60+0))
    assert scores_10["a"] > scores_60["a"]


# ---------------------------------------------------------------------------
# Task 2b: backend-agnostic dedup in the retrieval path
# ---------------------------------------------------------------------------


def test_dedup_limits_per_source() -> None:
    """deduplicate_by_source keeps at most max_per_source facts per source_doc_id."""
    facts = [
        ScoredFact(
            record=MemoryRecord(tenant_id="t", content=f"fact {i}", source_doc_id="doc1"),
            score=1.0 - i * 0.1,
            source_doc_id="doc1",
        )
        for i in range(5)
    ]
    result = deduplicate_by_source(facts, max_per_source=2)
    assert len(result) == 2
    # Highest-scoring facts are kept (input order preserved)
    assert result[0].score == pytest.approx(1.0)
    assert result[1].score == pytest.approx(0.9)


def test_dedup_keeps_no_source_records() -> None:
    """Facts with no source_doc_id are always kept (treated as unique sources)."""
    facts = [
        ScoredFact(
            record=MemoryRecord(tenant_id="t", content=f"no-source {i}"),
            score=0.9,
            source_doc_id=None,
        )
        for i in range(5)
    ]
    result = deduplicate_by_source(facts, max_per_source=1)
    assert len(result) == 5


def test_ask_pipeline_dedup_excludes_same_source(client) -> None:
    """Three facts sharing the same source_doc_id → at most 2 survive dedup."""
    store = client.app.state.container.memory_store
    now = datetime.now(tz=UTC)

    shared_doc = "shared_source_doc_001"
    for i in range(3):
        asyncio.run(
            store.write(
                MemoryRecord(
                    tenant_id="default",
                    content=f"duplicate fact {i} about Google recruitment",
                    source_doc_id=shared_doc,
                    created_at=now - timedelta(days=i),
                    updated_at=now - timedelta(days=i),
                )
            )
        )

    q = RetrievalQuery(tenant_id="default", text="google recruitment", limit=10)
    raw_results = asyncio.run(store.query(q))
    # All 3 score > 0 against "google recruitment" terms
    assert len(raw_results) == 3

    # Simulate the /ask dedup step (same logic as routes_ask.py step 3a)
    scored = [
        ScoredFact(
            record=r.record, score=r.score, source_doc_id=r.record.source_doc_id
        )
        for r in raw_results
    ]
    deduped = deduplicate_by_source(scored, max_per_source=2)
    assert len(deduped) <= 2, "Dedup must cap at 2 facts per source_doc_id"


# ---------------------------------------------------------------------------
# Task 2c: temporal filter correctly excludes stale records
# ---------------------------------------------------------------------------


def test_temporal_filter_excludes_old_records() -> None:
    """after_date filter excludes records older than the cutoff."""
    store = InMemoryStore()
    now = datetime.now(tz=UTC)

    asyncio.run(
        store.write(
            MemoryRecord(
                tenant_id="t",
                content="recent job outreach from Google",
                created_at=now - timedelta(days=10),
                updated_at=now - timedelta(days=10),
            )
        )
    )
    asyncio.run(
        store.write(
            MemoryRecord(
                tenant_id="t",
                content="old job outreach from Microsoft",
                created_at=now - timedelta(days=120),
                updated_at=now - timedelta(days=120),
            )
        )
    )

    after_date = now - timedelta(days=30)
    q = RetrievalQuery(
        tenant_id="t",
        text="job outreach",
        limit=10,
        filters={"after_date": after_date},
    )
    results = asyncio.run(store.query(q))

    contents = [r.record.content for r in results]
    assert any("Google" in c for c in contents), "Recent record should appear"
    assert all("Microsoft" not in c for c in contents), "Old record must be excluded"
