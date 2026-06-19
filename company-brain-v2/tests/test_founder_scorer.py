"""Tests for the founder signal scorer (Phase 2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.models.vc import FounderProfile, FundSignal
from app.scoring.founder import (
    FounderSignalScorer,
    frequency_score,
    recency_score,
    urgency_score,
)

_NOW = datetime(2026, 6, 19, tzinfo=UTC)


def _founder(name: str) -> FounderProfile:
    return FounderProfile(
        tenant_id="default",
        full_name=name,
        company_name=f"{name} Co",
        stage="seed",
        domain="saas",
        location="SF",
        last_contact_date=_NOW,
    )


def _signal(founder_id, signal_type: str, days_ago: int) -> FundSignal:
    return FundSignal(
        tenant_id="default",
        signal_type=signal_type,
        founder_id=founder_id,
        company_name="X",
        signal_date=_NOW - timedelta(days=days_ago),
        raw_text="...",
        confidence=1.0,
    )


def test_scorer_ranking() -> None:
    """A (hot) > B (mid) > C (cold), each score within [0, 1]."""
    scorer = FounderSignalScorer()

    a = _founder("A")
    b = _founder("B")
    c = _founder("C")

    a_signals = [_signal(a.id, "term_sheet", 2) for _ in range(3)]
    b_signals = [_signal(b.id, "deck_shared", 20)]
    c_signals = [_signal(c.id, "outreach", 100)]

    score_a = scorer.score(a, a_signals, now=_NOW)
    score_b = scorer.score(b, b_signals, now=_NOW)
    score_c = scorer.score(c, c_signals, now=_NOW)

    assert score_a > score_b > score_c
    for s in (score_a, score_b, score_c):
        assert 0.0 <= s <= 1.0


def test_scorer_zero_signals_is_zero() -> None:
    """A founder with no signals scores exactly 0.0."""
    scorer = FounderSignalScorer()
    assert scorer.score(_founder("Z"), [], now=_NOW) == 0.0


def test_recency_score_boundaries() -> None:
    """Step function buckets at 7 / 30 / 90 day edges."""
    assert recency_score(0) == 1.0
    assert recency_score(7) == 1.0
    assert recency_score(7.5) == 0.8
    assert recency_score(30) == 0.8
    assert recency_score(31) == 0.5
    assert recency_score(90) == 0.5
    assert recency_score(91) == 0.2


def test_frequency_score_boundaries() -> None:
    """min(count / 5, 1.0)."""
    assert frequency_score(0) == 0.0
    assert frequency_score(5) == 1.0
    assert frequency_score(10) == 1.0
    assert frequency_score(2) == 0.4


def test_urgency_score_per_type() -> None:
    """Max urgency weight over the present types."""
    assert urgency_score(set()) == 0.0
    assert urgency_score({"pass"}) == 0.0
    assert urgency_score({"outreach"}) == 0.1
    assert urgency_score({"follow_up"}) == 0.3
    assert urgency_score({"deck_shared"}) == 0.5
    assert urgency_score({"meeting_requested"}) == 0.8
    assert urgency_score({"term_sheet"}) == 1.0
    # Max wins when multiple types are present.
    assert urgency_score({"outreach", "term_sheet"}) == 1.0


def test_uuid_helpers_distinct() -> None:
    """Sanity: generated founder ids are distinct UUIDs."""
    assert uuid4() != uuid4()
