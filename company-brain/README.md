# Company Brain (VIKI MVP)

A persistent, always-on context layer for your company — powered by [GBrain](https://github.com/garrytan/gbrain) and [LangGraph](https://langchain-ai.github.io/langgraph/). VIKI ingests Gmail and Notion, extracts memory-worthy facts using an LLM pipeline, stores structured knowledge in GBrain's hybrid search engine, and injects relevant context into any LangGraph agent on demand.

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | ≥ 3.11 |
| [Bun](https://bun.sh) | ≥ 1.0 |
| OpenAI API key | GPT-4o access |
| Gmail OAuth credentials | Google Cloud Console |
| Notion Integration token | Notion developer portal |

---

## Setup

### 1. Clone and install Python dependencies

```bash
git clone <repo-url> company-brain && cd company-brain
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in OPENAI_API_KEY, GMAIL_*, NOTION_* at minimum
```

### 3. Install and start GBrain

```bash
bash scripts/setup_gbrain.sh
```

This installs Bun + GBrain, initialises a local PGLite brain, runs `gbrain doctor`, and starts the HTTP MCP server on port 3721.

Verify: open http://localhost:3721/admin

### 4. Authenticate Gmail

```bash
uvicorn src.api.main:app --port 8000
# Then open: http://localhost:8000/auth/gmail
# Complete the OAuth consent screen — token is saved to ~/.config/company-brain/
```

### 5. Run your first ingestion

```bash
# Dry run — see what would be stored without writing
python scripts/run_ingestion.py --source gmail --hours 24 --dry-run

# Live run — ingest and store in GBrain
python scripts/run_ingestion.py --source gmail --hours 24
```

### 6. Query the brain

```bash
gbrain search "recent decisions"
gbrain think "what decisions were made this week?"
```

---

## Project Structure

```
company-brain/
├── src/
│   ├── config.py               # Pydantic settings — all config from .env
│   ├── connectors/
│   │   ├── base.py             # Abstract BaseConnector + RawDocument
│   │   ├── gmail.py            # Gmail connector (OAuth 2.0, filters noise)
│   │   └── notion.py           # Notion connector (blocks → markdown)
│   ├── pipeline/
│   │   ├── state.py            # LangGraph ExtractionState TypedDict
│   │   ├── prompts.py          # ChatPromptTemplate definitions
│   │   ├── nodes.py            # classify, extract, deduplicate, write nodes
│   │   └── graph.py            # StateGraph wiring + conditional edges
│   ├── gbrain_client/
│   │   ├── mcp_client.py       # HTTP JSON-RPC client for GBrain MCP tools
│   │   ├── page_builder.py     # Builds frontmatter + markdown for put_page
│   │   └── context_injector.py # inject_context() + make_context_node()
│   ├── api/
│   │   └── main.py             # FastAPI: OAuth callbacks, /ingest, /brain/*
│   └── scheduler/
│       └── cron.py             # APScheduler: 30min ingest, 5min health check
├── tests/                      # pytest test suite (mocked)
├── scripts/
│   ├── setup_gbrain.sh         # One-shot GBrain install + server start
│   └── run_ingestion.py        # Manual ingestion CLI with --dry-run
└── .env.example                # All required environment variables
```

---

## Architecture

```
Gmail / Notion
      │
      ▼
[BaseConnector.fetch()] → RawDocument
      │
      ▼
[LangGraph Pipeline]
  classify_node   →  is this worth remembering? (LLM, threshold gate)
  extract_node    →  summary, entities, key_facts (LLM)
  deduplicate_node → brain_search() similarity check
  write_node      →  put_page() → GBrain stores + auto-links graph
      │
      ▼
GBrain (hybrid search + knowledge graph + MCP server)
      │
      ▼
[Any LangGraph Agent] ← inject_context() / make_context_node()
```

---

## Drop-in Context Injection for LangGraph Agents

```python
from src.gbrain_client.context_injector import make_context_node
from langgraph.graph import StateGraph

# Your agent state must have a field with the user's query
graph = StateGraph(dict)

# Add GBrain context retrieval as the first node
graph.add_node("fetch_context", make_context_node(query_field="user_input"))
graph.add_node("respond", your_response_node)

graph.set_entry_point("fetch_context")
graph.add_edge("fetch_context", "respond")

agent = graph.compile()

# Result will have `injected_context` and `injected_sources` populated
result = await agent.ainvoke({"user_input": "what did we decide about the Q2 budget?"})
print(result["injected_context"])
```

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Background Sync (Production)

The scheduler runs automatically when you start the API:

```python
# src/api/main.py starts APScheduler on startup
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

- **Every 30 minutes**: ingests all sources, runs extraction pipeline
- **Every 5 minutes**: health-checks GBrain + connectors

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | System health (GBrain + connectors) |
| GET | `/auth/gmail` | Redirect to Gmail OAuth |
| GET | `/auth/gmail/callback` | OAuth callback handler |
| POST | `/ingest/run?hours=N` | Trigger manual ingestion |
| GET | `/brain/search?q=...` | Proxy to GBrain hybrid search |
| GET | `/brain/think?q=...` | Proxy to GBrain synthesis |
| GET | `/brain/stats` | Ingestion stats + source health |

---

## What GBrain Handles (Don't Rebuild)

- Vector storage + BM25 + hybrid RRF search
- Knowledge graph auto-extraction and edge creation
- Admin dashboard at `/admin`
- Dream cycle / enrichment (43 built-in skills)
- Deduplication scoring via `brain_search` similarity

VIKI's job is purely the **ingestion and extraction layer** on top of GBrain.
