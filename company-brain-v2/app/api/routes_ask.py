"""Ask endpoint — retrieve + generate a conversational answer.

POST /ask  — take a question, retrieve relevant memories, call the LLM,
             return a synthesised answer with sources.

Phase 1 additions:
- Temporal query parsing (strips time phrases, adds after_date filter)
- Cross-encoder reranking (degrades gracefully if model unavailable)
- Source-type weight scoring

Phase 2 additions:
- Query rewriting: short queries (<= 4 tokens) expanded to variants via LLM;
  all variants are searched and results unioned by record_id (highest score wins).
- Per-result AskResult in the response (content, score, source_type, age_days,
  source_refs) — enables rich frontend rendering without a second request.
- Score floor: when all results fall below 0.05 after weighting, the
  low_confidence flag is set so the LLM (and UI) can signal uncertainty.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_container, get_llm_provider
from app.core.dedup import deduplicate_by_source
from app.core.logging import get_logger
from app.core.query_rewriter import rewrite_query
from app.core.source_weights import apply_source_weight
from app.core.temporal import extract_temporal_constraint
from app.llm.base import LLMProvider
from app.models.retrieval import RetrievalResult, ScoredFact
from app.prompts.ask import build_ask_messages
from app.services.container import ServiceContainer

router = APIRouter(tags=["ask"])
logger = get_logger(__name__)

_CONTEXT_MAX_CHARS = 6000
_SCORE_FLOOR = 0.05  # absolute floor for post-weight scores


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural-language question.")
    tenant_id: str = Field(default="default")
    limit: int = Field(default=10, ge=1, le=50)


class AskResult(BaseModel):
    """Per-result detail for rich frontend rendering."""

    content: str
    score: float
    source_type: str | None = None
    age_days: int | None = None
    source_refs: list[str] = Field(default_factory=list)


class AskResponse(BaseModel):
    answer: str
    sources: list[str]
    hit_count: int
    results: list[AskResult] = Field(default_factory=list)
    low_confidence: bool = False


@router.post("/ask", response_model=AskResponse)
async def ask(
    req: AskRequest,
    container: ServiceContainer = Depends(get_container),
    llm: LLMProvider | None = Depends(get_llm_provider),
) -> AskResponse:
    """Retrieve relevant memories and return a synthesised LLM answer."""
    if llm is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "LLM is not configured. Set CB_LLM_API_KEY in the environment "
                "and restart the service."
            ),
        )

    # 1. Parse temporal constraint from the query
    cleaned_query, after_date = extract_temporal_constraint(req.query)

    # 1b. Query rewriting for short/entity queries (<=4 tokens)
    #     llm is guaranteed non-None by the guard above
    queries_to_run = await rewrite_query(cleaned_query, llm)

    # 2. Retrieve for all query variants; union by record_id keeping highest score
    filters: dict[str, object] = {}
    if after_date:
        filters["after_date"] = after_date

    record_map: dict[str, RetrievalResult] = {}
    for q_text in queries_to_run:
        variant_results = await container.retrieval_service.query(
            tenant_id=req.tenant_id,
            text=q_text,
            limit=req.limit,
            filters=filters,
        )
        for r in variant_results:
            existing = record_map.get(r.record.id)
            if existing is None or r.score > existing.score:
                record_map[r.record.id] = r

    results: list[RetrievalResult] = sorted(
        record_map.values(), key=lambda r: r.score, reverse=True
    )[: req.limit]

    # 3. Convert to ScoredFact for dedup + optional reranking
    scored: list[ScoredFact] = [
        ScoredFact(
            record=r.record,
            score=r.score,
            source_doc_id=r.record.source_doc_id,
        )
        for r in results
    ]

    # 3a. Deduplicate by source (backend-agnostic — applies to both in-memory and pgvector)
    scored = deduplicate_by_source(scored)

    # 3b. Optionally rerank with cross-encoder
    reranker = container.reranker
    if reranker is not None and scored:
        top_k = getattr(container.settings, "reranker_top_k", req.limit)
        scored = reranker.rerank(cleaned_query, scored, top_k=top_k)

    results = [sf.to_retrieval_result() for sf in scored]

    # 4. Apply source-type weights and re-sort
    weighted_results: list[RetrievalResult] = []
    for r in results:
        hint = getattr(r.record, "source_type_hint", None) or r.record.metadata.get(
            "source_type_hint"
        )
        new_score = apply_source_weight(r.score, hint)
        weighted_results.append(
            RetrievalResult(
                record=r.record,
                score=min(1.0, new_score),
                rationale=r.rationale,
            )
        )
    weighted_results.sort(key=lambda r: r.score, reverse=True)
    results = weighted_results

    # 4b. Score floor: flag low-confidence result sets
    #     When the top result falls below the absolute floor, the retrieval
    #     backend found nothing with meaningful relevance for this query.
    #     We still pass results to the LLM (it handles the "I don't know" case)
    #     but surface the flag so the UI can show appropriate messaging.
    top_score = results[0].score if results else 0.0
    low_confidence = top_score < _SCORE_FLOOR

    # 5. Build context string for LLM
    now = datetime.now(tz=UTC)
    context_lines: list[str] = []
    budget = _CONTEXT_MAX_CHARS
    for i, result in enumerate(results, start=1):
        line = f"[{i}] {result.record.content}"
        if len(line) > budget:
            break
        context_lines.append(line)
        budget -= len(line) + 1
    context = "\n".join(context_lines)

    seen: set[str] = set()
    sources: list[str] = []
    for result in results:
        for ref in result.record.source_refs:
            if ref not in seen:
                seen.add(ref)
                sources.append(ref)

    # Build per-result detail for the response
    ask_results: list[AskResult] = []
    for result in results:
        hint = (
            getattr(result.record, "source_type_hint", None)
            or result.record.metadata.get("source_type_hint")
        )
        age_days: int | None = None
        if result.record.created_at is not None:
            delta = now - result.record.created_at
            age_days = max(0, delta.days)
        ask_results.append(
            AskResult(
                content=result.record.content,
                score=result.score,
                source_type=hint,
                age_days=age_days,
                source_refs=list(result.record.source_refs),
            )
        )

    messages = build_ask_messages(
        question=req.query,
        context=context,
        hit_count=len(results),
    )
    answer = await llm.chat(messages, temperature=0.2)

    logger.info(
        "api.ask",
        tenant_id=req.tenant_id,
        original_query=req.query,
        cleaned_query=cleaned_query,
        queries_run=len(queries_to_run),
        after_date=str(after_date) if after_date else None,
        hits=len(results),
        sources_count=len(sources),
        low_confidence=low_confidence,
    )

    return AskResponse(
        answer=answer,
        sources=sources,
        hit_count=len(results),
        results=ask_results,
        low_confidence=low_confidence,
    )
