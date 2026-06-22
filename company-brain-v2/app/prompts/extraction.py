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


# ---------------------------------------------------------------------------
# VC fund intelligence extraction (Phase 2, ADDITIVE)
# ---------------------------------------------------------------------------

VC_EXTRACT_SYSTEM = """\
You are a structured fact extractor for a VC fund intelligence system.
Extract only durable, specific facts from the input document.

STRICT REJECTION RULES — output an empty array [] if the document is:
- A newsletter, digest, or bulk mailing (e.g. contains a List-Unsubscribe \
header or "unsubscribe"/"view in browser")
- A job board alert (LinkedIn Jobs, Naukri, AngelList digest)
- A promotional email from a SaaS tool
- An automated system notification (CI/CD, calendar invite, OTP)
- A legal disclaimer or terms update

For every fact you extract, classify it into exactly one of:
  FOUNDER_SIGNAL — someone is raising, building, or reaching out for investment
    Required fields: company_name, founder_name, signal_type, signal_date, \
raise_amount (if mentioned), stage (if mentioned)
  JOB_OPPORTUNITY — a recruiter or company reached out to the user for a role
    Required fields: company_name, recruiter_name (if known), role_title, \
outreach_date, seniority
  GENERAL_FACT — any other durable fact about a person, company, or project
    Required fields: subject, predicate, object

Output schema (JSON array, no markdown):
[
  {
    "fact_type": "FOUNDER_SIGNAL | JOB_OPPORTUNITY | GENERAL_FACT",
    "statement": "one crisp sentence",
    "entities": {"company": "...", "person": "...", "raise_amount": 2000000},
    "confidence": 0.0,
    "signal_date": "ISO8601 or null"
  }
]
If nothing durable is extractable, return [].
"""


def build_vc_extract_messages(
    *,
    source: str,
    title: str,
    author: str,
    content: str,
) -> list[dict[str, str]]:
    """Build the chat messages list for VC fund extraction.

    Mirrors :func:`build_extract_messages` but uses :data:`VC_EXTRACT_SYSTEM`.
    """
    return [
        {"role": "system", "content": VC_EXTRACT_SYSTEM},
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


def parse_vc_extraction(raw: str) -> list[dict]:
    """Parse the model's VC extraction output (a JSON array).

    Tolerates surrounding whitespace and markdown code fences. Returns ``[]``
    on empty or invalid input (never raises). Each item is coerced to the keys:
    ``fact_type``, ``statement``, ``entities`` (dict), ``confidence`` (float),
    ``signal_date`` (str | None).

    Args:
        raw: Raw model output string.

    Returns:
        A list of normalized fact dicts (possibly empty).
    """
    import json

    if not raw or not raw.strip():
        return []

    text_payload = raw.strip()
    # Strip markdown code fences if present (```json ... ``` or ``` ... ```).
    if text_payload.startswith("```"):
        lines = text_payload.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text_payload = "\n".join(lines).strip()

    try:
        data = json.loads(text_payload)
    except (ValueError, TypeError):
        return []

    if not isinstance(data, list):
        return []

    result: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        entities = item.get("entities")
        if not isinstance(entities, dict):
            entities = {}
        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        signal_date = item.get("signal_date")
        if signal_date is not None and not isinstance(signal_date, str):
            signal_date = str(signal_date)
        result.append(
            {
                "fact_type": item.get("fact_type"),
                "statement": item.get("statement"),
                "entities": entities,
                "confidence": confidence,
                "signal_date": signal_date,
            }
        )
    return result
