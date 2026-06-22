"""PostgreSQL + pgvector memory backend.

Implements the MemoryStore interface using:
- asyncpg/SQLAlchemy for persistence
- pgvector for semantic (cosine) search
- tsvector for BM25 full-text search
- HybridRetriever + RRF for query answering

Embeddings are generated via the LLMProvider.embed() method
and stored in the memory_records.embedding column.
"""
from __future__ import annotations

import json

from sqlalchemy import text

from app.core.logging import get_logger
from app.db.engine import session_scope
from app.llm.base import LLMProvider
from app.memory.base import MemoryStore
from app.models.common import FactType, SourceType
from app.models.memory import MemoryRecord
from app.models.retrieval import RetrievalQuery, RetrievalResult
from app.utils.ids import utcnow

logger = get_logger(__name__)

# Number of top candidates to retrieve before deduplication + reranking
_HYBRID_CANDIDATES = 20


class PgVectorMemoryStore(MemoryStore):
    """pgvector-backed memory store with hybrid BM25 + semantic retrieval.

    Args:
        dsn: asyncpg-compatible PostgreSQL DSN.
        llm: LLM provider used to generate embeddings.
    """

    def __init__(self, dsn: str, llm: LLMProvider) -> None:
        self._dsn = dsn
        self._llm = llm

    async def write(self, record: MemoryRecord) -> MemoryRecord:
        """Upsert a memory record, computing and storing its embedding.

        Args:
            record: The record to store.

        Returns:
            The stored record with embedding populated.
        """
        embeddings = await self._llm.embed([record.content])
        embedding = embeddings[0]

        source_doc_id = record.source_doc_id or (
            record.source_refs[0] if record.source_refs else None
        )

        async with session_scope(self._dsn) as session:
            await session.execute(
                text("""
                    INSERT INTO memory_records (
                        id, tenant_id, content, record_type, source,
                        source_doc_id, source_refs, source_type_hint,
                        embedding, record_metadata, created_at, updated_at
                    ) VALUES (
                        :id, :tenant_id, :content, :record_type, :source,
                        :source_doc_id, CAST(:source_refs AS jsonb), :source_type_hint,
                        CAST(:embedding AS vector), CAST(:record_metadata AS jsonb),
                        :created_at, :updated_at
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        content = EXCLUDED.content,
                        record_type = EXCLUDED.record_type,
                        source = EXCLUDED.source,
                        source_doc_id = EXCLUDED.source_doc_id,
                        source_refs = EXCLUDED.source_refs,
                        source_type_hint = EXCLUDED.source_type_hint,
                        embedding = EXCLUDED.embedding,
                        record_metadata = EXCLUDED.record_metadata,
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    "id": record.id,
                    "tenant_id": record.tenant_id,
                    "content": record.content,
                    "record_type": record.record_type,
                    "source": record.source,
                    "source_doc_id": source_doc_id,
                    "source_refs": json.dumps(record.source_refs),
                    "source_type_hint": record.source_type_hint,
                    "embedding": str(embedding),
                    "record_metadata": json.dumps(record.metadata),
                    "created_at": record.created_at,
                    "updated_at": utcnow(),
                },
            )
        logger.info("pgvector.write", tenant=record.tenant_id, record_id=record.id)
        return record

    async def get(self, *, tenant_id: str, record_id: str) -> MemoryRecord | None:
        """Fetch a single record by id.

        Args:
            tenant_id: Owning tenant.
            record_id: The record's unique id.

        Returns:
            The matching MemoryRecord, or None if not found.
        """
        async with session_scope(self._dsn) as session:
            row = (
                await session.execute(
                    text("""
                        SELECT id, tenant_id, content, record_type, source,
                               source_doc_id, source_refs, source_type_hint,
                               record_metadata, created_at, updated_at
                        FROM memory_records
                        WHERE id = :id AND tenant_id = :tenant_id
                    """),
                    {"id": record_id, "tenant_id": tenant_id},
                )
            ).fetchone()
        if row is None:
            return None
        return _row_to_record(row)

    async def query(self, query: RetrievalQuery) -> list[RetrievalResult]:
        """Hybrid BM25 + vector retrieval with RRF merge.

        Args:
            query: The retrieval request (tenant-scoped).

        Returns:
            Ranked results, best first (up to query.limit).
        """
        from app.core.dedup import deduplicate_by_source
        from app.db.retriever import HybridRetriever

        embeddings = await self._llm.embed([query.text])
        query_embedding = embeddings[0]

        after_date = query.filters.get("after_date")  # type: ignore[assignment]

        async with session_scope(self._dsn) as session:
            retriever = HybridRetriever(session)
            scored = await retriever.retrieve(
                query=query.text,
                query_embedding=query_embedding,
                tenant_id=query.tenant_id,
                top_k=max(query.limit, _HYBRID_CANDIDATES),
                after_date=after_date,
            )

        # Dedup + clamp to limit
        scored = deduplicate_by_source(scored, max_per_source=2)

        return [sf.to_retrieval_result() for sf in scored[: query.limit]]

    async def delete(self, *, tenant_id: str, record_id: str) -> bool:
        """Delete a record by id.

        Args:
            tenant_id: Owning tenant.
            record_id: The record to delete.

        Returns:
            True if a record was removed, False if it didn't exist.
        """
        async with session_scope(self._dsn) as session:
            result = await session.execute(
                text(
                    "DELETE FROM memory_records WHERE id = :id AND tenant_id = :tenant_id"
                ),
                {"id": record_id, "tenant_id": tenant_id},
            )
        return result.rowcount > 0

    async def find_by_dedupe_key(self, *, tenant_id: str, dedupe_key: str) -> MemoryRecord | None:
        """Direct SQL lookup by dedupe_key stored in record_metadata JSONB."""
        async with session_scope(self._dsn) as session:
            row = (
                await session.execute(
                    text("""
                        SELECT id, tenant_id, content, record_type, source,
                               source_doc_id, source_refs, source_type_hint,
                               record_metadata, created_at, updated_at
                        FROM memory_records
                        WHERE tenant_id = :tenant_id
                          AND record_metadata->>'dedupe_key' = :dedupe_key
                        LIMIT 1
                    """),
                    {"tenant_id": tenant_id, "dedupe_key": dedupe_key},
                )
            ).fetchone()
        return _row_to_record(row) if row else None

    async def health_check(self) -> bool:
        """Check if the database is reachable.

        Returns:
            True if a SELECT 1 succeeds, False otherwise.
        """
        try:
            async with session_scope(self._dsn) as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.warning("pgvector.health_check_failed", error=str(exc))
            return False


def _row_to_record(row) -> MemoryRecord:
    """Convert a database row to a MemoryRecord.

    Args:
        row: A SQLAlchemy Row with memory_records columns.

    Returns:
        A fully populated MemoryRecord.
    """
    source_val = None
    if row.source and row.source in SourceType.__members__.values():
        source_val = SourceType(row.source)
    fact_type_val = FactType.FACT
    if row.record_type and row.record_type in FactType.__members__.values():
        fact_type_val = FactType(row.record_type)
    return MemoryRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        content=row.content,
        record_type=fact_type_val,
        source=source_val,
        source_doc_id=row.source_doc_id,
        source_refs=row.source_refs or [],
        source_type_hint=row.source_type_hint,
        embedding=None,
        metadata=row.record_metadata or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
