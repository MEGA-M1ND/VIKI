"""Integration tests for the pgvector HybridRetriever.

These tests require a live PostgreSQL+pgvector instance with the schema
migrated (``alembic upgrade head``). They are SKIPPED automatically when no
database is reachable, so the default ``pytest`` run stays green in CI.

To run them, start the DB (``docker compose up -d`` in ``company-brain-v2``),
apply migrations, and set ``CB_MEMORY_DSN`` if you use a non-default DSN.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import text

from app.db.engine import session_scope
from app.db.retriever import HybridRetriever
from app.llm.fake import FakeLLMProvider
from app.memory.pgvector import PgVectorMemoryStore
from app.models.memory import MemoryRecord

_DSN = os.environ.get(
    "CB_MEMORY_DSN", "postgresql+asyncpg://viki:viki@localhost:5432/viki"
)


def _db_available() -> bool:
    """Return True if the test database is reachable and migrated.

    Uses a raw asyncpg connection in a throwaway event loop so it does NOT
    populate the lru_cached SQLAlchemy engine (whose pooled connections would
    otherwise be bound to this dead loop and break the actual test).
    """

    async def _check() -> bool:
        import asyncpg

        raw_dsn = _DSN.replace("+asyncpg", "")
        try:
            conn = await asyncpg.connect(raw_dsn)
        except Exception:
            return False
        try:
            await conn.execute("SELECT 1 FROM memory_records LIMIT 1")
            return True
        except Exception:
            return False
        finally:
            await conn.close()

    try:
        return asyncio.run(_check())
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(),
    reason="PostgreSQL+pgvector not reachable (start docker compose + alembic upgrade head)",
)


@pytest.fixture(autouse=True)
def _fresh_engine() -> object:
    """Build the async engine inside the test's own event loop.

    The engine is lru_cached and its asyncpg pool is event-loop bound; clearing
    the cache around each test avoids reusing connections across loops.
    """
    from app.db import engine as engine_module

    engine_module.get_engine.cache_clear()
    yield
    engine_module.get_engine.cache_clear()


async def test_bm25_websearch_does_not_block_on_missing_term() -> None:
    """A query with one absent term must still return results.

    Regression test for the plainto_tsquery -> websearch_to_tsquery switch.
    'funding' appears in zero documents. Under plainto_tsquery (AND semantics)
    BM25 would match 0 rows; under websearch_to_tsquery (OR semantics) the
    other terms still match. Either way the vector arm contributes, so the
    hybrid retriever must never return an empty list just because one query
    term is missing from the corpus.
    """
    tenant = f"test_{uuid.uuid4().hex[:8]}"
    llm = FakeLLMProvider()
    store = PgVectorMemoryStore(dsn=_DSN, llm=llm)

    records = [
        MemoryRecord(
            id=f"{tenant}_r1",
            tenant_id=tenant,
            content="Acme founder Alice is raising a seed round",
            source_doc_id="docA",
        ),
        MemoryRecord(
            id=f"{tenant}_r2",
            tenant_id=tenant,
            content="Bob discussed his seed stage startup over coffee",
            source_doc_id="docB",
        ),
    ]
    for rec in records:
        await store.write(rec)

    query = "founder raising seed round funding"  # 'funding' is in no document
    embedding = (await llm.embed([query]))[0]

    try:
        async with session_scope(_DSN) as session:

            async def _count(sql_fn: str, q: str) -> int:
                return (
                    await session.execute(
                        text(
                            "SELECT count(*) FROM memory_records "
                            "WHERE tenant_id = :t "
                            f"AND ts_content @@ {sql_fn}('english', :q)"
                        ),
                        {"t": tenant, "q": q},
                    )
                ).scalar_one()

            # Bare multi-term query: BOTH plainto and websearch AND every lexeme,
            # so the absent term 'funding' yields zero BM25 matches. (websearch
            # does NOT OR unquoted terms — that is standard Postgres behaviour.)
            plain_count = await _count("plainto_tsquery", query)
            web_count = await _count("websearch_to_tsquery", query)
            # websearch's real advantage: it understands explicit OR / phrases /
            # negation that plainto cannot express at all.
            or_count = await _count("websearch_to_tsquery", "founder or funding")

        assert plain_count == 0, "plainto ANDs every term -> 0 on a missing term"
        assert web_count == 0, "websearch also ANDs unquoted terms -> 0 on a missing term"
        assert or_count >= 1, "websearch supports explicit OR (plainto cannot)"

        # Core goal: the hybrid retriever is resilient. Even when BM25 contributes
        # zero rows (a query term is absent), the vector arm still contributes, so
        # retrieve() must never return an empty list.
        async with session_scope(_DSN) as session:
            retriever = HybridRetriever(session)
            results = await retriever.retrieve(
                query=query,
                query_embedding=embedding,
                tenant_id=tenant,
                top_k=10,
            )
        assert results, "HybridRetriever must not return empty when BM25 matches nothing"
    finally:
        async with session_scope(_DSN) as session:
            await session.execute(
                text("DELETE FROM memory_records WHERE tenant_id = :t"), {"t": tenant}
            )
