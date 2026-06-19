"""Tests for source-level deduplication."""
from __future__ import annotations

import pytest

from app.core.dedup import deduplicate_by_source
from app.models.common import FactType
from app.models.memory import MemoryRecord
from app.models.retrieval import ScoredFact


def _make_fact(id_: str, source_doc_id: str | None, score: float) -> ScoredFact:
    """Helper: create a ScoredFact with the given fields."""
    record = MemoryRecord(
        id=id_,
        tenant_id="test",
        content=f"content for {id_}",
        record_type=FactType.FACT,
        source_doc_id=source_doc_id,
    )
    return ScoredFact(record=record, score=score, source_doc_id=source_doc_id)


def test_empty_input() -> None:
    """Empty list in, empty list out."""
    assert deduplicate_by_source([]) == []


def test_single_source_keeps_max_per_source() -> None:
    """Three facts from the same source — only top-2 should survive."""
    facts = [
        _make_fact("f1", "doc1", 0.9),
        _make_fact("f2", "doc1", 0.8),
        _make_fact("f3", "doc1", 0.7),
    ]
    result = deduplicate_by_source(facts, max_per_source=2)
    assert len(result) == 2
    assert result[0].record.id == "f1"
    assert result[1].record.id == "f2"


def test_multiple_sources() -> None:
    """Third fact from each source should be dropped."""
    facts = [
        _make_fact("f1", "doc1", 0.9),
        _make_fact("f2", "doc2", 0.85),
        _make_fact("f3", "doc1", 0.8),
        _make_fact("f4", "doc2", 0.75),
        _make_fact("f5", "doc1", 0.7),   # 3rd from doc1 — should be cut
        _make_fact("f6", "doc2", 0.6),   # 3rd from doc2 — should be cut
    ]
    result = deduplicate_by_source(facts, max_per_source=2)
    ids = [r.record.id for r in result]
    assert "f5" not in ids
    assert "f6" not in ids
    assert len(result) == 4


def test_no_source_doc_id_always_kept() -> None:
    """Facts with source_doc_id=None should always be kept (each treated as unique)."""
    facts = [
        _make_fact("f1", None, 0.9),
        _make_fact("f2", None, 0.8),
        _make_fact("f3", None, 0.7),
    ]
    result = deduplicate_by_source(facts, max_per_source=1)
    # all should be kept since source_doc_id is None
    assert len(result) == 3


def test_max_per_source_one() -> None:
    """max_per_source=1 should keep only the first fact per source."""
    facts = [
        _make_fact("f1", "doc1", 0.9),
        _make_fact("f2", "doc1", 0.8),
        _make_fact("f3", "doc2", 0.7),
    ]
    result = deduplicate_by_source(facts, max_per_source=1)
    ids = [r.record.id for r in result]
    assert "f1" in ids
    assert "f3" in ids
    assert "f2" not in ids


def test_preserves_ranking_order() -> None:
    """Facts should remain in their original relative order after dedup."""
    facts = [
        _make_fact("f1", "doc1", 0.9),
        _make_fact("f2", "doc2", 0.85),
        _make_fact("f3", "doc1", 0.8),
        _make_fact("f4", "doc3", 0.7),
    ]
    result = deduplicate_by_source(facts)
    ids = [r.record.id for r in result]
    # f1 comes before f2 comes before f4
    assert ids.index("f1") < ids.index("f2") < ids.index("f4")


def test_mixed_source_and_none() -> None:
    """Mix of sourced and unsourced facts — sourced are deduplicated, none are kept."""
    facts = [
        _make_fact("f1", "doc1", 0.9),
        _make_fact("f2", None, 0.88),
        _make_fact("f3", "doc1", 0.8),  # second from doc1 — kept
        _make_fact("f4", None, 0.7),    # second None — always kept
        _make_fact("f5", "doc1", 0.6),  # third from doc1 — dropped
    ]
    result = deduplicate_by_source(facts, max_per_source=2)
    ids = [r.record.id for r in result]
    assert "f1" in ids
    assert "f2" in ids
    assert "f3" in ids
    assert "f4" in ids
    assert "f5" not in ids
    assert len(result) == 4


def test_max_per_source_default_is_two() -> None:
    """Default max_per_source should be 2."""
    facts = [
        _make_fact("f1", "doc1", 0.9),
        _make_fact("f2", "doc1", 0.8),
        _make_fact("f3", "doc1", 0.7),
    ]
    result = deduplicate_by_source(facts)  # default max_per_source=2
    assert len(result) == 2
