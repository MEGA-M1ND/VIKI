"""Memory CRUD routes.

GET    /memories           — list memory records for a tenant
GET    /memories/{id}      — fetch a single record
DELETE /memories/{id}      — delete a record
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import get_container
from app.core.logging import get_logger
from app.models.memory import MemoryRecord
from app.models.retrieval import RetrievalQuery
from app.services.container import ServiceContainer

router = APIRouter(prefix="/memories", tags=["memory"])
logger = get_logger(__name__)


class MemoryListResponse(BaseModel):
    items: list[MemoryRecord]
    total: int


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    tenant_id: str = "default",
    query: str = "",
    limit: int = 20,
    container: ServiceContainer = Depends(get_container),
) -> MemoryListResponse:
    """Return memory records for a tenant, optionally filtered by query."""
    q = RetrievalQuery(tenant_id=tenant_id, text=query or " ", limit=limit)
    results = await container.memory_store.query(q)
    records = [r.record for r in results]
    return MemoryListResponse(items=records, total=len(records))


@router.get("/{record_id}", response_model=MemoryRecord)
async def get_memory(
    record_id: str,
    tenant_id: str = "default",
    container: ServiceContainer = Depends(get_container),
) -> MemoryRecord:
    """Fetch a single memory record by id."""
    record = await container.memory_store.get(tenant_id=tenant_id, record_id=record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory record '{record_id}' not found for tenant '{tenant_id}'.",
        )
    return record


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    record_id: str,
    tenant_id: str = "default",
    container: ServiceContainer = Depends(get_container),
) -> None:
    """Delete a memory record."""
    deleted = await container.memory_store.delete(tenant_id=tenant_id, record_id=record_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory record '{record_id}' not found for tenant '{tenant_id}'.",
        )
    logger.info("api.memory_deleted", record_id=record_id, tenant_id=tenant_id)
