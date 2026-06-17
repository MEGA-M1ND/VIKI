"""Classification prompt.

Asks the LLM whether a document contains information worth remembering as a
durable company-brain fact. Returns structured JSON so the classify node can
gate extraction without string parsing.
"""

from __future__ import annotations

CLASSIFY_SYSTEM = """\
You are a corporate memory filter. Your job is to decide whether a document \
contains information that is worth storing in long-term company memory.

Worth storing: decisions, approvals, budget information, project updates, key \
meeting outcomes, team changes, technical architecture choices, and important \
preferences or commitments.

NOT worth storing: routine status updates with no new information, social \
pleasantries, spam, auto-generated notifications, or already-known facts.

Respond with a JSON object:
{
  "is_worth_remembering": true | false,
  "confidence": 0.0–1.0,
  "reasoning": "<one sentence>"
}
"""

CLASSIFY_USER = """\
Source: {source}
Title: {title}
Author: {author}

Content:
{content}
"""


def build_classify_messages(
    *,
    source: str,
    title: str,
    author: str,
    content: str,
) -> list[dict[str, str]]:
    """Build the chat messages list for classification."""
    return [
        {"role": "system", "content": CLASSIFY_SYSTEM},
        {
            "role": "user",
            "content": CLASSIFY_USER.format(
                source=source,
                title=title or "(no title)",
                author=author or "(unknown)",
                content=content[:3000],  # cap input length
            ),
        },
    ]
