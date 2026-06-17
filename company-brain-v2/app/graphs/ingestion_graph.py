"""Ingestion pipeline wiring (LangGraph).

Defines the *shape* of the ingest flow — extract → persist — as a compiled
LangGraph. The node bodies delegate to injected collaborators
(:class:`BaseExtractor`, :class:`MemoryStore`) so this module owns orchestration
only, never business logic.

The graph is built lazily via :func:`build_ingestion_graph` because the
collaborators are runtime dependencies.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.logging import get_logger
from app.graphs.state import IngestionState
from app.ingestion.base import BaseExtractor
from app.memory.base import MemoryStore
from app.models.memory import MemoryRecord

logger = get_logger(__name__)


def build_ingestion_graph(extractor: BaseExtractor, store: MemoryStore) -> CompiledStateGraph:
    """Compile the ingestion graph for the given collaborators.

    Args:
        extractor: Strategy that turns a document into facts.
        store: Memory backend that persists records.

    Returns:
        A compiled LangGraph runnable accepting/returning :class:`IngestionState`.
    """

    async def extract_node(state: IngestionState) -> IngestionState:
        document = state["document"]
        try:
            facts = await extractor.extract(document)
        except Exception as exc:  # noqa: BLE001 - captured into state, not raised
            logger.error("ingest.extract_failed", doc_id=document.id, error=str(exc))
            return {**state, "facts": [], "error": str(exc)}
        logger.info("ingest.extracted", doc_id=document.id, facts=len(facts))
        return {**state, "facts": facts}

    async def persist_node(state: IngestionState) -> IngestionState:
        facts = state.get("facts") or []
        records: list[MemoryRecord] = []
        for fact in facts:
            record = MemoryRecord(
                tenant_id=fact.tenant_id,
                content=fact.statement,
                record_type=fact.fact_type,
                source=fact.source,
                source_refs=[fact.document_id, fact.id],
                metadata={"confidence": fact.confidence},
            )
            records.append(await store.write(record))
        logger.info("ingest.persisted", records=len(records))
        return {**state, "records": records}

    def should_persist(state: IngestionState) -> str:
        """Skip persistence if extraction errored or produced nothing."""
        if state.get("error") or not state.get("facts"):
            return END
        return "persist"

    graph = StateGraph(IngestionState)
    graph.add_node("extract", extract_node)
    graph.add_node("persist", persist_node)
    graph.set_entry_point("extract")
    graph.add_conditional_edges("extract", should_persist, {"persist": "persist", END: END})
    graph.add_edge("persist", END)
    return graph.compile()
