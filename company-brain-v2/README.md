# Company Brain

A **context layer for AI agents**. Company Brain ingests data from tools like
Gmail, Notion, and Slack, extracts durable facts, preferences, and entities,
stores them in a retrievable memory system, and injects relevant context into
downstream agents so they remember user and company context across sessions.

This repository is a **production-leaning MVP scaffold**: clean interfaces, a
runnable end-to-end skeleton, and clear seams for adding connectors, an LLM
extractor, and a real memory backend.

---

## Quickstart

> Requires **Python 3.11+**. [`uv`](https://docs.astral.sh/uv/) is preferred;
> plain `pip` works too (the Makefile auto-detects).

```bash
# 1. (optional) create a virtualenv
python -m venv .venv && source .venv/bin/activate

# 2. install the project + dev tools
make install

# 3. copy and edit config (defaults boot with zero changes)
cp .env.example .env

# 4. run the checks
make lint
make test

# 5. boot the API
make run-api
```

Then:

```bash
curl localhost:8000/health    # liveness
curl localhost:8000/ready     # readiness (probes dependencies)
open  localhost:8000/docs     # OpenAPI docs
```

Run the no-network pipeline smoke test:

```bash
python scripts/smoke.py
```

---

## Make targets

| Command          | Description                              |
|------------------|------------------------------------------|
| `make install`   | Install the project and dev dependencies |
| `make format`    | Auto-format + autofix with ruff          |
| `make lint`      | Lint and format-check (no changes)       |
| `make typecheck` | Static type check with mypy              |
| `make test`      | Run the pytest suite                     |
| `make run-api`   | Run the FastAPI app with reload          |
| `make clean`     | Remove caches and build artifacts        |

---

## Project layout

```
company-brain/
├── app/
│   ├── api/          # FastAPI routers, schemas, deps, error mapping
│   ├── core/         # config (Pydantic Settings), logging (structlog), exceptions
│   ├── connectors/   # source connectors → RawDocument        (interface)
│   ├── ingestion/    # fact extraction from documents          (interface)
│   ├── memory/       # persist + retrieve MemoryRecord         (interface + in-memory ref)
│   ├── context/      # retrieve memory + render agent context  (implemented, non-LLM)
│   ├── graphs/       # LangGraph pipeline orchestration
│   ├── models/       # domain models: RawDocument, ExtractedFact, MemoryRecord, RetrievalResult
│   ├── prompts/      # LLM prompt templates                     (placeholder)
│   ├── services/     # composition root + use-case services
│   ├── utils/        # small helpers (ids, time)
│   └── main.py       # FastAPI entrypoint + app factory
├── scripts/          # local dev scripts (smoke test)
├── tests/            # pytest suite
├── docs/             # architecture notes
├── .env.example      # all config keys (prefix: CB_)
├── Makefile          # common commands
└── pyproject.toml    # deps + tooling config
```

---

## System overview

```
Connectors ─▶ Ingestion ─▶ Memory ─▶ Context
 (fetch)      (extract)    (store)   (inject)
RawDocument  ExtractedFact MemoryRecord RetrievalResult
```

- **Connectors** fetch and normalize source data into `RawDocument`s.
- **Ingestion** extracts durable `ExtractedFact`s from documents.
- **Memory** persists facts as `MemoryRecord`s and retrieves them by relevance,
  always scoped by tenant.
- **Context** retrieves relevant memory and renders an injectable context block
  for a downstream agent.

Every stage lives behind an interface, so implementations can be swapped without
touching the rest of the system. See [`docs/architecture.md`](docs/architecture.md)
for details and design rationale.

### What works today

- FastAPI app boots; `/health` and `/ready` respond.
- Typed settings, structured logging, and a domain exception hierarchy.
- A runnable end-to-end skeleton: `scripts/smoke.py` pushes a document through
  the ingestion graph into the in-memory store and renders injected context.

### Deliberately not implemented yet

- Connector business logic (OAuth, API calls).
- The LLM extractor and prompt templates.
- Real persistence backends (pgvector, GBrain) and embeddings.

These are isolated behind interfaces and can be added incrementally.
