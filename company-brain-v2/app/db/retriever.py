"""Hybrid retriever: pgvector cosine similarity + PostgreSQL BM25.

Combines two ranked lists using Reciprocal Rank Fusion (RRF) with k=60.
RRF score = Σ 1/(k + rank_i) across retrieval methods.

The retriever operates directly on the memory_records table via
asyncpg/SQLAlchemy and returns ScoredFact objects ready for downstream
deduplication and reranking.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.common import FactType, SourceType
from app.models.memory import MemoryRecord
from app.models.retrieval import ScoredFact

logger = get_logger(__name__)

_RRF_K = 60


class HybridRetriever:
    """Combines pgvector cosine similarity with PostgreSQL BM25 full-text search.

    Uses Reciprocal Rank Fusion (RRF) to merge two ranked lists:
      - Vector search: top-N by cosine similarity on embedding column
      - BM25 search: top-N by ts_rank on ts_content tsvector column

    RRF score = sum(1 / (k + rank_i)) where k=60 and rank_i is the
    zero-based rank in each list (so rank_i=0 -> highest score).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def retrieve(
        self,
        query: str,
        query_embedding: list[float],
        tenant_id: str,
        top_k: int = 20,
        source_type_filter: str | None = None,
        after_date: datetime | None = None,
    ) -> list[ScoredFact]:
        """Retrieve and RRF-merge vector + BM25 results.

        Args:
            query: Raw query text (used for BM25 plainto_tsquery).
            query_embedding: Precomputed embedding for vector search.
            tenant_id: Tenant to restrict results to.
            top_k: Number of merged results to return.
            source_type_filter: Optional source_type_hint filter.
            after_date: If set, only return records created after this datetime.

        Returns:
            RRF-merged list of ScoredFact (up to top_k * 2 candidates for downstream ranking).
        """
        # Build optional WHERE clauses
        extra_conditions = ""
        params: dict = {
            "tenant_id": tenant_id,
            "embedding": str(query_embedding),
            "tsquery": query,
            "top_n": top_k * 2,  # fetch extra candidates for RRF
        }

        if source_type_filter:
            extra_conditions += " AND source_type_hint = :source_type_filter"
            params["source_type_filter"] = source_type_filter

        if after_date:
            extra_conditions += " AND created_at >= :after_date"
            params["after_date"] = after_date

        vector_sql = text(f"""
            SELECT
                id,
                ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:embedding AS vector)) - 1 AS rank
            FROM memory_records
            WHERE tenant_id = :tenant_id
              AND embedding IS NOT NULL
              {extra_conditions}
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :top_n
        """)

        # websearch_to_tsquery (vs plainto_tsquery) defaults unquoted terms to OR,
        # not AND — so a query like "founder raising seed funding" still matches
        # docs missing "funding". It also supports quoted phrases ("seed round"),
        # explicit OR, and negation (-newsletter). This materially improves recall.
        bm25_sql = text(f"""
            SELECT
                id,
                ROW_NUMBER() OVER (
                    ORDER BY ts_rank(ts_content, websearch_to_tsquery('english', :tsquery)) DESC
                ) - 1 AS rank
            FROM memory_records
            WHERE tenant_id = :tenant_id
              AND ts_content @@ websearch_to_tsquery('english', :tsquery)
              {extra_conditions}
            ORDER BY ts_rank(ts_content, websearch_to_tsquery('english', :tsquery)) DESC
            LIMIT :top_n
        """)

        vec_rows = (await self._session.execute(vector_sql, params)).fetchall()
        bm25_rows = (await self._session.execute(bm25_sql, params)).fetchall()

        # Build RRF score map: id -> sum of 1/(k + rank)
        rrf_scores: dict[str, float] = {}
        for row in vec_rows:
            rrf_scores[row.id] = rrf_scores.get(row.id, 0.0) + 1.0 / (_RRF_K + row.rank)
        for row in bm25_rows:
            rrf_scores[row.id] = rrf_scores.get(row.id, 0.0) + 1.0 / (_RRF_K + row.rank)

        if not rrf_scores:
            return []

        # Sort by RRF score descending, take top_k * 2 candidates
        sorted_ids = sorted(rrf_scores, key=lambda i: rrf_scores[i], reverse=True)[: top_k * 2]

        # Fetch full records for the merged set
        fetch_sql = text("""
            SELECT
                id, tenant_id, content, record_type, source,
                source_doc_id, source_refs, source_type_hint,
                record_metadata, created_at, updated_at
            FROM memory_records
            WHERE id = ANY(:ids)
        """)
        rows = (await self._session.execute(fetch_sql, {"ids": sorted_ids})).fetchall()

        row_by_id = {r.id: r for r in rows}
        results: list[ScoredFact] = []
        for rec_id in sorted_ids:
            if rec_id not in row_by_id:
                continue
            r = row_by_id[rec_id]
            source_val = None
            if r.source and r.source in SourceType.__members__.values():
                source_val = SourceType(r.source)
            fact_type_val = FactType.FACT
            if r.record_type and r.record_type in FactType.__members__.values():
                fact_type_val = FactType(r.record_type)
            record = MemoryRecord(
                id=r.id,
                tenant_id=r.tenant_id,
                content=r.content,
                record_type=fact_type_val,
                source=source_val,
                source_doc_id=r.source_doc_id,
                source_refs=r.source_refs or [],
                source_type_hint=r.source_type_hint,
                embedding=None,  # don't send vectors back to app layer
                metadata=r.record_metadata or {},
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            results.append(
                ScoredFact(
                    record=record,
                    score=rrf_scores[rec_id],
                    source_doc_id=r.source_doc_id,
                )
            )

        logger.info(
            "retriever.hybrid",
            tenant_id=tenant_id,
            vector_hits=len(vec_rows),
            bm25_hits=len(bm25_rows),
            merged=len(results),
        )
        return results
