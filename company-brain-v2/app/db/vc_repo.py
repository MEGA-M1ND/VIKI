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
from app.utils.ids import utcnow


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

    @abstractmethod
    async def upsert_founder_from_signal(
        self, *, tenant_id: str, vc_fact: dict, source_doc_id: str
    ) -> FounderProfile:
        """Create or update a FounderProfile from a parsed VC extraction fact dict.

        Matches on (tenant_id, company_name). If not found, creates a new profile
        with full_name from entities.person, company_name from entities.company,
        stage from entities.stage (default "idea"), domain="" initially, location="",
        last_contact_date = signal_date or now, raw_signals=[fact.statement],
        source_doc_ids=[source_doc_id].

        If found, appends fact.statement to raw_signals (if not already present),
        updates last_contact_date if signal_date is more recent, appends source_doc_id
        to source_doc_ids if not present.

        Args:
            tenant_id: Owning tenant.
            vc_fact: A parsed VC extraction fact dict with keys: fact_type,
                statement, entities (dict), confidence, signal_date.
            source_doc_id: The source document id to associate.

        Returns:
            The inserted or updated :class:`FounderProfile`.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_signals_for_founder(
        self, *, tenant_id: str, founder_id: UUID
    ) -> list[FundSignal]:
        """Return all signals for this founder, sorted by signal_date desc.

        Args:
            tenant_id: Owning tenant.
            founder_id: The founder whose signals to retrieve.

        Returns:
            List of :class:`FundSignal` sorted by signal_date descending.
        """
        raise NotImplementedError

    @abstractmethod
    async def update_founder_score(
        self, *, tenant_id: str, founder_id: UUID, score: float
    ) -> None:
        """Update signal_score on a FounderProfile.

        Args:
            tenant_id: Owning tenant.
            founder_id: The founder to update.
            score: The new signal score in [0, 1].
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

    async def upsert_founder_from_signal(
        self, *, tenant_id: str, vc_fact: dict, source_doc_id: str
    ) -> FounderProfile:
        """Create or update a FounderProfile from a parsed VC extraction fact dict."""
        from datetime import UTC

        entities = vc_fact.get("entities") or {}
        company_name: str = entities.get("company") or "unknown"
        person_name: str = entities.get("person") or ""
        stage: str = entities.get("stage") or "idea"
        statement: str = vc_fact.get("statement") or ""
        signal_date_str: str | None = vc_fact.get("signal_date")

        # Parse signal_date
        signal_date: datetime | None = None
        if signal_date_str:
            try:
                dt = datetime.fromisoformat(signal_date_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                signal_date = dt
            except (ValueError, AttributeError):
                signal_date = None

        contact_date = signal_date or utcnow()

        # Validate stage literal
        valid_stages = {"idea", "pre-seed", "seed", "series-a", "series-b+"}
        if stage not in valid_stages:
            stage = "idea"

        # Match on (tenant_id, company_name)
        existing: FounderProfile | None = None
        for f in self._founders.get(tenant_id, {}).values():
            if f.company_name == company_name:
                existing = f
                break

        if existing is None:
            founder = FounderProfile(
                tenant_id=tenant_id,
                full_name=person_name,
                company_name=company_name,
                stage=stage,  # type: ignore[arg-type]
                domain="",
                location="",
                last_contact_date=contact_date,
                raw_signals=[statement] if statement else [],
                source_doc_ids=[source_doc_id],
            )
            self._founders.setdefault(tenant_id, {})[founder.id] = founder
            return founder

        # Update existing founder
        updated_signals = list(existing.raw_signals)
        if statement and statement not in updated_signals:
            updated_signals.append(statement)

        updated_source_ids = list(existing.source_doc_ids)
        if source_doc_id not in updated_source_ids:
            updated_source_ids.append(source_doc_id)

        updated_contact = existing.last_contact_date
        if signal_date and signal_date > updated_contact:
            updated_contact = signal_date

        updated = existing.model_copy(update={
            "raw_signals": updated_signals,
            "source_doc_ids": updated_source_ids,
            "last_contact_date": updated_contact,
        })
        self._founders[tenant_id][existing.id] = updated
        return updated

    async def get_signals_for_founder(
        self, *, tenant_id: str, founder_id: UUID
    ) -> list[FundSignal]:
        """Return all signals for this founder, sorted by signal_date desc."""
        items = [
            s for s in self._signals.get(tenant_id, [])
            if s.founder_id == founder_id
        ]
        items.sort(key=lambda s: s.signal_date, reverse=True)
        return items

    async def update_founder_score(
        self, *, tenant_id: str, founder_id: UUID, score: float
    ) -> None:
        """Update signal_score on a FounderProfile."""
        tenant_map = self._founders.get(tenant_id, {})
        if founder_id in tenant_map:
            existing = tenant_map[founder_id]
            tenant_map[founder_id] = existing.model_copy(update={"signal_score": score})
