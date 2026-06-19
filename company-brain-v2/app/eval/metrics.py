"""Result models for the VIKI retrieval evaluation framework.

:class:`EvalResult` captures the per-case metrics; :class:`EvalReport`
aggregates multiple results with summary statistics.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EvalResult(BaseModel):
    """Metrics for a single golden evaluation case.

    Attributes:
        query: The natural-language query that was evaluated.
        precision_at_5: Fraction of the top-5 results that contain at least
            one expected company name (case-insensitive).
        mrr: Mean Reciprocal Rank — 1/rank of the first result containing an
            expected company, or 0.0 if none found in top-5.
        noise_rate: Fraction of the top-5 results that match at least one
            ``must_not_contain`` pattern (lower is better).
        temporal_respected: True if no temporal constraint was given, or if the
            after_date cutoff was successfully extracted and applied.
        latency_ms: Wall-clock latency of the retrieval call in milliseconds.
        hits: Content snippets (first 120 chars) of the top-5 results.
    """

    query: str
    precision_at_5: float
    mrr: float
    noise_rate: float
    temporal_respected: bool
    latency_ms: float
    hits: list[str]


class EvalReport(BaseModel):
    """Aggregated evaluation report across all golden cases.

    Attributes:
        run_at: UTC timestamp when the evaluation ran.
        git_commit: Short git commit hash (or "unknown" if unavailable).
        cases: Per-case results.
        summary: Aggregated statistics — mean_precision_at_5, mean_mrr,
            noise_rate (mean across cases).
    """

    run_at: datetime
    git_commit: str
    cases: list[EvalResult]
    summary: dict  # mean_precision_at_5, mean_mrr, noise_rate
