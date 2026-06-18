"""Ask endpoint — retrieve + generate a conversational answer.

POST /ask  — take a question, retrieve relevant memories, call the LLM,
             return a synthesised answer with sources.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_container, get_llm_provider
from app.core.logging import get_logger
from app.llm.base import LLMProvider
from app.prompts.ask import build_ask_messages
from app.services.container import ServiceContainer

router = APIRouter(tags=["ask"])
logger = get_logger(__name__)

_CONTEXT_MAX_CHARS = 6000


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural-language question.")
    tenant_id: str = Field(default="default")
    limit: int = Field(default=10, ge=1, le=50)


class AskResponse(BaseModel):
    answer: str
    sources: list[str]
    hit_count: int


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

    results = await container.retrieval_service.query(
        tenant_id=req.tenant_id,
        text=req.query,
        limit=req.limit,
    )

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

    messages = build_ask_messages(
        question=req.query,
        context=context,
        hit_count=len(results),
    )
    answer = await llm.chat(messages, temperature=0.2)

    logger.info(
        "api.ask",
        tenant_id=req.tenant_id,
        hits=len(results),
        sources_count=len(sources),
    )

    return AskResponse(answer=answer, sources=sources, hit_count=len(results))
