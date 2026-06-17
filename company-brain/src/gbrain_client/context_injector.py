import structlog

from src.config import get_settings
from src.gbrain_client.mcp_client import GBrainMCPClient

logger = structlog.get_logger(__name__)

_CHARS_PER_TOKEN_APPROX = 4


async def inject_context(
    agent_state: dict,
    query: str,
    max_tokens: int = 2000,
) -> dict:
    """Retrieve relevant context from GBrain and inject it into agent state.

    Call at the start of any LangGraph agent that needs company context.
    Adds `injected_context` (str) and `injected_sources` (list) to state.
    """
    settings = get_settings()
    client = GBrainMCPClient(settings)
    log = logger.bind(query=query[:80])

    budget = max_tokens * _CHARS_PER_TOKEN_APPROX
    sections: list[str] = []

    try:
        synthesis = await client.think(query)
        if synthesis:
            section = f"## Synthesized Company Context\n{synthesis}"
            sections.append(section)
            budget -= len(section)
            log.debug("context_injector.synthesis_ok", chars=len(section))
    except Exception as exc:
        log.warning("context_injector.synthesis_failed", error=str(exc))

    sources: list[dict] = []
    try:
        raw_results = await client.search(query, limit=5)
        for result in raw_results:
            if budget <= 0:
                break
            slug = result.get("slug", "")
            snippet = result.get("snippet") or result.get("content", "")
            score = result.get("score", 0.0)
            if not snippet:
                continue
            snippet = snippet[: min(400, budget)]
            entry = f"### [{slug}] (score: {score:.2f})\n{snippet}"
            sections.append(entry)
            sources.append({"slug": slug, "score": score})
            budget -= len(entry)
        log.debug("context_injector.sources_ok", source_count=len(sources))
    except Exception as exc:
        log.warning("context_injector.search_failed", error=str(exc))

    injected_context = "\n\n".join(sections) if sections else ""

    log.info(
        "context_injector.done",
        total_chars=len(injected_context),
        source_count=len(sources),
    )

    return {
        **agent_state,
        "injected_context": injected_context,
        "injected_sources": sources,
    }


def make_context_node(query_field: str = "user_input"):
    """Return a LangGraph node that injects GBrain context into state."""

    async def context_node(state: dict) -> dict:
        query = state.get(query_field, "")
        return await inject_context(state, query)

    return context_node
