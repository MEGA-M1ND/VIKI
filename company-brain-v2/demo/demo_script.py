#!/usr/bin/env python3
"""VIKI Demo Script — Day 90 demo artifact.

Runs end-to-end with zero external dependencies:
  - InMemoryStore  (no database required)
  - InMemoryVCRepository  (no database required)
  - FakeLLMProvider  (no API key required)
  - Fixture data seeded from app/eval/fixtures.py

Usage:
    cd company-brain-v2
    python demo/demo_script.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure the project root is importable when running from any directory.
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.dedup import deduplicate_by_source
from app.core.temporal import extract_temporal_constraint
from app.db.vc_repo import InMemoryVCRepository
from app.eval.seed import seed_eval_store
from app.llm.fake import FakeLLMProvider
from app.memory.in_memory import InMemoryStore
from app.models.retrieval import RetrievalQuery, ScoredFact
from app.prompts.ask import build_ask_messages
from app.scoring.founder import FounderSignalScorer

_TENANT = "demo"

_QUERIES = [
    {
        "id": "job_outreach",
        "label": "Job Outreach (last 30d)",
        "query": "which companies approached me for a job lately",
        "target": "store",
    },
    {
        "id": "founders_raising",
        "label": "Founders Raising Seed",
        "query": "founders raising seed round right now",
        "target": "store",
    },
    {
        "id": "followup_week",
        "label": "Follow-ups This Week",
        "query": "who followed up with me this week",
        "target": "store",
    },
    {
        "id": "alice_fundraise",
        "label": "Alice Chen Signals",
        "query": "what did Alice Chen say about her fundraise",
        "target": "store",
    },
    {
        "id": "fintech_deals",
        "label": "VC Fintech Founders",
        "query": "show me warm deals in fintech",
        "target": "vc_founders",
    },
]


async def _query_store(
    store: InMemoryStore,
    query_text: str,
    limit: int = 5,
) -> list[dict]:
    """Run a store retrieval query and return formatted rows."""
    cleaned, after_date = extract_temporal_constraint(query_text)
    filters: dict = {}
    if after_date:
        filters["after_date"] = after_date

    rq = RetrievalQuery(
        tenant_id=_TENANT,
        text=cleaned or query_text,
        limit=limit * 3,  # over-fetch for dedup
        filters=filters,
    )
    raw = await store.query(rq)

    # Dedup by source (mirrors /ask pipeline step 3a)
    scored = [
        ScoredFact(record=r.record, score=r.score, source_doc_id=r.record.source_doc_id)
        for r in raw
    ]
    scored = deduplicate_by_source(scored, max_per_source=2)

    now = datetime.now(tz=UTC)
    rows = []
    for sf in scored[:limit]:
        age_days = (now - sf.record.created_at).days
        rows.append(
            {
                "top_result": sf.record.content[:90],
                "score": round(sf.score, 3),
                "source": sf.record.source_type_hint or "unknown",
                "age_days": age_days,
            }
        )
    return rows


async def _query_vc_founders(
    vc_repo: InMemoryVCRepository,
    domain: str | None = "fintech",
    limit: int = 5,
) -> list[dict]:
    """Query VC founder table by domain and return formatted rows."""
    scorer = FounderSignalScorer()
    founders = await vc_repo.list_founders(tenant_id=_TENANT, domain=domain)

    # Recompute scores
    for f in founders:
        signals = await vc_repo.get_signals_for_founder(
            tenant_id=_TENANT, founder_id=f.id
        )
        score = scorer.score(f, signals)
        await vc_repo.update_founder_score(
            tenant_id=_TENANT, founder_id=f.id, score=score
        )

    founders = await vc_repo.list_founders(tenant_id=_TENANT, domain=domain)
    now = datetime.now(tz=UTC)
    rows = []
    for f in founders[:limit]:
        age_days = (now - f.last_contact_date).days
        rows.append(
            {
                "top_result": f"{f.full_name} @ {f.company_name} [{f.stage}]",
                "score": round(f.signal_score, 3),
                "source": "vc_table",
                "age_days": age_days,
            }
        )
    return rows


async def run_demo() -> dict:
    """Seed fixtures, run all demo queries, synthesise answers via FakeLLM."""
    store = InMemoryStore()
    vc_repo = InMemoryVCRepository()
    llm = FakeLLMProvider(
        default_response="Based on the retrieved context, I found relevant information."
    )
    llm.register("job", "Google, Stripe, and Acme Corp reached out about engineering roles.")
    llm.register("seed round", "Alice Chen at Acme AI is actively raising a $2M seed round.")
    llm.register("followed up", "Bob from DataStream and Carol both followed up this week.")
    llm.register("alice", "Alice Chen mentioned Acme AI is raising $2M seed, targeting Sequoia.")
    llm.register("fintech", "FinStack (Bob Rao) is the top fintech founder in the pipeline.")

    await seed_eval_store(store, vc_repo=vc_repo, tenant_id=_TENANT)

    output_rows: list[dict] = []
    for q in _QUERIES:
        if q["target"] == "store":
            rows = await _query_store(store, q["query"])
        else:
            rows = await _query_vc_founders(vc_repo)

        if rows:
            top_row = rows[0]
            # Synthesise an LLM answer for store queries
            if q["target"] == "store" and rows:
                context = "\n".join(f"[{i+1}] {r['top_result']}" for i, r in enumerate(rows))
                messages = build_ask_messages(
                    question=q["query"],
                    context=context,
                    hit_count=len(rows),
                )
                answer = await llm.chat(messages, temperature=0.2)
                top_row = {**top_row, "llm_answer": answer[:120]}

            output_rows.append(
                {
                    "query_id": q["id"],
                    "label": q["label"],
                    "query": q["query"],
                    "hit_count": len(rows),
                    **top_row,
                    "all_results": rows,
                }
            )
        else:
            output_rows.append(
                {
                    "query_id": q["id"],
                    "label": q["label"],
                    "query": q["query"],
                    "hit_count": 0,
                    "top_result": "(no results)",
                    "score": 0.0,
                    "source": "—",
                    "age_days": 0,
                }
            )

    return {
        "run_at": datetime.now(tz=UTC).isoformat(),
        "tenant": _TENANT,
        "queries_run": len(_QUERIES),
        "results": output_rows,
    }


def _print_table(demo_output: dict) -> None:
    w = 110
    print(f"\n{'='*w}")
    print(f"{'VIKI — Demo Run':^{w}}")
    print(f"{'='*w}")
    print(f"  {'Query':<42} {'Top Result':<40} {'Score':>6} {'Source':<24} {'Age':>5}")
    print(f"  {'-'*w}")

    prev_label = None
    for row in demo_output["results"]:
        label = row.get("label", "")
        if label != prev_label:
            if prev_label is not None:
                print()
            print(f"\n  [{label}]")
            prev_label = label

        q = row["query"]
        q_short = (q[:40] + "..") if len(q) > 40 else q
        res = row.get("top_result", "")
        res_short = (res[:38] + "..") if len(res) > 38 else res
        score = row.get("score", 0.0)
        source = row.get("source", "")
        age = row.get("age_days", 0)
        print(
            f"  {q_short:<42} {res_short:<40} {score:>6.3f} {source:<24} {age:>4}d"
        )
        if "llm_answer" in row:
            ans = row["llm_answer"]
            print(f"  {'':42} Answer: {ans}")

    print(f"\n  {'='*w}")
    print(f"  Queries run: {demo_output['queries_run']} | Tenant: {demo_output['tenant']}")
    print(f"  {'='*w}\n")


if __name__ == "__main__":
    demo_output = asyncio.run(run_demo())
    _print_table(demo_output)

    demo_dir = Path(__file__).parent
    out_file = demo_dir / "demo_output.json"
    out_file.write_text(json.dumps(demo_output, indent=2, default=str))
    print(f"Output saved to: {out_file}\n")
