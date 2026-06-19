"""VC intelligence read routes (Phase 2 + 3).

GET /vc/founders  — list founders, ranked by signal_score desc
GET /vc/deals     — list deals, ranked by last_activity_date desc
GET /vc/signals   — list fund signals, ranked by signal_date desc

These are read-only and tenant-scoped. Phase 3 adds enforcement via
:func:`~app.api.deps.require_tenant_id`: all three routes require either the
``X-Tenant-ID`` header or a ``tenant_id`` query parameter.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import get_vc_repository, require_tenant_id
from app.core.logging import get_logger
from app.db.vc_repo import VCRepository
from app.models.vc import DealOpportunity, FounderProfile, FundSignal

router = APIRouter(prefix="/vc", tags=["vc"])
logger = get_logger(__name__)


@router.get("/founders", response_model=list[FounderProfile])
async def list_founders(
    tenant_id: str = Depends(require_tenant_id),
    min_score: float | None = None,
    stage: str | None = None,
    domain: str | None = None,
    repo: VCRepository = Depends(get_vc_repository),
) -> list[FounderProfile]:
    """List founders for a tenant, sorted by signal_score descending.

    Optional filters: min_score (>=), stage, domain.
    Requires X-Tenant-ID header or tenant_id query param.
    """
    return await repo.list_founders(
        tenant_id=tenant_id, min_score=min_score, stage=stage, domain=domain
    )


@router.get("/deals", response_model=list[DealOpportunity])
async def list_deals(
    tenant_id: str = Depends(require_tenant_id),
    stage: str | None = None,
    since: datetime | None = None,
    repo: VCRepository = Depends(get_vc_repository),
) -> list[DealOpportunity]:
    """List deals for a tenant, sorted by last_activity_date descending.

    Optional filters: stage (deal_stage), since (last_activity_date >=).
    Requires X-Tenant-ID header or tenant_id query param.
    """
    return await repo.list_deals(tenant_id=tenant_id, stage=stage, since=since)


@router.get("/signals", response_model=list[FundSignal])
async def list_signals(
    tenant_id: str = Depends(require_tenant_id),
    founder_id: UUID | None = None,
    since: datetime | None = None,
    repo: VCRepository = Depends(get_vc_repository),
) -> list[FundSignal]:
    """List fund signals for a tenant, sorted by signal_date descending.

    Optional filters: founder_id, since (signal_date >=).
    Requires X-Tenant-ID header or tenant_id query param.
    """
    return await repo.list_signals(
        tenant_id=tenant_id, founder_id=founder_id, since=since
    )
