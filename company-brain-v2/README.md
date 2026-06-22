# Company Brain v2

A **context layer for AI agents** — clean, interface-first, and storage-agnostic. Company Brain ingests data from Gmail and Notion, extracts durable facts using an LLM pipeline, stores them in a retrievable memory system, and injects relevant context into downstream agents across sessions.

This is the production-leaning implementation: typed domain models, LangGraph orchestration, pluggable backends, full REST API, and background scheduling — with the in-memory store as the default (no external deps to run locally).

---

## Quickstart

> Requires **Python 3.11+**. [`uv`](https://docs.astral.sh/uv/) is preferred; plain `pip` works too.

```bash
# 1. Install
bash scripts/setup_dev.sh    # creates .venv, installs deps, copies .env.example

# 2. Edit .env (optional — all defaults boot without changes)
#    Add CB_LLM_API_KEY for the full LLM pipeline
#    Add CB_GMAIL_* / CB_NOTION_* for connectors

# 3. Verify everything works
python scripts/smoke.py      # end-to-end test (fake extractor, in-memory store)
make test                    # 46 tests

# 4. Boot the API
make run-api                 # http://localhost:8000
```

```bash
curl localhost:8000/health   # liveness
curl localhost:8000/ready    # readiness (probes memory store)
open localhost:8000/docs     # OpenAPI UI
```

---

## Make targets

| Command          | Description                              |
|------------------|------------------------------------------|
| `make install`   | Install the project and dev dependencies |
| `make format`    | Auto-format + autofix with ruff          |
| `make lint`      | Lint and format-check                    |
| `make typecheck` | Static type check with mypy              |
| `make test`      | Run the pytest suite (46 tests)          |
| `make run-api`   | Run the FastAPI app with reload          |
| `make clean`     | Remove caches and build artifacts        |

---

## Running ingestion

```bash
# Dry run — authenticate and fetch, but skip persistence
python scripts/run_ingestion.py --source gmail --hours 24 --dry-run

# Live run — full pipeline (needs CB_LLM_API_KEY + Gmail credentials)
python scripts/run_ingestion.py --source notion --hours 48

# All sources
python scripts/run_ingestion.py --source all --hours 24
```

---

## API reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness — always 200 |
| `GET` | `/ready` | Readiness — probes memory store |
| `POST` | `/ingest/run` | Trigger an ingestion run for a source |
| `GET` | `/ingest/status` | Last-run stats per source |
| `POST` | `/context/query` | Retrieve and render context for a query |
| `GET` | `/memories` | List memory records (filterable by query) |
| `GET` | `/memories/{id}` | Fetch a single memory record |
| `DELETE` | `/memories/{id}` | Delete a memory record |

Full schema at `localhost:8000/docs` when the API is running.

---

## Project layout

```
company-brain-v2/
├── app/
│   ├── api/
│   │   ├── deps.py              # FastAPI dependency providers
│   │   ├── errors.py            # Domain error → HTTP status mapping
│   │   ├── routes_health.py     # GET /health, GET /ready
│   │   ├── routes_ingest.py     # POST /ingest/run, GET /ingest/status
│   │   ├── routes_context.py    # POST /context/query
│   │   └── routes_memory.py     # GET/DELETE /memories/{id}
│   ├── connectors/
│   │   ├── base.py              # BaseConnector ABC (async generator interface)
│   │   ├── gmail.py             # Gmail connector (OAuth 2.0, async generator)
│   │   └── notion.py            # Notion connector (blocks → Markdown)
│   ├── context/
│   │   ├── base.py              # ContextProvider ABC
│   │   └── provider.py          # MemoryContextProvider (non-LLM, scoring)
│   ├── core/
│   │   ├── config.py            # Pydantic Settings (CB_ prefix, .env)
│   │   ├── exceptions.py        # Exception hierarchy (CompanyBrainError → …)
│   │   └── logging.py           # structlog configuration
│   ├── graphs/
│   │   ├── state.py             # IngestionState, PipelineState, RetrievalState
│   │   ├── ingestion_graph.py   # Simple extract → persist graph
│   │   ├── pipeline_graph.py    # Full classify → extract → dedupe → write
│   │   ├── context_graph.py     # retrieve → assemble context-injection graph
│   │   └── nodes/
│   │       ├── classify.py      # LLM classification node
│   │       ├── extract.py       # LLM fact extraction node
│   │       ├── dedupe.py        # Deduplication node (key + similarity)
│   │       └── write.py         # Persistence node (+ dead-letter file)
│   ├── ingestion/
│   │   ├── base.py              # BaseExtractor ABC
│   │   └── orchestrator.py      # IngestionOrchestrator + IngestionStats
│   ├── llm/
│   │   ├── base.py              # LLMProvider ABC
│   │   ├── openai.py            # ChatOpenAI-backed provider
│   │   └── fake.py              # FakeLLMProvider, SequentialLLMProvider
│   ├── memory/
│   │   ├── base.py              # MemoryStore ABC
│   │   ├── factory.py           # build_memory_store(settings)
│   │   └── in_memory.py         # InMemoryStore (dev/test reference impl)
│   ├── models/
│   │   ├── common.py            # SourceType, FactType, EntityType, ValidityKind
│   │   ├── documents.py         # RawDocument
│   │   ├── facts.py             # ExtractedFact, EntityRef (with triple fields)
│   │   ├── memory.py            # MemoryRecord
│   │   ├── results.py           # Ok[T] / Err result envelopes
│   │   └── retrieval.py         # RetrievalQuery, RetrievalResult
│   ├── prompts/
│   │   ├── classification.py    # Classifier prompt + message builder
│   │   └── extraction.py        # Extractor prompt + message builder
│   ├── scheduler/
│   │   └── cron.py              # APScheduler wrapper (ingest + health jobs)
│   ├── services/
│   │   ├── container.py         # ServiceContainer — composition root
│   │   ├── health.py            # HealthService (liveness + readiness)
│   │   ├── interfaces.py        # MemoryWriter, MemoryRetriever, ContextAssembler … Protocols
│   │   └── retrieval.py         # RetrievalService (facade + timing logs)
│   ├── utils/
│   │   └── ids.py               # new_id(), utcnow()
│   └── main.py                  # FastAPI entrypoint + app factory
├── scripts/
│   ├── smoke.py                 # End-to-end test (no network, fake extractor)
│   ├── run_ingestion.py         # Ingestion CLI (--source, --hours, --dry-run)
│   ├── setup_dev.sh             # One-shot dev setup
│   ├── run_api.sh               # Start API server
│   └── run_full_demo.sh         # Smoke + tests + API boot demo
├── tests/
│   ├── conftest.py              # settings + TestClient fixtures
│   ├── test_config.py           # Settings validation
│   ├── test_connectors.py       # Gmail + Notion connector tests (mocked)
│   ├── test_context_graph.py    # Context graph + assembler tests
│   ├── test_health.py           # Health/ready endpoint tests
│   ├── test_models.py           # Domain model validation
│   ├── test_pipeline.py         # Simple ingestion graph end-to-end
│   └── test_pipeline_graph.py   # Full classify→extract→dedupe→write tests
├── docs/
│   └── architecture.md          # Design rationale + layer responsibilities
├── .env.example                 # All config keys with comments
├── Makefile
└── pyproject.toml               # Deps + ruff + mypy + pytest config
```

---

## System overview

```
Connectors ──▶ Ingestion ──▶ Memory ──▶ Context
 (fetch)        (extract)    (store)   (inject)
RawDocument  ExtractedFact  MemoryRecord  RetrievalResult
```

### Pipeline in detail

```
[Connector.fetch_documents()]
        │   async generator of RawDocument
        ▼
[IngestionOrchestrator.run()]
        │   passes each doc to the LangGraph pipeline
        ▼
[build_pipeline_graph(llm, store)]
  ┌─────────────────────────────────┐
  │ classify_node                   │  LLM decides: worth storing?
  │   → is_worth_remembering        │  (short-circuits if no)
  │ extract_node                    │  LLM extracts facts + triples
  │   → ExtractedFact list          │  (subject, predicate, object, tags)
  │ dedupe_node                     │  key hash + similarity check
  │   → new_facts (filtered)        │  (skips already-known facts)
  │ write_node                      │  persists to MemoryStore
  │   → MemoryRecord list           │  (failures → failed_writes.jsonl)
  └─────────────────────────────────┘
        │
        ▼
[MemoryStore]                        ←── tenant-scoped, pluggable backend
        │
        ▼
[ContextProvider / context graph]    ←── retrieval + Markdown rendering
        │
        ▼
[LangGraph Agent]  ←  injected_context, injected_sources
```

---

## Drop-in context injection

```python
from app.graphs.context_graph import make_context_node, DefaultContextAssembler
from app.memory.in_memory import InMemoryStore
from langgraph.graph import StateGraph

store = InMemoryStore()
assembler = DefaultContextAssembler()

# Embed in any agent graph
graph = StateGraph(dict)
graph.add_node("inject_context", make_context_node(store, assembler))
graph.add_node("respond", your_response_node)
graph.set_entry_point("inject_context")
graph.add_edge("inject_context", "respond")
agent = graph.compile()

result = await agent.ainvoke({
    "tenant_id": "acme",
    "user_query": "what did we decide about the Q2 budget?",
})
print(result["injected_context"])
```

---

## Configuration

All variables are prefixed `CB_` and loaded from `.env` (see `.env.example` for the full list):

| Variable | Default | Description |
|---|---|---|
| `CB_APP_ENV` | `local` | `local` \| `dev` \| `staging` \| `prod` |
| `CB_LLM_API_KEY` | | OpenAI API key |
| `CB_LLM_MODEL` | `gpt-4o-mini` | Chat model |
| `CB_GMAIL_CLIENT_ID` | | Gmail OAuth client ID |
| `CB_GMAIL_CLIENT_SECRET` | | Gmail OAuth client secret |
| `CB_NOTION_API_KEY` | | Notion integration token |
| `CB_NOTION_DATABASE_IDS` | | Comma-separated Notion database IDs |
| `CB_MEMORY_BACKEND` | `in_memory` | `in_memory` \| `pgvector` \| `gbrain` |
| `CB_INGESTION_SCHEDULE_MINUTES` | `30` | Scheduler ingest interval |
| `CB_HEALTH_CHECK_SCHEDULE_MINUTES` | `5` | Scheduler health-check interval |
| `CB_CLASSIFIER_CONFIDENCE_THRESHOLD` | `0.5` | Min LLM confidence to proceed |
| `CB_RETRIEVAL_DEFAULT_LIMIT` | `5` | Default retrieval results |

---

## Testing

```bash
make test          # 46 tests, all fast (no network, no LLM)
make typecheck     # mypy — 61 source files, 0 errors
make lint          # ruff — 0 warnings
```

The test suite uses `FakeLLMProvider` / `SequentialLLMProvider` to script LLM responses, and `InMemoryStore` for persistence — no external services required.

---

## Adding a real memory backend

Implement `MemoryStore` and register it in `app/memory/factory.py`:

```python
class PgVectorStore(MemoryStore):
    async def write(self, record: MemoryRecord) -> MemoryRecord: ...
    async def query(self, query: RetrievalQuery) -> list[RetrievalResult]: ...
    async def get(self, *, tenant_id: str, record_id: str) -> MemoryRecord | None: ...
    async def delete(self, *, tenant_id: str, record_id: str) -> bool: ...
    async def health_check(self) -> bool: ...
```

Set `CB_MEMORY_BACKEND=pgvector` and `CB_MEMORY_DSN=postgresql://...` — no other changes needed.

## Adding a real LLM extractor

Implement `LLMProvider` or use `OpenAIProvider` directly:

```python
from app.llm.openai import OpenAIProvider
from app.graphs.pipeline_graph import build_pipeline_graph

llm = OpenAIProvider(model="gpt-4o-mini")
graph = build_pipeline_graph(llm, store)
```

---

## Multi-tenancy and required headers (Phase 3)

All VC routes require a tenant identifier. Provide it via:

- **HTTP header**: `X-Tenant-ID: <tenant>` (preferred for API clients)
- **Query param**: `?tenant_id=<tenant>` (accepted everywhere; existing tests use this)

Without a tenant identifier, VC routes return **400 Bad Request**.  
Invalid format (only `[a-zA-Z0-9_-]{1,64}` accepted) also returns **400**.

### Rate limits

| Path prefix | Limit | Window |
|-------------|-------|--------|
| `/ingest`   | 100 req | 60 s |
| `/ask`      | 60 req  | 60 s |
| `/vc`       | 120 req | 60 s |

When exceeded, the API returns **429** with a `Retry-After` header.

---

## Retrieval evaluation (`make eval`)

```bash
make eval
# Runs: python -m app.eval.runner --output eval_results/
```

Seeds an in-memory store with golden records, issues 3 natural-language
queries, and writes a timestamped JSON report to `eval_results/`.

**Reading the report** (`eval_results/YYYY-MM-DD_HH-MM.json`):

| Field                | Meaning                                                   |
|----------------------|-----------------------------------------------------------|
| `precision_at_5`     | Fraction of top-5 results that matched expected companies |
| `mrr`                | Reciprocal rank of first correct hit (0 if none in top-5) |
| `noise_rate`         | Fraction of top-5 that contained noise patterns           |
| `temporal_respected` | True if the temporal cutoff was extracted and applied     |
| `latency_ms`         | Wall-clock retrieval latency in milliseconds              |

The `summary` block gives means across all cases.

---

## Design principles

- **Interfaces over implementations** — every major role is an ABC or Protocol. Swap without touching orchestration.
- **Async generators for connectors** — `fetch_documents()` yields lazily; bounded memory even for large mailboxes.
- **Dead-letter queue** — facts that fail to write land in `failed_writes.jsonl`, never silently dropped.
- **Tenant-first** — `tenant_id` is structural in every model and store operation.
- **Composition root** — `ServiceContainer.build()` is the only place that chooses implementations.
- **No framework DI** — dependencies are explicit dataclass fields. Simple, readable, testable.
