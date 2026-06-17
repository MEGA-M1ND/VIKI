"""Full classify → extract → dedupe → write pipeline (LangGraph).

Wires all four nodes together with conditional edges so expensive LLM calls are
skipped when the classifier rejects a document or deduplication finds nothing new.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graphs.nodes.classify import make_classify_node
from app.graphs.nodes.dedupe import make_dedupe_node
from app.graphs.nodes.extract import make_extract_node
from app.graphs.nodes.write import make_write_node
from app.graphs.state import PipelineState
from app.llm.base import LLMProvider
from app.memory.base import MemoryStore


def build_pipeline_graph(llm: LLMProvider, store: MemoryStore) -> CompiledStateGraph:
    """Compile the full ingestion pipeline.

    Args:
        llm: LLM provider for classification and extraction.
        store: Memory backend for deduplication and persistence.

    Returns:
        Compiled LangGraph accepting/returning :class:`PipelineState`.
    """
    classify_node = make_classify_node(llm)
    extract_node = make_extract_node(llm)
    dedupe_node = make_dedupe_node(store)
    write_node = make_write_node(store)

    def should_extract(state: PipelineState) -> str:
        if state.get("error"):
            return END
        if not state.get("is_worth_remembering"):
            return END
        return "extract"

    def should_dedupe(state: PipelineState) -> str:
        if state.get("error") or not state.get("facts"):
            return END
        return "dedupe"

    def should_write(state: PipelineState) -> str:
        if state.get("error") or not state.get("new_facts"):
            return END
        return "write"

    graph = StateGraph(PipelineState)
    graph.add_node("classify", classify_node)  # type: ignore[call-overload]
    graph.add_node("extract", extract_node)  # type: ignore[call-overload]
    graph.add_node("dedupe", dedupe_node)  # type: ignore[call-overload]
    graph.add_node("write", write_node)  # type: ignore[call-overload]

    graph.set_entry_point("classify")
    graph.add_conditional_edges("classify", should_extract, {"extract": "extract", END: END})
    graph.add_conditional_edges("extract", should_dedupe, {"dedupe": "dedupe", END: END})
    graph.add_conditional_edges("dedupe", should_write, {"write": "write", END: END})
    graph.add_edge("write", END)

    return graph.compile()
