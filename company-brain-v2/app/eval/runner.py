"""Retrieval evaluation runner.

Executes the golden evaluation cases against an in-memory store (or any
:class:`~app.memory.base.MemoryStore`) and produces an :class:`EvalReport`.

Can be run as a CLI script::

    python -m app.eval.runner --output eval_results/

The ``--output`` directory receives a JSON file named by run timestamp.
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from app.eval.golden import GOLDEN_CASES, EvalCase
from app.eval.metrics import EvalReport, EvalResult
from app.eval.seed import seed_eval_store  # noqa: F401 — re-exported for backward compat
from app.memory.base import MemoryStore
from app.models.retrieval import RetrievalQuery


def _get_git_commit() -> str:
    """Return short git commit hash, or 'unknown' if git is unavailable.

    Returns:
        A 7-character short SHA or ``"unknown"``.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


async def run_eval(store: MemoryStore, cases: list[EvalCase]) -> EvalReport:
    """Run all evaluation cases against the provided store.

    For each case: extracts temporal constraints, issues a retrieval query,
    measures latency, and computes precision@5, MRR, and noise_rate.

    Args:
        store: The memory store to query.
        cases: List of golden evaluation cases.

    Returns:
        An :class:`EvalReport` with per-case metrics and aggregate summary.
    """
    from app.core.temporal import extract_temporal_constraint

    results: list[EvalResult] = []

    for case in cases:
        # Build the combined query string for temporal extraction
        combined_query = case.query
        if case.temporal_constraint:
            combined_query = f"{case.query} {case.temporal_constraint}"

        _cleaned, after_date = extract_temporal_constraint(combined_query)

        filters: dict = {}
        if after_date is not None:
            filters["after_date"] = after_date

        q = RetrievalQuery(
            tenant_id=case.tenant_id,
            text=case.query,
            limit=5,
            filters=filters,
        )

        t0 = time.monotonic()
        retrieved = await store.query(q)
        latency_ms = (time.monotonic() - t0) * 1000.0

        top5_contents = [r.record.content for r in retrieved[:5]]
        expected = case.expected_companies
        noise_patterns = case.must_not_contain

        # Precision@5: fraction of top-5 that mention an expected company
        def _has_expected(content: str, _exp: list[str] = expected) -> bool:
            lower = content.lower()
            return any(c.lower() in lower for c in _exp)

        if expected:
            hits_count = sum(1 for c in top5_contents if _has_expected(c))
            precision = hits_count / max(len(top5_contents), 1) if top5_contents else 0.0
        else:
            # No expected companies → precision is vacuously 1.0 (nothing to miss)
            precision = 1.0

        # MRR: 1/rank of first hit (1-indexed)
        mrr = 0.0
        if expected:
            for rank, content in enumerate(top5_contents, start=1):
                if _has_expected(content):
                    mrr = 1.0 / rank
                    break

        # Noise rate: fraction of top-5 matching must_not_contain
        def _is_noisy(content: str, _noise: list[str] = noise_patterns) -> bool:
            lower = content.lower()
            return any(n.lower() in lower for n in _noise)

        noise_hits = sum(1 for c in top5_contents if _is_noisy(c))
        noise_rate = noise_hits / max(len(top5_contents), 1) if top5_contents else 0.0

        temporal_respected = (
            case.temporal_constraint is None or after_date is not None
        )

        results.append(
            EvalResult(
                query=case.query,
                precision_at_5=round(precision, 4),
                mrr=round(mrr, 4),
                noise_rate=round(noise_rate, 4),
                temporal_respected=temporal_respected,
                latency_ms=round(latency_ms, 2),
                hits=[c[:120] for c in top5_contents],
            )
        )

    # Summary statistics
    n = len(results)
    summary = {
        "mean_precision_at_5": round(sum(r.precision_at_5 for r in results) / n, 4) if n else 0.0,
        "mean_mrr": round(sum(r.mrr for r in results) / n, 4) if n else 0.0,
        "noise_rate": round(sum(r.noise_rate for r in results) / n, 4) if n else 0.0,
    }

    return EvalReport(
        run_at=datetime.now(tz=UTC),
        git_commit=_get_git_commit(),
        cases=results,
        summary=summary,
    )


def _print_report(report: EvalReport) -> None:
    """Print a human-readable summary table to stdout.

    Args:
        report: The completed eval report.
    """
    print(f"\n{'='*70}")
    print(f"VIKI Retrieval Eval  |  {report.run_at.strftime('%Y-%m-%d %H:%M UTC')}  |  git: {report.git_commit}")
    print(f"{'='*70}")
    print(f"{'Query':<40} {'P@5':>5} {'MRR':>5} {'Noise':>6} {'ms':>8}")
    print(f"{'-'*70}")
    for r in report.cases:
        short_q = r.query[:38] + ".." if len(r.query) > 38 else r.query
        print(
            f"{short_q:<40} {r.precision_at_5:>5.2f} {r.mrr:>5.2f} "
            f"{r.noise_rate:>6.2f} {r.latency_ms:>8.1f}"
        )
    print(f"{'-'*70}")
    s = report.summary
    print(
        f"{'SUMMARY':<40} {s['mean_precision_at_5']:>5.2f} {s['mean_mrr']:>5.2f} "
        f"{s['noise_rate']:>6.2f}"
    )
    print(f"{'='*70}\n")


if __name__ == "__main__":
    import argparse
    import os

    from app.memory.in_memory import InMemoryStore

    parser = argparse.ArgumentParser(description="Run the VIKI retrieval eval suite.")
    parser.add_argument(
        "--output",
        default="eval_results",
        help="Directory to write JSON output (default: eval_results/)",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        default=False,
        help="Seed the store with fixture data before running eval.",
    )
    args = parser.parse_args()

    async def _main() -> None:
        store = InMemoryStore()
        if args.seed:
            await seed_eval_store(store, tenant_id="eval_test")
        report = await run_eval(store, GOLDEN_CASES)
        _print_report(report)

        output_dir = Path(args.output)
        # Use os.makedirs instead of pathlib to avoid ASYNC240 lint warning
        os.makedirs(str(output_dir), exist_ok=True)
        ts = datetime.now(tz=UTC).strftime("%Y-%m-%d_%H-%M")
        out_file = output_dir / f"{ts}.json"
        out_file.write_text(report.model_dump_json(indent=2))
        print(f"Report written to: {out_file}")

    asyncio.run(_main())
