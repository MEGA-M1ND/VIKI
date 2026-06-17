"""Tests for the full classify → extract → dedupe → write pipeline graph."""

from __future__ import annotations

import json

import pytest

from app.graphs.pipeline_graph import build_pipeline_graph
from app.llm.fake import SequentialLLMProvider
from app.memory.in_memory import InMemoryStore
from app.models import RawDocument, SourceType

_WORTHY = json.dumps({"is_worth_remembering": True, "confidence": 0.9, "reasoning": "decision"})
_UNWORTHY = json.dumps({"is_worth_remembering": False, "confidence": 0.95, "reasoning": "routine"})
_EXTRACT_ONE = json.dumps({
    "facts": [
        {
            "statement": "Alice approved $500k budget",
            "subject": "Alice",
            "predicate": "approved",
            "object": "$500k budget",
            "tags": ["budget"],
            "fact_type": "decision",
            "confidence": 0.95,
        }
    ],
    "entities": [{"name": "Alice", "type": "person"}],
})


def _make_doc(content: str = "Alice approved the Q2 budget of $500k.") -> RawDocument:
    return RawDocument(source=SourceType.GMAIL, source_id="m1", content=content)


async def test_pipeline_ingests_worthy_document() -> None:
    # Call order: classify → extract
    llm = SequentialLLMProvider([_WORTHY, _EXTRACT_ONE])
    store = InMemoryStore()
    graph = build_pipeline_graph(llm, store)

    state = await graph.ainvoke({"document": _make_doc()})

    assert state.get("is_worth_remembering") is True
    assert len(state.get("facts", [])) == 1
    assert len(state.get("records", [])) == 1
    assert state["records"][0].content == "Alice approved $500k budget"


async def test_pipeline_skips_unworthy_document() -> None:
    # Only classify is called; extraction should be skipped
    llm = SequentialLLMProvider([_UNWORTHY])
    store = InMemoryStore()
    graph = build_pipeline_graph(llm, store)

    state = await graph.ainvoke({"document": _make_doc("Hi, how are you?")})

    assert state.get("is_worth_remembering") is False
    # Extraction and write nodes were not reached
    assert not state.get("facts")
    assert not state.get("records")
    # LLM was called exactly once (only classify)
    assert len(llm.calls) == 1


async def test_pipeline_deduplicates_same_document() -> None:
    # Each run: classify + extract (2 calls per run)
    llm = SequentialLLMProvider([_WORTHY, _EXTRACT_ONE, _WORTHY, _EXTRACT_ONE])
    store = InMemoryStore()
    graph = build_pipeline_graph(llm, store)

    doc = _make_doc()
    state1 = await graph.ainvoke({"document": doc})
    assert len(state1.get("records", [])) == 1

    # Second run: same document → deduped → no new records
    state2 = await graph.ainvoke({"document": doc})
    assert len(state2.get("new_facts", [])) == 0
    assert len(state2.get("records", [])) == 0


async def test_pipeline_extract_error_raises_extraction_error() -> None:
    """If the LLM returns non-JSON, extraction raises ExtractionError."""
    from app.core.exceptions import ExtractionError

    llm = SequentialLLMProvider([_WORTHY, "not valid json"])
    store = InMemoryStore()
    graph = build_pipeline_graph(llm, store)

    with pytest.raises(ExtractionError):
        await graph.ainvoke({"document": _make_doc()})


async def test_pipeline_fact_triple_stored_in_metadata() -> None:
    """Triple fields (subject/predicate/object) should survive write → memory."""
    llm = SequentialLLMProvider([_WORTHY, _EXTRACT_ONE])
    store = InMemoryStore()
    graph = build_pipeline_graph(llm, store)

    state = await graph.ainvoke({"document": _make_doc()})
    record = state["records"][0]

    assert record.metadata.get("subject") == "Alice"
    assert record.metadata.get("predicate") == "approved"
    assert record.metadata.get("object") == "$500k budget"
