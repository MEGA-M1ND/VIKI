"""Context injection graph (LangGraph).

A thin graph that wraps the retrieve→assemble flow so it can be embedded inside
a larger agent graph as a node or run standalone. The factory
:func:`make_context_node` produces a single async function compatible with
LangGraph's node signature.

Usage (standalone retrieval)::

    graph = build_context_graph(store, assembler)
    result = await graph.ainvoke({
        "tenant_id": "acme",
        "user_query": "What did Alice decide about the Q2 budget?",
    })
    print(result["injected_context"])

Usage (embed in agent graph)::

    agent_graph.add_node("inject_context", make_context_node(store, assembler))
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.logging import get_logger
from app.graphs.state import RetrievalState
from app.memory.base import MemoryStore
from app.models.retrieval import RetrievalQuery
from app.services.interfaces import ContextAssembler

logger = get_logger(__name__)


def make_context_node(
    store: MemoryStore,
    assembler: ContextAssembler,
    *,
    query_field: str = "user_query",
    tenant_field: str = "tenant_id",
    context_output_field: str = "injected_context",
    sources_output_field: str = "injected_sources",
    limit: int = 5,
    max_chars: int = 4000,
) -> Callable[[dict], Awaitable[dict]]:
    """Return an async node function that retrieves and assembles context.

    The node reads *query_field* and *tenant_field* from the incoming state dict
    and writes *context_output_field* and *sources_output_field* back.

    Args:
        store: Memory backend to retrieve from.
        assembler: Renders ranked results into a context string.
        query_field: Key in state that holds the user query string.
        tenant_field: Key in state that holds the tenant id.
        context_output_field: Output key for the formatted context block.
        sources_output_field: Output key for the list of source document ids.
        limit: Max number of results to fetch.
        max_chars: Budget for the rendered context.
    """

    async def context_node(state: dict) -> dict:
        query_text = state.get(query_field, "")
        tenant_id = state.get(tenant_field, "default")

        if not query_text:
            return {**state, context_output_field: "", sources_output_field: []}

        query = RetrievalQuery(tenant_id=tenant_id, text=query_text, limit=limit)
        try:
            results = await store.query(query)
        except Exception as exc:  # noqa: BLE001
            logger.error("context_node.query_failed", error=str(exc))
            return {**state, context_output_field: "", sources_output_field: [], "error": str(exc)}

        context = assembler.assemble(results, max_chars=max_chars)
        sources = [ref for r in results for ref in r.record.source_refs]

        logger.info("context_node.done", hits=len(results), chars=len(context))
        return {**state, context_output_field: context, sources_output_field: sources}

    return context_node


def build_context_graph(store: MemoryStore, assembler: ContextAssembler) -> CompiledStateGraph:
    """Compile a standalone context-injection graph."""

    async def retrieve_node(state: RetrievalState) -> RetrievalState:
        tenant_id = state.get("tenant_id", "default")
        query_text = state.get("user_query", "")
        limit = state.get("limit", 5)

        query = RetrievalQuery(tenant_id=tenant_id, text=query_text, limit=limit)
        try:
            results = await store.query(query)
        except Exception as exc:  # noqa: BLE001
            logger.error("context_graph.retrieve_failed", error=str(exc))
            return {**state, "results": [], "error": str(exc)}
        return {**state, "results": results}
    async def assemble_node(state: RetrievalState) -> RetrievalState:
        results = state.get("results") or []
        max_chars = 4000
        context = assembler.assemble(results, max_chars=max_chars)
        sources = [ref for r in results for ref in r.record.source_refs]
        return {**state, "injected_context": context, "injected_sources": sources}
    graph = StateGraph(RetrievalState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("assemble", assemble_node)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "assemble")
    graph.add_edge("assemble", END)
    return graph.compile()


class DefaultContextAssembler:
    """Default implementation of :class:`~app.services.interfaces.ContextAssembler`.

    Renders results as a Markdown section with scored bullets. Respects the
    *max_chars* budget by truncating the lowest-scored results first.
    """

    def assemble(self, results: list, *, max_chars: int = 4000) -> str:
        if not results:
            return ""

        header = "# Relevant context from Company Brain\n\n"
        lines: list[str] = []
        total = len(header)

        for r in results:
            line = f"- [{r.score:.2f}] {r.record.content}"
            if total + len(line) + 1 > max_chars:
                break
            lines.append(line)
            total += len(line) + 1

        if not lines:
            return ""
        return header + "\n".join(lines)
