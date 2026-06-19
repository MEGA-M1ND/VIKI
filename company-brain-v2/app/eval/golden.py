"""Hardcoded golden evaluation cases for VIKI retrieval quality.

Each :class:`EvalCase` specifies a natural-language query, the tenant to
search, companies that must appear in the top-5 results, content patterns
that must NOT appear (noise), and an optional temporal constraint string.

The runner (:mod:`app.eval.runner`) evaluates against these cases and
computes precision@5, MRR, and noise_rate.
"""

from __future__ import annotations

from pydantic import BaseModel


class EvalCase(BaseModel):
    """A single golden evaluation case.

    Attributes:
        query: The natural-language retrieval query.
        tenant_id: The tenant to search within.
        expected_companies: Company names that should appear in the top-5 results
            (case-insensitive match against result content).
        must_not_contain: Strings that must NOT appear in any top-5 result
            (noise rejection).
        temporal_constraint: Optional temporal constraint string (e.g. "last 90 days"),
            which is appended to the query for temporal extraction.
    """

    query: str
    tenant_id: str
    expected_companies: list[str]
    must_not_contain: list[str]
    temporal_constraint: str | None


GOLDEN_CASES: list[EvalCase] = [
    EvalCase(
        query="which companies approached me for a job lately",
        tenant_id="eval_test",
        expected_companies=["Google", "Stripe", "Acme"],
        must_not_contain=["newsletter", "unsubscribe", "digest"],
        temporal_constraint="last 90 days",
    ),
    EvalCase(
        query="founders raising seed round",
        tenant_id="eval_test",
        expected_companies=["Acme AI"],
        must_not_contain=["job alert", "LinkedIn Jobs"],
        temporal_constraint=None,
    ),
    EvalCase(
        query="who followed up with me this week",
        tenant_id="eval_test",
        expected_companies=[],
        must_not_contain=["automated", "noreply", "no-reply"],
        temporal_constraint="last 7 days",
    ),
]
