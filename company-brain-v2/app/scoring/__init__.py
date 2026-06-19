"""Scoring package for the VC intelligence layer (Phase 2).

Currently exposes :class:`~app.scoring.founder.FounderSignalScorer`, which
ranks founders by engagement using recency, frequency, and urgency of their
recorded fund signals.
"""

from __future__ import annotations

from app.scoring.founder import FounderSignalScorer

__all__ = ["FounderSignalScorer"]
