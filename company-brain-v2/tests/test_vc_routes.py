"""Tests for the VC read routes against the in-memory backend (Phase 2)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.models.vc import FounderProfile, FundSignal

_NOW = datetime(2026, 6, 19, tzinfo=UTC)


def _founder(name: str, score: float) -> FounderProfile:
    return FounderProfile(
        tenant_id="default",
        full_name=name,
        company_name=f"{name} Co",
        stage="seed",
        domain="saas",
        location="SF",
        last_contact_date=_NOW,
        signal_score=score,
    )


def test_vc_founders_route(client) -> None:
    """GET /vc/founders returns founders ordered by signal_score desc."""
    repo = client.app.state.container.vc_repository
    low = _founder("Low", 0.2)
    high = _founder("High", 0.9)
    asyncio.run(repo.upsert_founder(low))
    asyncio.run(repo.upsert_founder(high))

    resp = client.get("/vc/founders", params={"tenant_id": "default"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["full_name"] == "High"
    assert body[1]["full_name"] == "Low"
    assert body[0]["signal_score"] >= body[1]["signal_score"]


def test_vc_signals_route(client) -> None:
    """GET /vc/signals returns signals ordered by signal_date desc."""
    repo = client.app.state.container.vc_repository
    older = FundSignal(
        tenant_id="default",
        signal_type="outreach",
        company_name="Acme",
        signal_date=_NOW - timedelta(days=10),
        raw_text="older",
        confidence=0.5,
    )
    newer = FundSignal(
        tenant_id="default",
        signal_type="term_sheet",
        company_name="Acme",
        signal_date=_NOW - timedelta(days=1),
        raw_text="newer",
        confidence=0.9,
    )
    asyncio.run(repo.add_signal(older))
    asyncio.run(repo.add_signal(newer))

    resp = client.get("/vc/signals", params={"tenant_id": "default"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["raw_text"] == "newer"
    assert body[1]["raw_text"] == "older"
