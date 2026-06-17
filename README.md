# VIKI — Company Brain

**VIKI** is a persistent, always-on context layer for AI agents. It watches your company's communication tools (Gmail, Notion, Slack), extracts durable facts and decisions using an LLM pipeline, stores structured knowledge in a retrievable memory system, and injects relevant context into any LangGraph agent on demand.

> "What you need to know, when you need to know it."

---

## What's in this repository

```
VIKI/
├── company-brain/    # Phase 1 MVP — GBrain-coupled, fully end-to-end
└── company-brain-v2/ # Phase 2 — clean, storage-agnostic architecture
```

The two sub-projects are **complementary, not competing**:

| | `company-brain/` | `company-brain-v2/` |
|---|---|---|
| **Purpose** | Prove the concept end-to-end against a real backend | Clean, interface-first architecture for production |
| **Storage** | [GBrain](https://github.com/garrytan/gbrain) (hybrid search + knowledge graph) | Pluggable — in-memory now, pgvector/GBrain slot in |
| **LLM pipeline** | 4-node LangGraph (classify → extract → dedupe → write) | Same pipeline, fully implemented behind provider interface |
| **Connectors** | Gmail + Notion (OAuth, full API logic) | Gmail + Notion (same logic, cleaner interface) |
| **API** | FastAPI + APScheduler | FastAPI + APScheduler + full CRUD |
| **Tests** | 49 tests | 46 tests |
| **Status** | Working MVP, GBrain dependency | Production-leaning scaffold |

---

## How VIKI works

```
 Gmail / Notion / Slack
         │
         ▼
  [Connector.fetch()]         →  RawDocument
         │
         ▼
  [LangGraph Pipeline]
    classify_node             →  is this worth remembering? (LLM gate)
    extract_node              →  facts, entities, triple (LLM)
    dedupe_node               →  skip if already in memory
    write_node                →  persist to memory store
         │
         ▼
  [Memory Store]              →  MemoryRecord (tenant-scoped)
         │
         ▼
  [Context Provider]          →  ranked retrieval + rendered context block
         │
         ▼
  [Any LangGraph Agent]       ←  injected_context, injected_sources
```

Every stage is behind a typed interface. Swap storage backends, LLM providers, or connectors without touching orchestration.

---

## Quick start

### Option A — Phase 1 (GBrain-backed MVP)

Requires Bun + GBrain running locally.

```bash
cd company-brain
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # fill in OPENAI_API_KEY, GMAIL_*, NOTION_*
bash scripts/setup_gbrain.sh  # installs Bun, starts GBrain on port 3721
uvicorn src.api.main:app --port 8000
# then: http://localhost:8000/auth/gmail  →  complete OAuth
python scripts/run_ingestion.py --source gmail --hours 24
```

### Option B — Phase 2 (clean scaffold, no external deps)

```bash
cd company-brain-v2
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # all defaults work for local dev
python scripts/smoke.py       # end-to-end sanity check (no network)
make run-api                  # boots on :8000
```

---

## Inject company memory into any LangGraph agent

**Phase 1 (GBrain):**
```python
from src.gbrain_client.context_injector import make_context_node
from langgraph.graph import StateGraph

graph = StateGraph(dict)
graph.add_node("fetch_context", make_context_node(query_field="user_input"))
graph.add_node("respond", your_response_node)
graph.set_entry_point("fetch_context")
graph.add_edge("fetch_context", "respond")
agent = graph.compile()

result = await agent.ainvoke({"user_input": "what did we decide about Q2 budget?"})
print(result["injected_context"])
```

**Phase 2 (storage-agnostic):**
```python
from app.graphs.context_graph import make_context_node, DefaultContextAssembler
from app.memory.in_memory import InMemoryStore  # swap for pgvector, GBrain, etc.

store = InMemoryStore()
assembler = DefaultContextAssembler()
context_node = make_context_node(store, assembler)

# Drop it as a node in any LangGraph graph
graph.add_node("inject_context", context_node)
```

---

## Key components

### Domain models (`app/models/`)

| Model | Description |
|-------|-------------|
| `RawDocument` | Normalized content from a source connector |
| `ExtractedFact` | Durable atomic fact (with subject/predicate/object triple, tags, validity) |
| `MemoryRecord` | Persisted, retrievable unit of knowledge |
| `RetrievalResult` | Ranked match from a memory query |
| `Ok[T]` / `Err` | Typed success/failure envelopes for service boundaries |

### Connectors (`app/connectors/`)

| Connector | Source | Auth |
|-----------|--------|------|
| `GmailConnector` | Gmail | OAuth 2.0, token cached at `~/.config/company-brain/gmail_token.json` |
| `NotionConnector` | Notion databases | Integration token, blocks → Markdown |

### LLM pipeline (`app/graphs/`)

| Node | Input | Output |
|------|-------|--------|
| `classify` | RawDocument | `is_worth_remembering`, confidence |
| `extract` | RawDocument | `ExtractedFact` list (triples, tags, entities) |
| `dedupe` | ExtractedFact list | Filtered list (exact + semantic dedup) |
| `write` | Filtered facts | `MemoryRecord` list (failed → `failed_writes.jsonl`) |

### API endpoints (`company-brain-v2`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness |
| `GET` | `/ready` | Readiness (probes memory store) |
| `POST` | `/ingest/run` | Trigger ingestion for a source |
| `GET` | `/ingest/status` | Last run stats per source |
| `POST` | `/context/query` | Retrieve + format context for a query |
| `GET` | `/memories` | List memory records for a tenant |
| `GET` | `/memories/{id}` | Fetch a single record |
| `DELETE` | `/memories/{id}` | Delete a record |

### Scheduler

APScheduler runs in the same event loop as FastAPI:
- **Every 30 min** — incremental ingestion across all configured connectors
- **Every 5 min** — memory store health check

---

## Environment variables

All settings use the `CB_` prefix and are loaded from `.env`.

| Variable | Default | Description |
|---|---|---|
| `CB_LLM_API_KEY` | | OpenAI API key |
| `CB_LLM_MODEL` | `gpt-4o-mini` | Chat model |
| `CB_GMAIL_CLIENT_ID` | | Gmail OAuth client ID |
| `CB_GMAIL_CLIENT_SECRET` | | Gmail OAuth client secret |
| `CB_NOTION_API_KEY` | | Notion integration token |
| `CB_NOTION_DATABASE_IDS` | | Comma-separated database IDs |
| `CB_MEMORY_BACKEND` | `in_memory` | `in_memory` \| `pgvector` \| `gbrain` |
| `CB_INGESTION_SCHEDULE_MINUTES` | `30` | Scheduler interval |
| `CB_CLASSIFIER_CONFIDENCE_THRESHOLD` | `0.5` | Min LLM confidence to proceed |

Full list: see `company-brain-v2/.env.example`.

---

## Development

```bash
# company-brain-v2
make install      # install + dev deps
make lint         # ruff check
make typecheck    # mypy (61 source files, zero errors)
make test         # pytest (46 tests)
make run-api      # uvicorn with reload

# Or use the scripts directly
bash scripts/setup_dev.sh
python scripts/smoke.py
python scripts/run_ingestion.py --source gmail --hours 24 --dry-run
```

---

## Architecture decisions

- **Interfaces over implementations** — `MemoryStore`, `BaseConnector`, `BaseExtractor`, `LLMProvider`, and `ContextProvider` are all abstract. Swap without touching orchestration.
- **Async generators for connectors** — `fetch_documents()` yields `RawDocument`s lazily, keeping memory bounded for large mailboxes.
- **Dead-letter queue** — facts that fail to write land in `failed_writes.jsonl` instead of being silently dropped.
- **Tenant-first** — every model, store operation, and API call carries `tenant_id`. Multi-tenancy is structural, not bolted on.
- **Composition root** — `ServiceContainer.build()` is the single place that wires concrete implementations; everything else depends on interfaces.
- **No framework DI** — dependencies are explicit dataclass fields on `ServiceContainer`. Simple, readable, testable.

---

## Roadmap

- [ ] pgvector memory backend with real embeddings
- [ ] Slack connector
- [ ] Incremental sync cursor (avoid re-fetching old documents)
- [ ] Streaming context injection (SSE)
- [ ] Multi-tenant authentication (JWT / API key per tenant)
- [ ] GBrain memory backend for Phase 2 (hybrid search + knowledge graph)
- [ ] Evaluation harness for extraction quality

---

## License

Proprietary.
