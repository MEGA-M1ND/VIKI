"""VC intelligence read routes (Phase 2).

GET /vc/founders  — list founders, ranked by signal_score desc
GET /vc/deals     — list deals, ranked by last_activity_date desc
GET /vc/signals   — list fund signals, ranked by signal_date desc

These are read-only and tenant-scoped via a ``tenant_id`` query param (the
X-Tenant-ID header enforcement is Phase 3). They depend on the wired
:class:`~app.db.vc_repo.VCRepository`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import get_vc_repository
from app.core.logging import get_logger
from app.db.vc_repo import VCRepository
from app.models.vc import DealOpportunity, FounderProfile, FundSignal

router = APIRouter(prefix="/vc", tags=["vc"])
logger = get_logger(__name__)


@router.get("/founders", response_model=list[FounderProfile])
async def list_founders(
    tenant_id: str = "default",
    min_score: float | None = None,
    stage: str | None = None,
    domain: str | None = None,
    repo: VCRepository = Depends(get_vc_repository),
) -> list[FounderProfile]:
    """List founders for a tenant, sorted by signal_score descending.

    Optional filters: min_score (>=), stage, domain.
    """
    return await repo.list_founders(
        tenant_id=tenant_id, min_score=min_score, stage=stage, domain=domain
    )


@router.get("/deals", response_model=list[DealOpportunity])
async def list_deals(
    tenant_id: str = "default",
    stage: str | None = None,
    since: datetime | None = None,
    repo: VCRepository = Depends(get_vc_repository),
) -> list[DealOpportunity]:
    """List deals for a tenant, sorted by last_activity_date descending.

    Optional filters: stage (deal_stage), since (last_activity_date >=).
    """
    return await repo.list_deals(tenant_id=tenant_id, stage=stage, since=since)


@router.get("/signals", response_model=list[FundSignal])
async def list_signals(
    tenant_id: str = "default",
    founder_id: UUID | None = None,
    since: datetime | None = None,
    repo: VCRepository = Depends(get_vc_repository),
) -> list[FundSignal]:
    """List fund signals for a tenant, sorted by signal_date descending.

    Optional filters: founder_id, since (signal_date >=).
    """
    return await repo.list_signals(
        tenant_id=tenant_id, founder_id=founder_id, since=since
    )
