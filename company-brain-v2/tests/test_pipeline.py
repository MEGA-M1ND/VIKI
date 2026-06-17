"""End-to-end skeleton test: extractor -> ingestion graph -> memory -> context.

Uses a trivial fake extractor (no LLM) to prove the wiring is correct and the
interfaces compose.
"""

from __future__ import annotations

import pytest

from app.context.provider import MemoryContextProvider
from app.graphs.ingestion_graph import build_ingestion_graph
from app.graphs.state import IngestionState
from app.ingestion.base import BaseExtractor
from app.memory.in_memory import InMemoryStore
from app.models import ExtractedFact, RawDocument, SourceType


class _FakeExtractor(BaseExtractor):
    """Returns one fact echoing the document content."""

    async def extract(self, document: RawDocument) -> list[ExtractedFact]:
        return [
            ExtractedFact(
                document_id=document.id,
                tenant_id=document.tenant_id,
                source=document.source,
                statement=document.content,
            )
        ]


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


async def test_ingestion_graph_persists_facts(store: InMemoryStore) -> None:
    graph = build_ingestion_graph(_FakeExtractor(), store)
    doc = RawDocument(
        source=SourceType.GMAIL,
        source_id="m1",
        content="We shipped the new onboarding flow on Tuesday.",
    )

    state: IngestionState = await graph.ainvoke({"document": doc})

    assert len(state["records"]) == 1
    assert state["records"][0].content == doc.content


async def test_context_provider_retrieves_written_memory(store: InMemoryStore) -> None:
    graph = build_ingestion_graph(_FakeExtractor(), store)
    doc = RawDocument(
        source=SourceType.NOTION,
        source_id="p1",
        content="The Q3 roadmap prioritizes reliability work.",
    )
    await graph.ainvoke({"document": doc})

    provider = MemoryContextProvider(store)
    context = await provider.build_context(tenant_id="default", query="roadmap reliability")

    assert "Q3 roadmap" in context
    assert context.startswith("# Relevant context")


async def test_tenant_isolation(store: InMemoryStore) -> None:
    graph = build_ingestion_graph(_FakeExtractor(), store)
    await graph.ainvoke(
        {
            "document": RawDocument(
                source=SourceType.SLACK,
                source_id="s1",
                content="tenant-a secret",
                tenant_id="tenant-a",
            )
        }
    )

    provider = MemoryContextProvider(store)
    other = await provider.retrieve(tenant_id="tenant-b", query="secret")
    assert other == []
