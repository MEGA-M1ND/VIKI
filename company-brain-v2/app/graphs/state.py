"""Shared state schemas for LangGraph pipelines.

Each pipeline has its own TypedDict. Fields are populated progressively;
``None`` (or an absent key for total=False dicts) means "not yet computed".
"""

from __future__ import annotations

from typing import TypedDict

from app.models.documents import RawDocument
from app.models.facts import ExtractedFact
from app.models.memory import MemoryRecord
from app.models.retrieval import RetrievalResult


class IngestionState(TypedDict, total=False):
    """State for the simple extract→persist ingestion graph.

    Keys:
        document: The input raw document (required on entry).
        facts: Facts produced by the extraction node.
        records: Memory records produced by the persistence node.
        error: Error message if a node failed (halts the run).
    """

    document: RawDocument
    facts: list[ExtractedFact]
    records: list[MemoryRecord]
    error: str | None


class PipelineState(TypedDict, total=False):
    """State for the full classify→extract→dedupe→write pipeline.

    Keys:
        document: The input raw document (required on entry).
        is_worth_remembering: Classification outcome.
        classifier_reasoning: Free-text reasoning from the classifier node.
        confidence: Classifier confidence in [0, 1].
        facts: All facts produced by the extraction node.
        new_facts: Facts that survived deduplication (subset of facts).
        records: Successfully written memory records.
        failed_facts: Facts that could not be written (serialised for dead-letter).
        error: Error message if a node failed irrecoverably.
    """

    document: RawDocument
    is_worth_remembering: bool | None
    classifier_reasoning: str | None
    confidence: float | None
    facts: list[ExtractedFact]
    new_facts: list[ExtractedFact]
    records: list[MemoryRecord]
    failed_facts: list[dict]
    error: str | None


class RetrievalState(TypedDict, total=False):
    """State for the retrieve→assemble context-injection graph.

    Keys:
        tenant_id: Tenant whose memory to search.
        user_query: The agent's current question or task description.
        limit: Max number of memory records to include.
        results: Ranked retrieval results.
        injected_context: Formatted context block ready for prompt injection.
        injected_sources: Source document ids included in the context.
        error: Error message if retrieval or assembly failed.
    """

    tenant_id: str
    user_query: str
    limit: int
    results: list[RetrievalResult]
    injected_context: str
    injected_sources: list[str]
    error: str | None
