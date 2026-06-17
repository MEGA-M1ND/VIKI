from langchain_core.prompts import ChatPromptTemplate

CLASSIFIER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a knowledge curator for a company brain. Your job is to decide whether a document
contains information worth storing in long-term organizational memory.

WORTH REMEMBERING:
- Decisions made (product, technical, strategic, financial)
- Commitments and promises (deadlines, deliverables, agreements)
- Introductions and new relationships (people, partners, vendors)
- Project updates with concrete progress or blockers
- Technical knowledge and architectural decisions
- Action items assigned to specific people
- Key facts about people, companies, or projects

NOT WORTH REMEMBERING:
- Status-only updates with no decisions or actions
- Automated reports, CI/CD notifications, monitoring alerts
- Spam, newsletters, promotional emails
- Routine acknowledgements ("sounds good", "thanks", "noted")
- Calendar invites without agenda content
- Social media digests or aggregators

Respond ONLY with valid JSON. No explanation outside the JSON object.""",
        ),
        (
            "human",
            """Evaluate this document and decide if it is worth storing in long-term memory.

SOURCE: {source}
AUTHOR: {author}
SUBJECT: {subject}
CONTENT:
{content}

Respond with JSON:
{{
  "worth_remembering": true | false,
  "confidence": 0.0 to 1.0,
  "reasoning": "one sentence explanation"
}}""",
        ),
    ]
)

EXTRACTOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a knowledge extraction engine for a company brain. Extract structured facts,
entities, and a concise summary from the provided document.

Entity types you MUST use (no others):
- person: individual human being
- company: organization, startup, corporation, vendor
- project: named initiative, product, feature, codebase
- decision: a choice made or conclusion reached
- action_item: a task assigned to someone with or without a deadline
- concept: technical concept, methodology, framework

Be precise and extract only what is explicitly stated. Do not infer or hallucinate.
Respond ONLY with valid JSON.""",
        ),
        (
            "human",
            """Extract structured knowledge from this document.

SOURCE: {source}
AUTHOR: {author}
SUBJECT: {subject}
CONTENT:
{content}

Respond with JSON:
{{
  "summary": "2-3 sentence summary of the key points",
  "entities": [
    {{"name": "entity name", "type": "person|company|project|decision|action_item|concept"}}
  ],
  "key_facts": [
    "fact 1",
    "fact 2"
  ]
}}

Rules:
- summary: 2-3 sentences maximum, focus on decisions and outcomes
- entities: extract all named entities, 10 max
- key_facts: concrete, specific facts only, 10 max""",
        ),
    ]
)

FIX_JSON_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Fix the following malformed JSON and return only the corrected JSON object. "
            "Do not add any explanation.",
        ),
        ("human", "Malformed JSON:\n{malformed_json}"),
    ]
)
