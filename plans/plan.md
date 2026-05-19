# StructAI — Implementation Plan

## 1. Problem framing

Build a web app where users upload tabular files (CSV/TSV/XLSX/XLS), watch an AI agent analyze them, and end up with a **normalized PostgreSQL schema** plus a **reusable import script**. Combine **deterministic profiling** (cheap, exact, reproducible) with **LLM reasoning** (used only where judgment is needed: semantics, naming, normalization splits, ambiguity resolution).

The core principle: the LLM never touches raw data row-by-row. It receives compact, deterministic *summaries* and emits *decisions* (column meanings, type choices, transformations, table splits). Generated scripts are the durable artifact — code the user can read, version, edit, and rerun without the agent.

The **web UI is the primary surface**: a file manager for uploads, a chat sidebar for agent interaction and feedback, and a table browser over the resulting Postgres database.

## 2. Tech choices

| Concern | Choice | Why |
|---|---|---|
| Repo layout | **Monorepo** (`apps/api`, `apps/web`, `packages/core`) | Coordinated releases, shared OpenAPI types between backend and frontend |
| Backend language | Python 3.12 | Ecosystem (Polars, pandas, openpyxl, SQLAlchemy, LangChain) is unmatched here |
| Backend framework | **FastAPI** + `uvicorn` | Async, typed, OpenAPI for free, SSE-friendly |
| Backend pkg mgr | `uv` with workspaces | Single lockfile across the API and the shared core lib |
| Frontend | **React 18 + Vite + TypeScript** | Modern, fast dev loop |
| Frontend pkg mgr | `pnpm` workspaces | Native workspace support, fast |
| Data engine | **Polars** for profiling, **pandas** in generated scripts | Polars is fast and lazy; pandas is what users expect to read and edit |
| Excel | `openpyxl` (xlsx), `xlrd==1.2.0` (xls), `calamine` (fast fallback) | Covers the full xls/xlsx range |
| Database | **PostgreSQL 16** only | Real-world target; JSONB, rich types, schemas; ubiquitous |
| DB layer | SQLAlchemy 2.x + `asyncpg` | Typed ORM + async driver for the API; same SQLAlchemy used inside generated scripts |
| LLM | Anthropic `claude-opus-4-7` for inference, `claude-haiku-4-5` for routing | Strong tool use, Haiku for cheap fanout |
| Agent framework | **LangChain** (`langchain-anthropic`) with **LangGraph** for the loop | Built-in tool calling, callbacks, streaming, tracing |
| Realtime | Server-Sent Events from FastAPI to React | Streams agent tokens and tool calls into the chat sidebar |
| CLI (secondary) | `typer` | Power users can run the same flow headlessly |
| Tests (Python) | `pytest` + fixture files | Real CSV/XLSX in `tests/fixtures/` |
| Tests (TS) | `vitest` + React Testing Library | Same runtime as Vite |
| Lint/format | `ruff` (Python), `biome` (TS) | One tool each, fast |

## 3. Architecture

```
┌──────────────────────────────────────┐
│  apps/web — React + Vite + TS        │
│  ┌────────────────────────────────┐  │
│  │ File manager (uploads)         │  │
│  │ Chat sidebar (SSE stream)      │  │
│  │ Table browser (Postgres rows)  │  │
│  └────────────────────────────────┘  │
└────────────────┬─────────────────────┘
                 │ HTTP + SSE
                 ▼
┌──────────────────────────────────────┐
│  apps/api — FastAPI                  │
│  /files   /sessions   /scripts       │
│  /tables  /runs                      │
└────────────────┬─────────────────────┘
                 │ in-process
                 ▼
┌──────────────────────────────────────┐
│  packages/core                       │
│  sniff · profile · agent (LangGraph) │
│  schema (incl. normalize) · script   │
│  generator · executor · registry     │
└────────────────┬─────────────────────┘
                 ▼
          ┌──────────────┐
          │ PostgreSQL 16│
          └──────────────┘
```

### Module layout

```
structai/
├── pnpm-workspace.yaml
├── pyproject.toml                # uv workspace root
├── docker-compose.yml            # local Postgres
├── apps/
│   ├── api/                      # FastAPI service
│   │   ├── pyproject.toml
│   │   └── src/structai_api/
│   │       ├── main.py
│   │       ├── routes/
│   │       │   ├── files.py      # upload, list, get
│   │       │   ├── sessions.py   # agent runs, SSE stream
│   │       │   ├── scripts.py    # list, view, download
│   │       │   ├── runs.py       # execute a script
│   │       │   └── tables.py     # introspect Postgres, paginate rows
│   │       ├── stream.py         # SSE plumbing
│   │       └── deps.py
│   └── web/                      # React + Vite + TS
│       ├── package.json
│       ├── vite.config.ts
│       └── src/
│           ├── main.tsx
│           ├── App.tsx
│           ├── components/
│           │   ├── FileManager.tsx
│           │   ├── ChatSidebar.tsx
│           │   └── TableBrowser.tsx
│           └── api/              # OpenAPI-generated client
├── packages/
│   └── core/                     # the ingestion engine (Python)
│       ├── pyproject.toml
│       └── src/structai_core/
│           ├── io/{sniff,readers}.py
│           ├── profile/{columns,types,patterns}.py
│           ├── agent/{graph,tools,prompts,decisions}.py
│           ├── schema/{model,ddl,normalize}.py
│           ├── script/{templates,generator}.py
│           ├── execute/{runner,validate}.py
│           └── store/{registry,fingerprint}.py
└── tests/
    └── fixtures/
```

## 4. The deterministic profile

Before any LLM call, produce a compact JSON profile per file. Keep it small enough to fit in one prompt comfortably (target <30 KB).

For each column, capture:

- `name` (raw), `position`
- `inferred_type` (one of: `int`, `float`, `bool`, `date`, `datetime`, `string`, `enum`, `json`)
- `null_count`, `null_rate`
- `distinct_count`, `cardinality_class` (`unique` / `low` / `high`)
- `min`, `max` (for ordered types)
- 5 `sample_values` (drawn to maximize diversity, not just head — raw values, no PII redaction)
- `pattern_hits`: list like `["iso_date", "email"]` from regex matchers
- `format_examples`: a couple of literal samples for any detected format

File-level: row count, encoding, delimiter, has_header, sheet name (xlsx), file hash.

This profile is the contract between deterministic land and the LLM.

## 5. The agent loop

A LangGraph state machine with `langchain-anthropic`. Tools the agent can call:

| Tool | Purpose |
|---|---|
| `get_column_samples(column, n, strategy)` | More samples (`random`, `nulls`, `extremes`, `regex_match`) |
| `count_values(column, where=None)` | Cardinality, top-K values |
| `match_regex(column, pattern)` | Test a hypothesis ("are these all phone numbers?") |
| `cross_tab(col_a, col_b)` | Detect functional dependency for normalization splits |
| `parse_as(column, target_type)` | Try parsing and report failure rate |
| `propose_schema(tables)` | Submit the final decision (may contain multiple tables with FKs) |

The agent's job: starting from the profile, ask targeted questions via tools until it can commit to a `propose_schema` call. The schema submission is a strongly-typed pydantic object — a list of `Table`s, each with `Column`s (target SQL type, nullable, PK/unique, transformation rule, semantic label, comment) plus `ForeignKey` relations between tables when the agent decides to normalize. No free-form output goes downstream.

**Multi-table normalization from a single file:** the agent can recognize when one source file logically contains multiple entities (e.g., orders + customers, or events + event-types) and emit a multi-table schema with FK relations. Decision is driven by `cross_tab` and `count_values` evidence, not just intuition.

**Why tools, not a big prompt:** type inference is cheap, the agent only needs *judgment* — which column is the natural key, which two text columns are really the same enum, whether a column should split off into its own table. Tools let the model verify hypotheses against the actual data without us pre-computing everything.

**Streaming to the UI:** LangGraph callbacks emit events on the SSE channel — `tool_call_start`, `tool_call_result`, `message_delta`, `schema_proposed`. The chat sidebar renders them live.

## 6. Script generation

Generated scripts are **standalone, runnable Python files** — not opaque agent artifacts. A user should be able to open one, read it top to bottom, edit a transformation, and rerun it without the agent.

For a multi-table normalization the generator emits one `import.py` that loads tables in FK-dependency order, plus a sibling `schema.sql`.

Template structure (Jinja2):

```python
"""
Generated by structai for: customers_2024.csv
Source SHA256: ...
Target: postgresql://.../warehouse
Tables: customers, addresses
"""
import pandas as pd
from sqlalchemy import create_engine

SOURCE = "customers_2024.csv"

def split_and_transform(df):
    # agent decided to normalize addresses out of the main table
    df = df.rename(columns={...})
    df["signup_date"] = pd.to_datetime(df["signup_date"], format="%Y-%m-%d", errors="coerce")
    df["country"] = df["country"].str.upper().str.strip()

    addresses = (
        df[["address_line1", "city", "country", "postal_code"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    addresses["address_id"] = addresses.index + 1

    customers = df.merge(addresses, on=["address_line1", "city", "country", "postal_code"])[
        ["customer_id", "email", "signup_date", "address_id"]
    ]
    return {"addresses": addresses, "customers": customers}

def main(engine_url):
    df = pd.read_csv(SOURCE, encoding="utf-8")
    tables = split_and_transform(df)
    engine = create_engine(engine_url)
    # FK order matters: addresses before customers
    for name in ("addresses", "customers"):
        tables[name].to_sql(name, engine, if_exists="append", index=False, chunksize=10_000)

if __name__ == "__main__":
    import sys
    main(sys.argv[1])
```

Each generated script lives in `data/scripts/<dataset>/<timestamp>/` alongside `schema.sql` and `manifest.json`. The UI exposes a preview + download.

## 7. Execution & validation

- **Dry-run mode**: run `split_and_transform()` only; report row count, dropped rows, coerce failures per column, FK integrity between split tables.
- **Staging**: always load to `_stage_<table>` tables first in a transaction, validate, then `INSERT ... SELECT` into the real tables.
- **Validation checks**:
  - row count delta vs. source
  - null rates within tolerance of the profile
  - PK uniqueness, FK integrity between split tables
  - sample round-trip (read back N rows, compare)
- On failure, surface a diff to the user (in the UI) and to the agent for a revision pass.

## 8. Reuse & iteration

- Scripts are stored on the API server's filesystem (`./data/scripts/`) and indexed in Postgres for fingerprint lookup.
- Fingerprint = column-name set + inferred types + sample-hash. On a new file the registry checks for a match; if found, the UI shows "this looks like the file you imported on 2024-09-12 — adapt or regenerate?"
- User feedback flows through the chat sidebar (free text) and feeds the next agent call as context. Edits the user makes directly to the generated `.py` are picked up too — the registry diffs them and surfaces the changes for the next run.

## 9. Phased build

Six phases, each independently demoable end-to-end (backend + frontend slice).

### Phase 0 — Monorepo scaffold (1 day)
- `uv` workspace at root; `apps/api` with a FastAPI ping route; `apps/web` with a Vite app showing "hello"; `packages/core` as an empty installable lib.
- `pnpm-workspace.yaml`, `docker-compose.yml` for local Postgres, a single `make dev` (or `mise`) that boots api + web + db.
- OpenAPI codegen wired so the web client always matches the API.

### Phase 1 — Profiler + file manager (2–3 days)
- In `packages/core`: file sniffing (`charset-normalizer`, delimiter, header, xlsx sheet pick), unified `Reader` over CSV/TSV/XLS/XLSX, column profiling with the regex pattern bank.
- API: `POST /files` (multipart upload), `GET /files`, `GET /files/:id/profile`.
- UI: `FileManager.tsx` — drag-drop upload, file list with size/rows/type, click a file to see its JSON profile.
- Tests on fixture files: BOM, semicolon delim, mixed-type column, all-null column, single-row file, German decimals, Excel-serial dates.

### Phase 2 — Agent loop + chat sidebar (3 days)
- LangGraph state machine in `packages/core/agent/` with the tools from §5; pydantic `SchemaDecision` model as the terminating output.
- API: `POST /sessions` (start agent run for a file), `GET /sessions/:id/stream` (SSE).
- UI: `ChatSidebar.tsx` — kicks off a session, renders streamed tool calls and messages, accepts free-text nudges that get appended to the agent's context.
- Mock-LLM mode for tests (canned tool-call sequences) so the suite runs offline.

### Phase 3 — Schema (with normalization) + script generation (2 days)
- IR with multi-table support and FK relations (`packages/core/schema/`).
- DDL emitter for Postgres.
- Jinja2 templates that handle multi-table writes in dependency order.
- API: `GET /sessions/:id/schema`, `GET /sessions/:id/script`.
- UI: schema preview (collapsible table cards with column types and FKs), script preview with diff view when the agent revises after feedback.

### Phase 4 — Execute + validate (2 days)
- Staging-table flow in `packages/core/execute/`.
- Post-load validators.
- API: `POST /runs` (executes a script), SSE progress.
- UI: run button on a session, progress bar, validation report panel.

### Phase 5 — Table browser + script registry (2 days)
- API: `GET /tables` (Postgres introspection), `GET /tables/:name/rows?page=...` (paginated).
- UI: `TableBrowser.tsx` — list of tables, click for column types and a paginated row preview.
- Registry: store scripts with metadata; UI to view/download past scripts.

### Phase 6 — Reuse & feedback (2 days)
- Fingerprint matching on new uploads.
- "Adapt or regenerate?" prompt; "Rerun on this file" action on existing scripts.
- Free-form feedback re-invokes the agent with prior script + feedback in context, emits a revision.

## 10. Decisions taken

(Originally open questions, now resolved.)

1. **Input scope:** one file at a time, but the agent may decompose its contents into multiple normalized tables.
2. **Database:** PostgreSQL only.
3. **Schema source:** fully agent-inferred, with user feedback in the chat sidebar to refine.
4. **PII:** no special filtering — sample values (including emails/phones) go to the LLM as-is.
5. **Frontend:** React + Vite + TypeScript with file manager, chat sidebar, and table browser.
6. **Repo layout:** monorepo (`apps/api`, `apps/web`, `packages/core`).
7. **Agent framework:** LangChain with LangGraph (`langchain-anthropic`).

## 11. Risks & how I'd manage them

- **LLM hallucinates a transformation that silently corrupts data.** Mitigations: dry-run with per-row coercion-failure counts; staging tables; round-trip sampling; generated scripts are human-readable so review in the UI is realistic.
- **Excel is a swamp** (merged cells, multi-row headers, formulas, dates-as-numbers). Mitigation: detect these in the sniffer and either normalize or hard-fail with a clear message in the UI rather than silently mis-parsing.
- **Profile bloat** for wide files (500+ columns). Mitigation: token-budget the profile; for very wide files, the agent gets a column-group summary first and can drill in via tools.
- **Cost.** A single ingestion shouldn't cost more than a few cents. Route easy decisions through Haiku and only escalate to Opus when the profile is ambiguous.
- **Aggressive normalization.** The agent might over-split a table. Mitigation: surface every split as a separate card in the UI with its evidence (e.g. "found 1:N relationship between `customer_id` and `address_*` columns") and let the user reject splits individually.
- **LangChain / LangGraph API churn.** Pin versions tightly; keep all framework usage behind `packages/core/agent/` so a future swap is local.

## 12. Definition of done for v1

A user can:

1. Open the structai web app.
2. Upload `sales_q3.xlsx` via the file manager.
3. Open the chat sidebar and start a session against that file.
4. Watch the agent profile the file, propose a normalized schema (possibly multiple tables with FKs), and generate import scripts — streamed live with tool calls visible.
5. Nudge the agent in chat ("treat country as ISO-2", "don't split addresses, keep them in `sales`") and see a revised proposal.
6. Approve and run; data lands in Postgres via staging tables.
7. Browse the new tables in the table browser, paginate rows.
8. Download the generated scripts (`import.py`, `schema.sql`, `manifest.json`) for version control.
9. On `sales_q4.xlsx` next quarter, the registry finds the prior script — re-running uses zero or near-zero LLM calls.
