"""Founder signal scoring (Phase 2).

Computes a founder's engagement ``signal_score`` in [0, 1] from the dated
:class:`~app.models.vc.FundSignal` records associated with them. The score is a
weighted blend of three components:

    score = recency_score   * 0.40
          + frequency_score  * 0.35
          + urgency_score    * 0.25

Each component is defined in its own helper (see docstrings for the exact
formulae). A founder with zero signals scores ``0.0`` (recency falls into the
">90d" bucket at 0.2, but frequency and urgency are 0, and recency itself is
forced to 0 with no signals — see :meth:`FounderSignalScorer.score`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.vc import FounderProfile, FundSignal

# Component weights (must sum to 1.0).
_RECENCY_WEIGHT = 0.40
_FREQUENCY_WEIGHT = 0.35
_URGENCY_WEIGHT = 0.25

# Urgency weight per signal type (higher = more advanced in the funnel).
_URGENCY_BY_TYPE: dict[str, float] = {
    "term_sheet": 1.0,
    "meeting_requested": 0.8,
    "deck_shared": 0.5,
    "follow_up": 0.3,
    "outreach": 0.1,
    "pass": 0.0,
}

_FREQUENCY_WINDOW_DAYS = 90
_FREQUENCY_TARGET = 5


def recency_score(days_since_last_signal: float) -> float:
    """Score signal recency.

    Formula (step function on days since the most recent signal):
        1.0 if <= 7 days, 0.8 if <= 30, 0.5 if <= 90, else 0.2.

    Args:
        days_since_last_signal: Whole/fractional days since the latest signal.

    Returns:
        A float in {0.2, 0.5, 0.8, 1.0}.
    """
    if days_since_last_signal <= 7:
        return 1.0
    if days_since_last_signal <= 30:
        return 0.8
    if days_since_last_signal <= 90:
        return 0.5
    return 0.2


def frequency_score(signal_count_last_90d: int) -> float:
    """Score signal frequency.

    Formula: ``min(signal_count / 5, 1.0)`` where ``signal_count`` is the number
    of signals within the last 90 days.

    Args:
        signal_count_last_90d: Count of signals in the trailing 90-day window.

    Returns:
        A float in [0.0, 1.0].
    """
    return min(signal_count_last_90d / _FREQUENCY_TARGET, 1.0)


def urgency_score(signal_types_present: set[str]) -> float:
    """Score signal urgency.

    Formula: the maximum urgency weight over the signal types present, where
    term_sheet=1.0, meeting_requested=0.8, deck_shared=0.5, follow_up=0.3,
    outreach=0.1, pass=0.0. Returns 0.0 when no types are present.

    Args:
        signal_types_present: The distinct ``signal_type`` values observed.

    Returns:
        A float in [0.0, 1.0].
    """
    if not signal_types_present:
        return 0.0
    return max(_URGENCY_BY_TYPE.get(t, 0.0) for t in signal_types_present)


class FounderSignalScorer:
    """Compute a founder's engagement score from their fund signals."""

    def score(
        self,
        founder: FounderProfile,
        signals: list[FundSignal],
        *,
        now: datetime | None = None,
    ) -> float:
        """Compute the weighted engagement score for *founder*.

        Args:
            founder: The founder being scored (used for context; the score is
                driven by *signals*).
            signals: The founder's fund signals (any tenant filtering is the
                caller's responsibility).
            now: Reference "current time" (injectable for testing); defaults to
                ``datetime.now(tz=UTC)``.

        Returns:
            A float in [0.0, 1.0]. With no signals, returns 0.0.
        """
        del founder  # Score is derived from signals; founder kept for API clarity.

        if not signals:
            return 0.0

        reference = now or datetime.now(tz=UTC)

        most_recent = max(s.signal_date for s in signals)
        days_since = (reference - most_recent).total_seconds() / 86400.0
        rec = recency_score(days_since)

        window_start = reference - timedelta(days=_FREQUENCY_WINDOW_DAYS)
        count_90d = sum(1 for s in signals if s.signal_date >= window_start)
        freq = frequency_score(count_90d)

        types_present = {s.signal_type for s in signals}
        urg = urgency_score(types_present)

        score = (
            rec * _RECENCY_WEIGHT
            + freq * _FREQUENCY_WEIGHT
            + urg * _URGENCY_WEIGHT
        )
        # Clamp defensively into [0, 1].
        return max(0.0, min(1.0, score))
