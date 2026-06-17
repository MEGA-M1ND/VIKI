# Architecture

Company Brain is a **context layer for AI agents**. It ingests data from tools
(Gmail, Notion, Slack), extracts durable facts, stores them in a retrievable
memory system, and injects relevant context into downstream agents.

## Pipeline

```
┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐
│ Connectors │──▶│ Ingestion  │──▶│   Memory   │──▶│  Context   │
│  (fetch)   │   │ (extract)  │   │  (store)   │   │ (inject)   │
└────────────┘   └────────────┘   └────────────┘   └────────────┘
  RawDocument     ExtractedFact     MemoryRecord    RetrievalResult
```

Each arrow is a typed boundary (see `app/models/`). Each stage is replaceable
behind an interface.

## Layers & responsibilities

| Package          | Responsibility                                              | Status (MVP) |
|------------------|-------------------------------------------------------------|--------------|
| `app/models`     | Domain vocabulary: documents, facts, memory, retrieval.     | Implemented  |
| `app/connectors` | Fetch + normalize source data → `RawDocument`.              | Interface    |
| `app/ingestion`  | Extract durable facts from documents.                       | Interface    |
| `app/memory`     | Persist + retrieve `MemoryRecord`s (tenant-scoped).         | Interface + in-memory ref impl |
| `app/context`    | Retrieve relevant memory and render injectable context.     | Implemented (non-LLM) |
| `app/graphs`     | LangGraph orchestration of the pipeline (no business logic).| Implemented  |
| `app/prompts`    | Versioned LLM prompt templates.                             | Placeholder  |
| `app/services`   | Composition root (`ServiceContainer`) + use-case services.  | Implemented  |
| `app/api`        | FastAPI routers, schemas, error mapping.                    | Health/ready |
| `app/core`       | Config, logging, exception hierarchy.                       | Implemented  |
| `app/utils`      | Small dependency-free helpers.                              | Implemented  |

## Key design choices

- **Interfaces over implementations.** `MemoryStore`, `BaseConnector`,
  `BaseExtractor`, and `ContextProvider` are abstract. The in-memory store and
  memory-backed context provider exist so the system runs end-to-end today;
  pgvector/GBrain slot in behind the same contracts.
- **Separation of concerns.** Connectors only fetch. Extraction only extracts.
  Memory only persists/retrieves. Context only formats. Orchestration lives in
  `app/graphs`, wiring in `app/services`.
- **Multi-tenancy is structural, not bolted-on.** Every model and store
  operation carries `tenant_id`. Single-tenant MVP just uses the default tenant.
- **Composition root.** `ServiceContainer.build()` is the single place that
  chooses concrete implementations; the API depends only on interfaces.
- **Typed boundaries.** Pydantic domain models reject unknown fields to catch
  mapping bugs early; API schemas are separate from domain models.

## What is intentionally not built yet

- Connector business logic (OAuth flows, API calls).
- LLM prompts and the concrete extractor.
- Real persistence backends (pgvector, GBrain) and embeddings.

These are isolated behind the interfaces above and can be added without
reshaping the codebase.
