"""Tests for query_rewriter: graceful degradation and short-query detection."""
from __future__ import annotations

import pytest

from app.core.query_rewriter import rewrite_query
from app.llm.base import LLMProvider

# ---------------------------------------------------------------------------
# Minimal mock LLM implementations
# ---------------------------------------------------------------------------


class _LLMReturnsVariants(LLMProvider):
    """Always returns three newline-separated variant lines."""

    async def chat(
        self, messages: list[dict[str, str]], *, json_mode: bool = False, temperature: float = 0.0
    ) -> str:
        return "variant one\nvariant two\nvariant three"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


class _LLMRaisesError(LLMProvider):
    """Always raises to simulate a broken LLM."""

    async def chat(
        self, messages: list[dict[str, str]], *, json_mode: bool = False, temperature: float = 0.0
    ) -> str:
        raise RuntimeError("simulated LLM failure")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("simulated LLM failure")


class _LLMReturnsEmpty(LLMProvider):
    """Returns an empty string to simulate a blank LLM response."""

    async def chat(
        self, messages: list[dict[str, str]], *, json_mode: bool = False, temperature: float = 0.0
    ) -> str:
        return ""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return []


class _LLMCallTracker(LLMProvider):
    """Records whether chat() was called."""

    def __init__(self) -> None:
        self.called = False

    async def chat(
        self, messages: list[dict[str, str]], *, json_mode: bool = False, temperature: float = 0.0
    ) -> str:
        self.called = True
        return "v1\nv2\nv3"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return []


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_short_query_returns_variants() -> None:
    """Two-word query + working LLM → original plus three variants."""
    llm = _LLMReturnsVariants()
    result = await rewrite_query("Accenture Interview", llm)

    assert result[0] == "Accenture Interview", "Original must be first"
    assert len(result) == 4, "Should have original + 3 variants"
    assert "variant one" in result
    assert "variant two" in result
    assert "variant three" in result


@pytest.mark.asyncio
async def test_long_query_skips_llm() -> None:
    """Query with >4 tokens skips the LLM and returns the original only."""
    tracker = _LLMCallTracker()
    query = "which companies approached me for a job"
    result = await rewrite_query(query, tracker)

    assert result == [query]
    assert not tracker.called, "LLM must not be called for long queries"


@pytest.mark.asyncio
async def test_failing_llm_returns_original() -> None:
    """LLM raises → no exception propagated, returns [original]."""
    llm = _LLMRaisesError()
    result = await rewrite_query("Alice Chen", llm)

    assert result == ["Alice Chen"]


@pytest.mark.asyncio
async def test_empty_llm_response_returns_original() -> None:
    """LLM returns empty string → returns [original]."""
    llm = _LLMReturnsEmpty()
    result = await rewrite_query("short query", llm)

    assert result == ["short query"]


@pytest.mark.asyncio
async def test_original_always_first() -> None:
    """The original query is always the first element in the returned list."""
    llm = _LLMReturnsVariants()
    original = "funding news"
    result = await rewrite_query(original, llm)

    assert result[0] == original


@pytest.mark.asyncio
async def test_exactly_four_tokens_triggers_rewrite() -> None:
    """A query with exactly 4 tokens (the boundary) IS rewritten."""
    tracker = _LLMCallTracker()
    result = await rewrite_query("Alice Chen seed round", tracker)

    assert tracker.called, "4-token query should trigger LLM rewriting"
    assert result[0] == "Alice Chen seed round"


@pytest.mark.asyncio
async def test_five_tokens_skips_rewrite() -> None:
    """A query with 5 tokens is NOT rewritten."""
    tracker = _LLMCallTracker()
    result = await rewrite_query("Alice Chen seed round news", tracker)

    assert not tracker.called, "5-token query should skip LLM"
    assert result == ["Alice Chen seed round news"]
