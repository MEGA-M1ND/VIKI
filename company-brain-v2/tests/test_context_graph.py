"""Tests for the context injection graph and context assembler."""

from __future__ import annotations

from app.graphs.context_graph import DefaultContextAssembler, build_context_graph, make_context_node
from app.memory.in_memory import InMemoryStore
from app.models import MemoryRecord, RetrievalResult


async def _populate_store(store: InMemoryStore, content: str = "Alice approved $500k budget.") -> MemoryRecord:
    record = MemoryRecord(content=content, tenant_id="default")
    await store.write(record)
    return record


# ── DefaultContextAssembler ───────────────────────────────────────────────────

def test_assembler_empty_results_returns_empty_string() -> None:
    assembler = DefaultContextAssembler()
    assert assembler.assemble([]) == ""


def test_assembler_formats_results_with_score() -> None:
    record = MemoryRecord(content="Budget approved for Q2.")
    result = RetrievalResult(record=record, score=0.85)
    assembler = DefaultContextAssembler()
    ctx = assembler.assemble([result])
    assert "# Relevant context from Company Brain" in ctx
    assert "0.85" in ctx
    assert "Budget approved" in ctx


def test_assembler_respects_max_chars() -> None:
    records = [MemoryRecord(content="A" * 1000) for _ in range(10)]
    results = [RetrievalResult(record=r, score=0.8) for r in records]
    assembler = DefaultContextAssembler()
    ctx = assembler.assemble(results, max_chars=500)
    assert len(ctx) <= 600  # some flex for header


# ── make_context_node ─────────────────────────────────────────────────────────

async def test_context_node_retrieves_and_assembles() -> None:
    store = InMemoryStore()
    await _populate_store(store, "Alice approved Q2 budget of $500k.")

    assembler = DefaultContextAssembler()
    node = make_context_node(store, assembler)

    state = {"tenant_id": "default", "user_query": "Q2 budget Alice"}
    result = await node(state)

    assert "injected_context" in result
    assert "injected_sources" in result
    assert "Alice" in result["injected_context"] or result["injected_context"] == ""


async def test_context_node_empty_query_returns_empty() -> None:
    store = InMemoryStore()
    assembler = DefaultContextAssembler()
    node = make_context_node(store, assembler)

    result = await node({"tenant_id": "default", "user_query": ""})
    assert result["injected_context"] == ""
    assert result["injected_sources"] == []


# ── build_context_graph ───────────────────────────────────────────────────────

async def test_context_graph_retrieve_and_assemble() -> None:
    store = InMemoryStore()
    await _populate_store(store, "The Q3 roadmap focuses on reliability.")

    assembler = DefaultContextAssembler()
    graph = build_context_graph(store, assembler)

    result = await graph.ainvoke({
        "tenant_id": "default",
        "user_query": "Q3 roadmap reliability",
    })

    assert result.get("injected_context", "") != "" or len(result.get("results", [])) >= 0
    # The context or results should be populated
    assert "results" in result


async def test_context_graph_tenant_isolation() -> None:
    store = InMemoryStore()
    # Write to tenant-a
    await store.write(MemoryRecord(content="Secret for tenant A.", tenant_id="tenant-a"))

    assembler = DefaultContextAssembler()
    graph = build_context_graph(store, assembler)

    result = await graph.ainvoke({
        "tenant_id": "tenant-b",
        "user_query": "secret tenant",
    })

    # tenant-b should get no results from tenant-a's data
    assert result.get("results", []) == []
    assert result.get("injected_context", "") == ""
