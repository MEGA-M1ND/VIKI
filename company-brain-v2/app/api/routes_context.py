"""Context query routes.

POST /context/query — retrieve and format context for a natural-language query
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_container
from app.core.logging import get_logger
from app.services.container import ServiceContainer

router = APIRouter(prefix="/context", tags=["context"])
logger = get_logger(__name__)


class ContextQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    tenant_id: str = Field(default="default")
    limit: int = Field(default=5, ge=1, le=50)
    max_chars: int = Field(default=4000, ge=100, le=20000)


class ContextQueryResponse(BaseModel):
    context: str
    hits: int
    sources: list[str]


@router.post("/query", response_model=ContextQueryResponse)
async def query_context(
    req: ContextQueryRequest,
    container: ServiceContainer = Depends(get_container),
) -> ContextQueryResponse:
    """Retrieve memory and return a formatted context block."""
    context = await container.context_provider.build_context(
        tenant_id=req.tenant_id,
        query=req.query,
        limit=req.limit,
        max_chars=req.max_chars,
    )
    raw_results = await container.context_provider.retrieve(
        tenant_id=req.tenant_id,
        query=req.query,
        limit=req.limit,
    )
    sources = [ref for r in raw_results for ref in r.record.source_refs]

    logger.info("api.context_query", tenant_id=req.tenant_id, hits=len(raw_results))
    return ContextQueryResponse(context=context, hits=len(raw_results), sources=sources)
