"""Extraction prompt.

Instructs the LLM to pull atomic, durable facts from a document. Returns
structured JSON matching the :class:`~app.models.facts.ExtractedFact` schema
(minus id/tenant_id/created_at which are assigned downstream).
"""

from __future__ import annotations

EXTRACT_SYSTEM = """\
You are a fact extractor for a corporate memory system. Extract atomic, \
durable facts from the provided document.

Each fact must be:
- Self-contained (understandable without the source document)
- Durable (still relevant in 6 months)
- Specific (include names, amounts, dates where present)

For each fact, also extract:
- subject: who or what the fact is about
- predicate: the action or relationship
- object: the target or value
- tags: 1-3 short keywords for filtering
- fact_type: one of fact | decision | action_item | preference | entity | relationship
- confidence: 0.0–1.0

Respond with JSON:
{
  "facts": [
    {
      "statement": "Alice approved the Q2 infrastructure budget of $500k",
      "subject": "Alice",
      "predicate": "approved",
      "object": "Q2 infrastructure budget of $500k",
      "tags": ["budget", "q2", "infrastructure"],
      "fact_type": "decision",
      "confidence": 0.95
    }
  ],
  "entities": [
    {"name": "Alice", "type": "person"},
    {"name": "Q2 infrastructure budget", "type": "concept"}
  ]
}

Return at most 10 facts and 10 entities. If nothing durable is found, return \
{"facts": [], "entities": []}.
"""

EXTRACT_USER = """\
Source: {source}
Title: {title}
Author: {author}

Content:
{content}
"""


def build_extract_messages(
    *,
    source: str,
    title: str,
    author: str,
    content: str,
) -> list[dict[str, str]]:
    """Build the chat messages list for extraction."""
    return [
        {"role": "system", "content": EXTRACT_SYSTEM},
        {
            "role": "user",
            "content": EXTRACT_USER.format(
                source=source,
                title=title or "(no title)",
                author=author or "(unknown)",
                content=content[:6000],
            ),
        },
    ]
