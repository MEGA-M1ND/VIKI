"""Populate an in-memory store and VC repository with deterministic eval fixtures.

Idempotent: each fixture uses a fixed ``id`` so repeated calls are no-ops for
already-present records.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.eval.fixtures import FACT_FIXTURES, FOUNDER_FIXTURES
from app.memory.base import MemoryStore
from app.models.memory import MemoryRecord


async def seed_eval_store(
    store: MemoryStore,
    vc_repo=None,
    tenant_id: str = "eval_test",
) -> None:
    """Write fixture records into *store* and optionally *vc_repo*.

    Args:
        store: The memory store to populate.
        vc_repo: Optional VCRepository; if supplied, founder fixtures are upserted
            with associated FundSignal objects so FounderSignalScorer produces
            non-zero scores.
        tenant_id: Tenant partition to write into (default ``"eval_test"``).
    """
    now = datetime.now(tz=UTC)

    for fixture in FACT_FIXTURES:
        existing = await store.get(tenant_id=tenant_id, record_id=fixture["id"])
        if existing is not None:
            continue
        created_at = now - timedelta(days=fixture["age_days"])
        record = MemoryRecord(
            id=fixture["id"],
            tenant_id=tenant_id,
            content=fixture["content"],
            source_type_hint=fixture.get("source_type_hint"),
            metadata=fixture.get("metadata") or {},
            created_at=created_at,
            updated_at=created_at,
        )
        await store.write(record)

    if vc_repo is not None:
        from app.models.vc import FounderProfile, FundSignal

        existing_founders = await vc_repo.list_founders(tenant_id=tenant_id)
        existing_companies = {f.company_name for f in existing_founders}

        for f in FOUNDER_FIXTURES:
            entities = f["entities"]
            company = entities.get("company", "unknown")
            if company in existing_companies:
                continue

            signal_date = now - timedelta(days=f["signal_age_days"])
            founder = FounderProfile(
                tenant_id=tenant_id,
                full_name=entities.get("person", ""),
                company_name=company,
                stage=entities.get("stage", "idea"),  # type: ignore[arg-type]
                domain=f.get("domain", ""),
                location="",
                last_contact_date=signal_date,
                raw_signals=[f["statement"]],
                source_doc_ids=[f"fixture_founder_{company.lower().replace(' ', '_')}"],
            )
            created = await vc_repo.upsert_founder(founder)
            existing_companies.add(company)

            # Create a FundSignal so FounderSignalScorer returns a non-zero score
            signal_type = f.get("signal_type", "outreach")
            signal = FundSignal(
                tenant_id=tenant_id,
                signal_type=signal_type,  # type: ignore[arg-type]
                founder_id=created.id,
                company_name=company,
                signal_date=signal_date,
                raw_text=f["statement"],
                confidence=0.9,
            )
            await vc_repo.add_signal(signal)
