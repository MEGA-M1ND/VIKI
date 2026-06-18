"""Ask / QA prompt for the /ask endpoint.

Instructs VIKI to answer based strictly on retrieved memory context.
"""

from __future__ import annotations

ASK_SYSTEM = """\
You are VIKI, a personal memory assistant. You have access to a curated set of \
memory records retrieved from the user's inbox, notes, and documents.

Rules:
- Answer based ONLY on the provided context below.
- Be concise and direct. Do not repeat the question.
- If the context does not contain enough information to answer, say explicitly: \
"I don't have enough information in my memory to answer that."
- Never fabricate facts, names, dates, or figures.
- If multiple memory records are relevant, synthesize them into a single clear answer.
"""

ASK_USER = """\
Context from memory ({hit_count} records retrieved):

{context}

---
Question: {question}
"""


def build_ask_messages(
    *,
    question: str,
    context: str,
    hit_count: int,
) -> list[dict[str, str]]:
    """Build the chat messages list for the /ask endpoint."""
    return [
        {"role": "system", "content": ASK_SYSTEM},
        {
            "role": "user",
            "content": ASK_USER.format(
                question=question,
                context=context if context else "(no relevant records found)",
                hit_count=hit_count,
            ),
        },
    ]
