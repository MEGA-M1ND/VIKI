"""Tests for TenantMiddleware and RateLimitMiddleware (Phase 3).

Covers:
- GET /vc/founders with no tenant_id → 400
- GET /vc/founders with invalid tenant_id format → 400
- Tenant isolation: records for tenant A are not visible from tenant B
- RateLimitMiddleware unit test: allows N requests then returns 429
- Eval runner produces valid JSON output
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from app.middleware.rate_limit import RateLimitMiddleware


def test_missing_tenant_id_returns_400(client) -> None:
    """GET /vc/founders with no tenant_id header or query param → 400."""
    resp = client.get("/vc/founders")
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"


def test_invalid_tenant_id_format_returns_400(client) -> None:
    """GET /vc/founders with an invalid tenant_id format → 400."""
    resp = client.get("/vc/founders", params={"tenant_id": "!@#invalid!"})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"


def test_tenant_isolation_via_vc_repo(client) -> None:
    """A founder in tenant 'alpha' is not visible from tenant 'beta'."""
    import asyncio

    from app.models.vc import FounderProfile
    from app.utils.ids import utcnow

    repo = client.app.state.container.vc_repository

    founder = FounderProfile(
        tenant_id="alpha",
        full_name="Alpha Founder",
        company_name="Alpha Corp",
        stage="seed",
        domain="saas",
        location="SF",
        last_contact_date=utcnow(),
        signal_score=0.7,
    )
    asyncio.run(repo.upsert_founder(founder))

    # Alpha sees it
    resp_alpha = client.get("/vc/founders", params={"tenant_id": "alpha"})
    assert resp_alpha.status_code == 200
    assert any(f["company_name"] == "Alpha Corp" for f in resp_alpha.json())

    # Beta does not see it
    resp_beta = client.get("/vc/founders", params={"tenant_id": "beta"})
    assert resp_beta.status_code == 200
    assert not any(f["company_name"] == "Alpha Corp" for f in resp_beta.json())


def test_rate_limit_middleware_logic() -> None:
    """Unit test: RateLimitMiddleware allows N requests then returns 429."""

    async def _run() -> None:
        mw = RateLimitMiddleware(app=MagicMock(), limits={"/vc": (2, 60)})

        good_response = MagicMock()
        good_response.status_code = 200
        call_next = AsyncMock(return_value=good_response)

        req = MagicMock()
        req.headers.get = lambda k, d=None: None
        req.query_params.get = lambda k, d=None: "tenant_a" if k == "tenant_id" else d
        req.url.path = "/vc/founders"

        r1 = await mw.dispatch(req, call_next)
        r2 = await mw.dispatch(req, call_next)
        r3 = await mw.dispatch(req, call_next)

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 429, f"Expected 429 but got {r3.status_code}"

    asyncio.run(_run())


def test_eval_runner_produces_json_output(tmp_path) -> None:
    """Eval runner produces a valid JSON report with the expected summary keys."""
    from app.eval.golden import GOLDEN_CASES
    from app.eval.runner import run_eval, seed_eval_store
    from app.memory.in_memory import InMemoryStore

    store = InMemoryStore()
    asyncio.run(seed_eval_store(store, tenant_id="eval_test"))
    report = asyncio.run(run_eval(store, GOLDEN_CASES))

    output_file = tmp_path / "eval.json"
    output_file.write_text(report.model_dump_json())

    data = json.loads(output_file.read_text())
    assert "summary" in data
    assert "mean_precision_at_5" in data["summary"]
    assert "mean_mrr" in data["summary"]
    assert "noise_rate" in data["summary"]
    assert len(data["cases"]) == len(GOLDEN_CASES)

    # Each case should have the expected fields
    for case_result in data["cases"]:
        assert "query" in case_result
        assert "precision_at_5" in case_result
        assert "mrr" in case_result
        assert "noise_rate" in case_result
        assert "temporal_respected" in case_result
        assert "latency_ms" in case_result
        assert "hits" in case_result
