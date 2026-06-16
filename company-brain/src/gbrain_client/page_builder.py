import re
from datetime import datetime, timezone

from src.pipeline.state import ExtractionState


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:60].strip("-")


def build_gbrain_page(state: ExtractionState) -> tuple[str, str]:
    doc = state["document"]
    summary = state.get("summary") or ""
    entities = state.get("entities") or []
    extracted_facts = state.get("extracted_facts") or []
    confidence = state.get("confidence") or 1.0

    date_str = doc.fetched_at.strftime("%Y-%m-%d")
    title_raw = doc.subject or summary[:80] or doc.source_id
    title_slug = _slugify(title_raw)

    slug = f"{doc.source}/{date_str}/{title_slug}"

    entity_names = [e.get("name", "") for e in entities if e.get("name")]
    entity_names_str = ", ".join(entity_names) if entity_names else ""

    source_type_map = {"gmail": "email", "notion": "notion-page", "slack": "slack-message"}
    page_type = source_type_map.get(doc.source, doc.source)

    facts = [f.get("fact", str(f)) if isinstance(f, dict) else str(f) for f in extracted_facts]

    # Build frontmatter
    frontmatter_lines = [
        "---",
        f"type: {page_type}",
        f"source: {doc.source}",
        f"source_id: {doc.source_id}",
        f"author: {doc.author or 'unknown'}",
        f"date: {doc.fetched_at.isoformat()}",
    ]
    if entity_names_str:
        frontmatter_lines.append(f"entities: [{entity_names_str}]")
    frontmatter_lines.extend([
        "tags: [auto-extracted, company-brain]",
        f"confidence: {round(confidence, 2)}",
        "---",
    ])

    # Build body
    body_lines = [f"# {title_raw}", ""]

    if summary:
        body_lines.extend([summary, ""])

    if facts:
        body_lines.append("## Key Facts")
        for fact in facts:
            body_lines.append(f"- {fact}")
        body_lines.append("")

    if entities:
        body_lines.append("## Entities Mentioned")
        for entity in entities:
            name = entity.get("name", "")
            etype = entity.get("type", "")
            body_lines.append(f"- **{name}** ({etype})")
        body_lines.append("")

    body_lines.extend([
        "## Raw Content",
        doc.content[:2000],
    ])

    content = "\n".join(frontmatter_lines) + "\n\n" + "\n".join(body_lines)
    return slug, content
