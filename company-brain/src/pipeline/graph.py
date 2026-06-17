from langgraph.graph import StateGraph, END

from src.pipeline.state import ExtractionState
from src.pipeline.nodes import classify_node, extract_node, deduplicate_node, write_node


def should_extract(state: ExtractionState) -> str:
    return "extract" if state.get("is_worth_remembering") else END


def should_write(state: ExtractionState) -> str:
    return "write" if not state.get("is_duplicate") else END


def build_extraction_graph() -> StateGraph:
    graph = StateGraph(ExtractionState)

    graph.add_node("classify", classify_node)
    graph.add_node("extract", extract_node)
    graph.add_node("deduplicate", deduplicate_node)
    graph.add_node("write", write_node)

    graph.set_entry_point("classify")
    graph.add_conditional_edges("classify", should_extract, {"extract": "extract", END: END})
    graph.add_edge("extract", "deduplicate")
    graph.add_conditional_edges("deduplicate", should_write, {"write": "write", END: END})
    graph.add_edge("write", END)

    return graph.compile()
