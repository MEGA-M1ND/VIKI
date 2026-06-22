# Architecture

Company Brain is a **context layer for AI agents**. It ingests data from tools (Gmail, Notion, Slack), extracts durable facts, stores them in a retrievable memory system, and injects relevant context into downstream agents.

---

## Pipeline

```
┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐
│ Connectors │──▶│ Ingestion  │──▶│   Memory   │──▶│  Context   │
│  (fetch)   │   │ (extract)  │──▶│  (store)   │   │ (inject)   │
└────────────┘   └────────────┘   └────────────┘   └────────────┘
  RawDocument     ExtractedFact     MemoryRecord    RetrievalResult
```

Each arrow is a typed boundary (see `app/models/`). Each stage is replaceable behind an interface.

---

## Layers and responsibilities

| Package | Responsibility | Implementation |
|---|---|---|
| `app/models` | Domain vocabulary: documents, facts, memory, retrieval, results | Fully implemented |
| `app/connectors` | Fetch + normalize source data → `RawDocument` | Gmail + Notion implemented |
| `app/ingestion` | Extract durable facts + orchestrate pipeline runs | Implemented (`IngestionOrchestrator`) |
| `app/llm` | LLM provider abstraction | `OpenAIProvider` + fakes for tests |
| `app/prompts` | Versioned LLM prompt templates | Classification + extraction prompts |
| `app/memory` | Persist + retrieve `MemoryRecord`s (tenant-scoped) | Interface + `InMemoryStore` ref impl |
| `app/context` | Retrieve relevant memory and render injectable context | Implemented (`MemoryContextProvider`) |
| `app/graphs` | LangGraph orchestration (no business logic) | Simple + full pipeline + context graph |
| `app/services` | Composition root + use-case services | `ServiceContainer`, `RetrievalService`, Protocols |
| `app/scheduler` | Background periodic ingestion + health checks | `Scheduler` (APScheduler wrapper) |
| `app/api` | FastAPI routers, schemas, error mapping | Full CRUD + ingest + context routes |
| `app/core` | Config, logging, exception hierarchy | Implemented |
| `app/utils` | Small dependency-free helpers | Implemented |

---

## LangGraph graphs

### Simple ingestion graph (`app/graphs/ingestion_graph.py`)

For use with any `BaseExtractor` implementation (no LLM required):

```
extract_node  ──(has facts?)──▶  persist_node  ──▶  END
                     │
                    (no)
                     ▼
                    END
```

### Full pipeline graph (`app/graphs/pipeline_graph.py`)

LLM-backed classify → extract → dedupe → write:

```
classify_node ──(worth it?)──▶ extract_node ──(has facts?)──▶ dedupe_node ──(new facts?)──▶ write_node ──▶ END
       │                              │                              │
      (no)                           (no)                          (no)
       ▼                              ▼                              ▼
      END                            END                            END
```

All conditional edges short-circuit so no work is done unnecessarily.

### Context graph (`app/graphs/context_graph.py`)

Retrieve + assemble context for agent injection:

```
retrieve_node ──▶ assemble_node ──▶ END
```

Also exposed as `make_context_node()` — a single async function that can be dropped into any agent graph as a node.

---

## Data model

### `ExtractedFact`

The core unit of extraction. Stores both a natural-language `statement` and a structured triple for graph-style reasoning:

```python
ExtractedFact(
    statement="Alice approved the Q2 infra budget of $500k.",
    subject="Alice",
    predicate="approved",
    object_="Q2 infra budget of $500k",
    tags=["budget", "q2", "infra"],
    fact_type=FactType.DECISION,
    validity_kind=ValidityKind.CURRENT,
    confidence=0.95,
)
```

### `MemoryRecord`

The persisted form. Includes a `dedupe_key` in `metadata` for exact-match deduplication, plus the triple fields for downstream use:

```python
MemoryRecord(
    content="Alice approved the Q2 infra budget of $500k.",
    record_type=FactType.DECISION,
    metadata={
        "dedupe_key": "a1b2c3...",
        "subject": "Alice",
        "predicate": "approved",
        "object": "Q2 infra budget of $500k",
        "tags": ["budget", "q2", "infra"],
        "validity_kind": "current",
        "confidence": 0.95,
    },
)
```

### `Ok[T]` / `Err` result envelopes

Service boundaries return typed results instead of raising across layers:

```python
result: Ok[MemoryRecord] | Err = await writer.safe_write(record)
if result.ok:
    use(result.value)
else:
    log(result.error, result.details)
```

---

## Key design choices

**Interfaces over implementations.**
`MemoryStore`, `BaseConnector`, `BaseExtractor`, `LLMProvider`, and `ContextProvider` are all abstract. The in-memory store and fake LLM exist so the system runs end-to-end in tests without any external dependencies; real backends slot in behind the same contracts.

**Async generators for connectors.**
`BaseConnector.fetch_documents()` is declared as an async generator (uses `yield`). Calling it returns the iterator directly — no `await` required, and memory stays bounded even for large mailboxes.

**Tenant-first.**
Every model and store operation carries `tenant_id`. Multi-tenancy is structural, not bolted on. Single-tenant MVP just uses `"default"`.

**Composition root.**
`ServiceContainer.build()` is the single place that chooses concrete implementations. Every other layer depends on interfaces. No framework DI — dependencies are explicit dataclass fields.

**Dead-letter queue.**
Facts that fail to write are serialised to `failed_writes.jsonl` instead of being silently dropped. The write node logs the failure, appends the fact, and continues rather than crashing the pipeline.

**Separation of concerns.**
- Connectors only fetch and normalise.
- Extractors only extract.
- Stores only persist and retrieve.
- Context providers only retrieve and format.
- Graphs only wire stages together.

Business logic never crosses these boundaries. Orchestration lives in `app/graphs`, wiring in `app/services`.

---

## Adding a real memory backend

Implement `MemoryStore` (`app/memory/base.py`) and register it in `app/memory/factory.py`:

```python
class MemoryBackend(StrEnum):
    IN_MEMORY = "in_memory"
    PGVECTOR = "pgvector"   # ← implement PgVectorStore
    GBRAIN = "gbrain"       # ← implement GBrainStore
```

Set `CB_MEMORY_BACKEND=pgvector` — no other code changes required.

## Adding a connector

Subclass `BaseConnector` in `app/connectors/`, implement `authenticate()`, `fetch_documents()` (as an async generator), and `health_check()`. Wire it into `ServiceContainer.connectors` at startup.
