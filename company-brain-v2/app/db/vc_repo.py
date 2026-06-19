"""VC repository abstraction (Phase 2).

Defines the :class:`VCRepository` ABC that the VC routes and scorer depend on,
plus an :class:`InMemoryVCRepository` used by tests and the in-memory backend.
The SQL implementation lives in :mod:`app.db.vc_repo_sql`.

All operations are tenant-scoped. Filtering and sorting semantics are part of
the contract (documented per method) so the in-memory and SQL implementations
behave identically.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.models.vc import DealOpportunity, FounderProfile, FundSignal


class VCRepository(ABC):
    """Abstract persistence boundary for the VC intelligence layer."""

    @abstractmethod
    async def upsert_founder(self, founder: FounderProfile) -> FounderProfile:
        """Insert or update a founder by id. Returns the stored founder."""
        raise NotImplementedError

    @abstractmethod
    async def get_founder(
        self, *, tenant_id: str, founder_id: UUID
    ) -> FounderProfile | None:
        """Fetch a founder by id within a tenant, or None if absent."""
        raise NotImplementedError

    @abstractmethod
    async def list_founders(
        self,
        *,
        tenant_id: str,
        min_score: float | None = None,
        stage: str | None = None,
        domain: str | None = None,
    ) -> list[FounderProfile]:
        """List founders for a tenant, sorted by signal_score DESC.

        Optional filters: min_score (>=), stage (==), domain (==).
        """
        raise NotImplementedError

    @abstractmethod
    async def upsert_deal(self, deal: DealOpportunity) -> DealOpportunity:
        """Insert or update a deal by id. Returns the stored deal."""
        raise NotImplementedError

    @abstractmethod
    async def list_deals(
        self,
        *,
        tenant_id: str,
        stage: str | None = None,
        since: datetime | None = None,
    ) -> list[DealOpportunity]:
        """List deals for a tenant, sorted by last_activity_date DESC.

        Optional filters: stage (== deal_stage), since (last_activity_date >=).
        """
        raise NotImplementedError

    @abstractmethod
    async def add_signal(self, signal: FundSignal) -> FundSignal:
        """Append a fund signal. Returns the stored signal."""
        raise NotImplementedError

    @abstractmethod
    async def list_signals(
        self,
        *,
        tenant_id: str,
        founder_id: UUID | None = None,
        since: datetime | None = None,
    ) -> list[FundSignal]:
        """List signals for a tenant, sorted by signal_date DESC.

        Optional filters: founder_id (==), since (signal_date >=).
        """
        raise NotImplementedError


class InMemoryVCRepository(VCRepository):
    """In-memory VC repository (per-tenant dicts/lists).

    Filtering and sorting are applied in Python to mirror the SQL contract.
    Intended for tests and the in-memory backend.
    """

    def __init__(self) -> None:
        # tenant_id -> {founder_id -> FounderProfile}
        self._founders: dict[str, dict[UUID, FounderProfile]] = {}
        # tenant_id -> {deal_id -> DealOpportunity}
        self._deals: dict[str, dict[UUID, DealOpportunity]] = {}
        # tenant_id -> [FundSignal]
        self._signals: dict[str, list[FundSignal]] = {}

    async def upsert_founder(self, founder: FounderProfile) -> FounderProfile:
        self._founders.setdefault(founder.tenant_id, {})[founder.id] = founder
        return founder

    async def get_founder(
        self, *, tenant_id: str, founder_id: UUID
    ) -> FounderProfile | None:
        return self._founders.get(tenant_id, {}).get(founder_id)

    async def list_founders(
        self,
        *,
        tenant_id: str,
        min_score: float | None = None,
        stage: str | None = None,
        domain: str | None = None,
    ) -> list[FounderProfile]:
        items = list(self._founders.get(tenant_id, {}).values())
        if min_score is not None:
            items = [f for f in items if f.signal_score >= min_score]
        if stage is not None:
            items = [f for f in items if f.stage == stage]
        if domain is not None:
            items = [f for f in items if f.domain == domain]
        items.sort(key=lambda f: f.signal_score, reverse=True)
        return items

    async def upsert_deal(self, deal: DealOpportunity) -> DealOpportunity:
        self._deals.setdefault(deal.tenant_id, {})[deal.id] = deal
        return deal

    async def list_deals(
        self,
        *,
        tenant_id: str,
        stage: str | None = None,
        since: datetime | None = None,
    ) -> list[DealOpportunity]:
        items = list(self._deals.get(tenant_id, {}).values())
        if stage is not None:
            items = [d for d in items if d.deal_stage == stage]
        if since is not None:
            items = [d for d in items if d.last_activity_date >= since]
        items.sort(key=lambda d: d.last_activity_date, reverse=True)
        return items

    async def add_signal(self, signal: FundSignal) -> FundSignal:
        self._signals.setdefault(signal.tenant_id, []).append(signal)
        return signal

    async def list_signals(
        self,
        *,
        tenant_id: str,
        founder_id: UUID | None = None,
        since: datetime | None = None,
    ) -> list[FundSignal]:
        items = list(self._signals.get(tenant_id, []))
        if founder_id is not None:
            items = [s for s in items if s.founder_id == founder_id]
        if since is not None:
            items = [s for s in items if s.signal_date >= since]
        items.sort(key=lambda s: s.signal_date, reverse=True)
        return items
