import json
import time

import structlog
from langchain_openai import ChatOpenAI

from src.config import get_settings
from src.gbrain_client.mcp_client import GBrainMCPClient
from src.gbrain_client.page_builder import build_gbrain_page
from src.pipeline.prompts import CLASSIFIER_PROMPT, EXTRACTOR_PROMPT, FIX_JSON_PROMPT
from src.pipeline.state import ExtractionState

logger = structlog.get_logger(__name__)

SIMILARITY_DUPLICATE_THRESHOLD = 0.92


def _get_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )


def _parse_json_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    return json.loads(text)


async def _fix_and_parse_json(llm: ChatOpenAI, malformed: str) -> dict:
    chain = FIX_JSON_PROMPT | llm
    response = await chain.ainvoke({"malformed_json": malformed})
    return _parse_json_response(response.content)


async def classify_node(state: ExtractionState) -> ExtractionState:
    doc = state["document"]
    settings = get_settings()
    log = logger.bind(node="classify", source=doc.source, source_id=doc.source_id)

    llm = _get_llm()
    chain = CLASSIFIER_PROMPT | llm

    t0 = time.monotonic()
    try:
        response = await chain.ainvoke(
            {
                "source": doc.source,
                "author": doc.author or "unknown",
                "subject": doc.subject or "",
                "content": doc.content[:3000],
            }
        )
        parsed = _parse_json_response(response.content)
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("classify.json_parse_error", error=str(exc))
        try:
            parsed = await _fix_and_parse_json(llm, response.content)
        except Exception as fix_exc:
            log.error("classify.json_fix_failed", error=str(fix_exc))
            return {
                **state,
                "is_worth_remembering": False,
                "confidence": 0.0,
                "classifier_reasoning": f"JSON parse error: {exc}",
            }
    except Exception as exc:
        log.error("classify.llm_error", error=str(exc))
        return {
            **state,
            "is_worth_remembering": False,
            "confidence": 0.0,
            "classifier_reasoning": f"LLM error: {exc}",
        }

    worth = parsed.get("worth_remembering", False)
    confidence = float(parsed.get("confidence", 0.0))
    reasoning = parsed.get("reasoning", "")

    if confidence < settings.classifier_confidence_threshold:
        worth = False

    log.info(
        "classify.result",
        worth_remembering=worth,
        confidence=confidence,
        reasoning=reasoning,
        latency_ms=round((time.monotonic() - t0) * 1000),
    )

    return {
        **state,
        "is_worth_remembering": worth,
        "confidence": confidence,
        "classifier_reasoning": reasoning,
    }


async def extract_node(state: ExtractionState) -> ExtractionState:
    doc = state["document"]
    log = logger.bind(node="extract", source=doc.source, source_id=doc.source_id)

    llm = _get_llm()
    chain = EXTRACTOR_PROMPT | llm

    t0 = time.monotonic()
    try:
        response = await chain.ainvoke(
            {
                "source": doc.source,
                "author": doc.author or "unknown",
                "subject": doc.subject or "",
                "content": doc.content[:4000],
            }
        )
        parsed = _parse_json_response(response.content)
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("extract.json_parse_error", error=str(exc))
        try:
            parsed = await _fix_and_parse_json(llm, response.content)
        except Exception as fix_exc:
            log.error("extract.json_fix_failed", error=str(fix_exc))
            return {
                **state,
                "write_status": "failed",
                "error": f"Extraction JSON parse failed: {fix_exc}",
            }
    except Exception as exc:
        log.error("extract.llm_error", error=str(exc))
        return {
            **state,
            "write_status": "failed",
            "error": f"Extraction LLM error: {exc}",
        }

    summary = parsed.get("summary", "")
    entities = parsed.get("entities", [])[:10]
    key_facts = parsed.get("key_facts", [])[:10]

    log.info(
        "extract.result",
        entity_count=len(entities),
        fact_count=len(key_facts),
        latency_ms=round((time.monotonic() - t0) * 1000),
    )

    return {
        **state,
        "summary": summary,
        "entities": entities,
        "extracted_facts": [{"fact": f, "confidence": state.get("confidence", 1.0)} for f in key_facts],
    }


async def deduplicate_node(state: ExtractionState) -> ExtractionState:
    doc = state["document"]
    summary = state.get("summary") or doc.subject or doc.content[:200]
    log = logger.bind(node="deduplicate", source=doc.source, source_id=doc.source_id)

    settings = get_settings()
    client = GBrainMCPClient(settings)

    try:
        results = await client.search(summary, limit=5)
    except Exception as exc:
        log.warning("deduplicate.search_failed", error=str(exc))
        return {**state, "is_duplicate": False, "existing_similar_pages": []}

    high_sim = [r for r in results if r.get("score", 0.0) >= SIMILARITY_DUPLICATE_THRESHOLD]

    if high_sim:
        log.info(
            "deduplicate.duplicate_found",
            top_score=high_sim[0].get("score"),
            slug=high_sim[0].get("slug"),
        )
    else:
        log.debug("deduplicate.no_duplicate", result_count=len(results))

    return {
        **state,
        "is_duplicate": len(high_sim) > 0,
        "existing_similar_pages": high_sim,
    }


async def write_node(state: ExtractionState) -> ExtractionState:
    doc = state["document"]
    log = logger.bind(node="write", source=doc.source, source_id=doc.source_id)

    settings = get_settings()
    client = GBrainMCPClient(settings)

    try:
        slug, content = build_gbrain_page(state)
    except Exception as exc:
        log.error("write.page_build_failed", error=str(exc))
        return {**state, "write_status": "failed", "error": f"Page build error: {exc}"}

    entities = state.get("entities") or []
    metadata = {
        "source": doc.source,
        "source_id": doc.source_id,
        "author": doc.author,
        "confidence": state.get("confidence", 1.0),
        "entities": [e.get("name", "") for e in entities],
    }

    try:
        await client.put_page(slug=slug, content=content, metadata=metadata)
        log.info("write.success", slug=slug)
        return {**state, "gbrain_page_slug": slug, "write_status": "success"}
    except Exception as exc:
        log.error("write.gbrain_failed", slug=slug, error=str(exc))
        _save_failed_write(slug, content, str(exc))
        return {
            **state,
            "gbrain_page_slug": slug,
            "write_status": "failed",
            "error": str(exc),
        }


def _save_failed_write(slug: str, content: str, error: str) -> None:
    import json as _json
    from pathlib import Path

    record = {"slug": slug, "content": content, "error": error}
    with open("failed_writes.jsonl", "a") as f:
        f.write(_json.dumps(record) + "\n")
