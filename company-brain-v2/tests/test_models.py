"""Tests for the domain models and their validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import (
    EntityRef,
    EntityType,
    ExtractedFact,
    FactType,
    MemoryRecord,
    RawDocument,
    RetrievalQuery,
    RetrievalResult,
    SourceType,
)


def test_raw_document_autofills_ids_and_timestamps() -> None:
    doc = RawDocument(source=SourceType.GMAIL, source_id="m1", content="hello")
    assert doc.id.startswith("doc_")
    assert doc.tenant_id == "default"
    assert doc.fetched_at is not None


def test_extracted_fact_confidence_bounds() -> None:
    with pytest.raises(ValidationError):
        ExtractedFact(
            document_id="doc_1",
            source=SourceType.NOTION,
            statement="x",
            confidence=1.5,
        )


def test_fact_with_entities() -> None:
    fact = ExtractedFact(
        document_id="doc_1",
        source=SourceType.SLACK,
        fact_type=FactType.DECISION,
        statement="Team chose Postgres.",
        entities=[EntityRef(name="Postgres", type=EntityType.CONCEPT)],
    )
    assert fact.entities[0].type is EntityType.CONCEPT


def test_memory_record_touch_updates_timestamp() -> None:
    record = MemoryRecord(content="c")
    before = record.updated_at
    record.touch()
    assert record.updated_at >= before


def test_retrieval_result_score_bounds() -> None:
    record = MemoryRecord(content="c")
    with pytest.raises(ValidationError):
        RetrievalResult(record=record, score=2.0)


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        RetrievalQuery(text="q", bogus="nope")  # type: ignore[call-arg]
