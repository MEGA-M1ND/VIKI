"""SQL implementation of the VC repository (Phase 2).

Uses ``session_scope`` + parameterized ``text()`` SQL against the founders,
deal_opportunities, and fund_signals tables.

Phase 1 lessons applied here:
- JSONB params are bound as ``json.dumps(...)`` and cast with ``CAST(:p AS jsonb)``.
- UUID params are bound as ``str(uuid)`` (asyncpg + raw text needs explicit text);
  PostgreSQL implicitly coerces the text literal to uuid in equality/insert.
- UUID columns read back as Python ``uuid.UUID`` are passed straight to Pydantic.
"""

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import text

from app.core.logging import get_logger
from app.db.engine import session_scope
from app.db.vc_repo import VCRepository
from app.models.vc import DealOpportunity, FounderProfile, FundSignal
from app.utils.ids import utcnow

logger = get_logger(__name__)


class SqlVCRepository(VCRepository):
    """PostgreSQL-backed VC repository.

    Args:
        dsn: asyncpg-compatible PostgreSQL DSN.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    async def upsert_founder(self, founder: FounderProfile) -> FounderProfile:
        async with session_scope(self._dsn) as session:
            await session.execute(
                text("""
                    INSERT INTO founders (
                        id, tenant_id, full_name, company_name, stage, domain,
                        location, last_contact_date, signal_score, raw_signals,
                        source_doc_ids, created_at, updated_at
                    ) VALUES (
                        CAST(:id AS uuid), :tenant_id, :full_name, :company_name,
                        :stage, :domain, :location, :last_contact_date,
                        :signal_score, CAST(:raw_signals AS jsonb),
                        CAST(:source_doc_ids AS jsonb), :created_at, :updated_at
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        tenant_id = EXCLUDED.tenant_id,
                        full_name = EXCLUDED.full_name,
                        company_name = EXCLUDED.company_name,
                        stage = EXCLUDED.stage,
                        domain = EXCLUDED.domain,
                        location = EXCLUDED.location,
                        last_contact_date = EXCLUDED.last_contact_date,
                        signal_score = EXCLUDED.signal_score,
                        raw_signals = EXCLUDED.raw_signals,
                        source_doc_ids = EXCLUDED.source_doc_ids,
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    "id": str(founder.id),
                    "tenant_id": founder.tenant_id,
                    "full_name": founder.full_name,
                    "company_name": founder.company_name,
                    "stage": founder.stage,
                    "domain": founder.domain,
                    "location": founder.location,
                    "last_contact_date": founder.last_contact_date,
                    "signal_score": founder.signal_score,
                    "raw_signals": json.dumps(founder.raw_signals),
                    "source_doc_ids": json.dumps(founder.source_doc_ids),
                    "created_at": founder.created_at,
                    "updated_at": utcnow(),
                },
            )
        logger.info("vc.upsert_founder", tenant=founder.tenant_id, founder_id=str(founder.id))
        return founder

    async def get_founder(
        self, *, tenant_id: str, founder_id: UUID
    ) -> FounderProfile | None:
        async with session_scope(self._dsn) as session:
            row = (
                await session.execute(
                    text("""
                        SELECT id, tenant_id, full_name, company_name, stage, domain,
                               location, last_contact_date, signal_score, raw_signals,
                               source_doc_ids, created_at, updated_at
                        FROM founders
                        WHERE id = CAST(:id AS uuid) AND tenant_id = :tenant_id
                    """),
                    {"id": str(founder_id), "tenant_id": tenant_id},
                )
            ).fetchone()
        if row is None:
            return None
        return _row_to_founder(row)

    async def list_founders(
        self,
        *,
        tenant_id: str,
        min_score: float | None = None,
        stage: str | None = None,
        domain: str | None = None,
    ) -> list[FounderProfile]:
        clauses = ["tenant_id = :tenant_id"]
        params: dict[str, object] = {"tenant_id": tenant_id}
        if min_score is not None:
            clauses.append("signal_score >= :min_score")
            params["min_score"] = min_score
        if stage is not None:
            clauses.append("stage = :stage")
            params["stage"] = stage
        if domain is not None:
            clauses.append("domain = :domain")
            params["domain"] = domain
        where = " AND ".join(clauses)
        async with session_scope(self._dsn) as session:
            rows = (
                await session.execute(
                    text(f"""
                        SELECT id, tenant_id, full_name, company_name, stage, domain,
                               location, last_contact_date, signal_score, raw_signals,
                               source_doc_ids, created_at, updated_at
                        FROM founders
                        WHERE {where}
                        ORDER BY signal_score DESC
                    """),
                    params,
                )
            ).fetchall()
        return [_row_to_founder(r) for r in rows]

    async def upsert_deal(self, deal: DealOpportunity) -> DealOpportunity:
        async with session_scope(self._dsn) as session:
            await session.execute(
                text("""
                    INSERT INTO deal_opportunities (
                        id, tenant_id, founder_id, company_name, deal_stage,
                        raise_amount_usd, last_activity_date, next_action, source_doc_ids
                    ) VALUES (
                        CAST(:id AS uuid), :tenant_id, CAST(:founder_id AS uuid),
                        :company_name, :deal_stage, :raise_amount_usd,
                        :last_activity_date, :next_action, CAST(:source_doc_ids AS jsonb)
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        tenant_id = EXCLUDED.tenant_id,
                        founder_id = EXCLUDED.founder_id,
                        company_name = EXCLUDED.company_name,
                        deal_stage = EXCLUDED.deal_stage,
                        raise_amount_usd = EXCLUDED.raise_amount_usd,
                        last_activity_date = EXCLUDED.last_activity_date,
                        next_action = EXCLUDED.next_action,
                        source_doc_ids = EXCLUDED.source_doc_ids
                """),
                {
                    "id": str(deal.id),
                    "tenant_id": deal.tenant_id,
                    "founder_id": str(deal.founder_id),
                    "company_name": deal.company_name,
                    "deal_stage": deal.deal_stage,
                    "raise_amount_usd": deal.raise_amount_usd,
                    "last_activity_date": deal.last_activity_date,
                    "next_action": deal.next_action,
                    "source_doc_ids": json.dumps(deal.source_doc_ids),
                },
            )
        logger.info("vc.upsert_deal", tenant=deal.tenant_id, deal_id=str(deal.id))
        return deal

    async def list_deals(
        self,
        *,
        tenant_id: str,
        stage: str | None = None,
        since: datetime | None = None,
    ) -> list[DealOpportunity]:
        clauses = ["tenant_id = :tenant_id"]
        params: dict[str, object] = {"tenant_id": tenant_id}
        if stage is not None:
            clauses.append("deal_stage = :stage")
            params["stage"] = stage
        if since is not None:
            clauses.append("last_activity_date >= :since")
            params["since"] = since
        where = " AND ".join(clauses)
        async with session_scope(self._dsn) as session:
            rows = (
                await session.execute(
                    text(f"""
                        SELECT id, tenant_id, founder_id, company_name, deal_stage,
                               raise_amount_usd, last_activity_date, next_action,
                               source_doc_ids
                        FROM deal_opportunities
                        WHERE {where}
                        ORDER BY last_activity_date DESC
                    """),
                    params,
                )
            ).fetchall()
        return [_row_to_deal(r) for r in rows]

    async def add_signal(self, signal: FundSignal) -> FundSignal:
        async with session_scope(self._dsn) as session:
            await session.execute(
                text("""
                    INSERT INTO fund_signals (
                        id, tenant_id, signal_type, founder_id, company_name,
                        signal_date, raw_text, confidence
                    ) VALUES (
                        CAST(:id AS uuid), :tenant_id, :signal_type,
                        CAST(:founder_id AS uuid), :company_name, :signal_date,
                        :raw_text, :confidence
                    )
                """),
                {
                    "id": str(signal.id),
                    "tenant_id": signal.tenant_id,
                    "signal_type": signal.signal_type,
                    "founder_id": str(signal.founder_id) if signal.founder_id else None,
                    "company_name": signal.company_name,
                    "signal_date": signal.signal_date,
                    "raw_text": signal.raw_text,
                    "confidence": signal.confidence,
                },
            )
        logger.info("vc.add_signal", tenant=signal.tenant_id, signal_id=str(signal.id))
        return signal

    async def list_signals(
        self,
        *,
        tenant_id: str,
        founder_id: UUID | None = None,
        since: datetime | None = None,
    ) -> list[FundSignal]:
        clauses = ["tenant_id = :tenant_id"]
        params: dict[str, object] = {"tenant_id": tenant_id}
        if founder_id is not None:
            clauses.append("founder_id = CAST(:founder_id AS uuid)")
            params["founder_id"] = str(founder_id)
        if since is not None:
            clauses.append("signal_date >= :since")
            params["since"] = since
        where = " AND ".join(clauses)
        async with session_scope(self._dsn) as session:
            rows = (
                await session.execute(
                    text(f"""
                        SELECT id, tenant_id, signal_type, founder_id, company_name,
                               signal_date, raw_text, confidence
                        FROM fund_signals
                        WHERE {where}
                        ORDER BY signal_date DESC
                    """),
                    params,
                )
            ).fetchall()
        return [_row_to_signal(r) for r in rows]


def _as_uuid(value: object) -> UUID | None:
    """Coerce a DB value (UUID or str) into a uuid.UUID, or None."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _row_to_founder(row) -> FounderProfile:
    """Build a FounderProfile from a founders row."""
    return FounderProfile(
        id=_as_uuid(row.id),
        tenant_id=row.tenant_id,
        full_name=row.full_name,
        company_name=row.company_name,
        stage=row.stage,
        domain=row.domain,
        location=row.location,
        last_contact_date=row.last_contact_date,
        signal_score=row.signal_score,
        raw_signals=row.raw_signals or [],
        source_doc_ids=row.source_doc_ids or [],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _row_to_deal(row) -> DealOpportunity:
    """Build a DealOpportunity from a deal_opportunities row."""
    return DealOpportunity(
        id=_as_uuid(row.id),
        tenant_id=row.tenant_id,
        founder_id=_as_uuid(row.founder_id),
        company_name=row.company_name,
        deal_stage=row.deal_stage,
        raise_amount_usd=row.raise_amount_usd,
        last_activity_date=row.last_activity_date,
        next_action=row.next_action,
        source_doc_ids=row.source_doc_ids or [],
    )


def _row_to_signal(row) -> FundSignal:
    """Build a FundSignal from a fund_signals row."""
    return FundSignal(
        id=_as_uuid(row.id),
        tenant_id=row.tenant_id,
        signal_type=row.signal_type,
        founder_id=_as_uuid(row.founder_id),
        company_name=row.company_name,
        signal_date=row.signal_date,
        raw_text=row.raw_text,
        confidence=row.confidence,
    )
