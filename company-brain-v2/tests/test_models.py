"""Tests for the domain models and their validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import (
    EntityRef,
    EntityType,
    Err,
    ExtractedFact,
    FactType,
    MemoryRecord,
    Ok,
    RawDocument,
    RetrievalQuery,
    RetrievalResult,
    SourceType,
    ValidityKind,
)

# ── RawDocument ───────────────────────────────────────────────────────────────

def test_raw_document_autofills_ids_and_timestamps() -> None:
    doc = RawDocument(source=SourceType.GMAIL, source_id="m1", content="hello")
    assert doc.id.startswith("doc_")
    assert doc.tenant_id == "default"
    assert doc.fetched_at is not None


def test_raw_document_strips_whitespace() -> None:
    doc = RawDocument(source=SourceType.GMAIL, source_id="m1", content="  hello  ")
    assert doc.content == "hello"


# ── ExtractedFact ─────────────────────────────────────────────────────────────

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


def test_fact_triple_fields() -> None:
    fact = ExtractedFact(
        document_id="doc_1",
        source=SourceType.GMAIL,
        statement="Alice approved $500k budget.",
        subject="Alice",
        predicate="approved",
        object_="$500k budget",
    )
    assert fact.subject == "Alice"
    assert fact.predicate == "approved"
    assert fact.object_ == "$500k budget"


def test_fact_triple_via_object_alias() -> None:
    """The 'object' alias should also work for construction."""
    fact = ExtractedFact(
        document_id="doc_1",
        source=SourceType.GMAIL,
        statement="Alice approved $500k.",
        **{"object": "$500k"},  # alias
    )
    assert fact.object_ == "$500k"


def test_fact_tags_and_natural_language() -> None:
    fact = ExtractedFact(
        document_id="d1",
        source=SourceType.NOTION,
        statement="Budget approved.",
        tags=["budget", "q2"],
        natural_language="Alice approved the Q2 budget.",
    )
    assert fact.tags == ["budget", "q2"]
    assert fact.natural_language == "Alice approved the Q2 budget."


def test_fact_validity_kind_default() -> None:
    fact = ExtractedFact(document_id="d1", source=SourceType.GMAIL, statement="s")
    assert fact.validity_kind is ValidityKind.CURRENT


def test_fact_validity_kind_historical() -> None:
    fact = ExtractedFact(
        document_id="d1",
        source=SourceType.GMAIL,
        statement="We used Redis.",
        validity_kind=ValidityKind.HISTORICAL,
    )
    assert fact.validity_kind is ValidityKind.HISTORICAL


def test_fact_id_has_prefix() -> None:
    fact = ExtractedFact(document_id="d1", source=SourceType.GMAIL, statement="s")
    assert fact.id.startswith("fact_")


# ── MemoryRecord ──────────────────────────────────────────────────────────────

def test_memory_record_touch_updates_timestamp() -> None:
    record = MemoryRecord(content="c")
    before = record.updated_at
    record.touch()
    assert record.updated_at >= before


# ── RetrievalResult ───────────────────────────────────────────────────────────

def test_retrieval_result_score_bounds() -> None:
    record = MemoryRecord(content="c")
    with pytest.raises(ValidationError):
        RetrievalResult(record=record, score=2.0)


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        RetrievalQuery(text="q", bogus="nope")  # type: ignore[call-arg]


# ── ValidityKind ──────────────────────────────────────────────────────────────

def test_validity_kind_values() -> None:
    assert ValidityKind.CURRENT == "current"
    assert ValidityKind.HISTORICAL == "historical"
    assert ValidityKind.TENTATIVE == "tentative"


# ── Ok / Err result envelopes ─────────────────────────────────────────────────

def test_ok_envelope_stores_value() -> None:
    result: Ok[str] = Ok(value="done")
    assert result.ok is True
    assert result.value == "done"


def test_err_envelope_stores_error() -> None:
    result = Err(error="write failed", details={"record_id": "mem_123"})
    assert result.ok is False
    assert result.error == "write failed"
    assert result.details["record_id"] == "mem_123"


def test_err_envelope_defaults_empty_details() -> None:
    result = Err(error="oops")
    assert result.details == {}


def test_ok_and_err_discriminated_via_ok_flag() -> None:
    results: list[Ok[int] | Err] = [Ok(value=42), Err(error="fail")]
    successes = [r for r in results if r.ok]
    failures = [r for r in results if not r.ok]
    assert len(successes) == 1
    assert len(failures) == 1
