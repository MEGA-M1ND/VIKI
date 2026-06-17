"""Shared state schema for LangGraph pipelines.

The ingestion pipeline threads a single :class:`IngestionState` object through
its nodes. Fields are populated progressively; ``None`` means "not yet
computed".
"""

from __future__ import annotations

from typing import TypedDict

from app.models.documents import RawDocument
from app.models.facts import ExtractedFact
from app.models.memory import MemoryRecord


class IngestionState(TypedDict, total=False):
    """State passed between ingestion graph nodes.

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
