"""Cross-encoder reranker for retrieved facts.

Uses cross-encoder/ms-marco-MiniLM-L-6-v2 (MIT license, ~80 MB, CPU-only)
to score (query, content) pairs and re-rank retrieval results.

The model is loaded once at first use and cached as a module-level singleton.
If sentence-transformers is not installed, the reranker gracefully degrades
to returning the input list unchanged (order preserved).
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.models.retrieval import ScoredFact

logger = get_logger(__name__)

_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_model = None  # singleton
_model_load_attempted = False


def _get_model():
    """Load the cross-encoder model once and cache it as a module-level singleton."""
    global _model, _model_load_attempted
    if _model_load_attempted:
        return _model
    _model_load_attempted = True
    try:
        from sentence_transformers import CrossEncoder

        _model = CrossEncoder(_MODEL_NAME)
        logger.info("reranker.loaded", model=_MODEL_NAME)
    except Exception as exc:
        logger.warning("reranker.unavailable", reason=str(exc))
        _model = None
    return _model


class CrossEncoderReranker:
    """Reranks top-k hybrid retrieval results using a cross-encoder.

    Cross-encoder sees (query, fact_content) pairs and outputs relevance
    scores. Much more accurate than cosine similarity alone because the
    model attends to both query and document jointly.

    Model: cross-encoder/ms-marco-MiniLM-L-6-v2
    Gracefully degrades to no-op when sentence-transformers is unavailable.
    """

    def rerank(
        self,
        query: str,
        facts: list[ScoredFact],
        top_k: int = 10,
    ) -> list[ScoredFact]:
        """Rerank *facts* for *query*, returning the top *top_k*.

        Scoring formula: score = cross_encoder_score(query, fact.record.content).
        Source-type weights are applied AFTER this method (in the pipeline).

        Args:
            query: The user's natural-language question.
            facts: Candidate facts (e.g. top-20 from HybridRetriever).
            top_k: Number of results to return.

        Returns:
            Top-k facts sorted by descending cross-encoder score.
            If the model is unavailable, returns facts[:top_k] unchanged.
        """
        if not facts:
            return []

        model = _get_model()
        if model is None:
            logger.debug("reranker.skip", reason="model not loaded")
            return facts[:top_k]

        pairs = [(query, f.record.content) for f in facts]
        try:
            scores = model.predict(pairs)
        except Exception as exc:
            logger.warning("reranker.predict_failed", error=str(exc))
            return facts[:top_k]

        scored = sorted(
            zip(scores, facts, strict=True),
            key=lambda t: t[0],
            reverse=True,
        )
        result = []
        for score, fact in scored[:top_k]:
            result.append(
                ScoredFact(
                    record=fact.record,
                    score=float(score),
                    source_doc_id=fact.source_doc_id,
                    rationale=fact.rationale,
                )
            )
        return result
