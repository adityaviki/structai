# StructAI

An AI-powered import tool that turns messy CSV / TSV / XLSX / JSON files into a
proper Postgres schema, with a human in the loop for the calls the model
shouldn't make alone.

The story every analyst knows: someone hands you a spreadsheet, the columns are
named `Cust_Email_Final_v2`, the same customer appears with three slightly
different addresses, and you spend an afternoon writing one-off Python before you
can even start the work you were actually asked to do.

StructAI is the tool for that afternoon. Drop a document on a project; an agent
profiles it, proposes a Postgres schema (extracted entities, foreign keys,
primary keys — the boring choices made for you), and once you accept the schema
it generates and runs the import script inside a single transaction. Every run
takes a database snapshot first, so any import that lands badly is one click to
undo.

## Features

- **Schema-first review.** The agent shows you the DDL before it writes a line of
  import code. You accept, or you reply in natural language ("split the address
  into its own table; make `customer.email` the PK") and it revises. This is the
  most expensive decision in an import, and the one the model should not silently
  make.
- **Self-correcting execute loop.** When the generated script blows up (encoding,
  mixed date formats, an embedded comma in a quoted field), the agent reads the
  stderr tail, diagnoses the root cause, and rewrites — up to five attempts,
  after which it asks for help instead of thrashing.
- **Cheap undo.** Every successful import gets a template-DB snapshot. One click
  rolls the project back to before the import landed; a retention sweeper prunes
  old snapshots.
- **Many shapes in, one schema out.** CSV, TSV, XLSX (multi-sheet), and JSON —
  including multi-table inputs where foreign keys are inferred across tables.
- **See and browse the result.** An interactive ER diagram (drag-to-arrange,
  layout persisted per project) and a data browser with server-side sort and
  per-column filters.

## Tech stack

- **Backend** — [FastAPI](https://fastapi.tiangolo.com) + [arq](https://arq-docs.helpmanual.io)
  (one Redis-backed job at a time), managed with [uv](https://github.com/astral-sh/uv).
  Server-sent events stream the agent's progress to the UI in real time. File
  parsing via [polars](https://pola.rs) / openpyxl; structured logging with
  structlog.
- **Frontend** — **React 18** + **Vite 5** + **Tailwind 3**, with
  `@xyflow/react` + dagre for the ER diagram and `react-router-dom` for routing.
- **AI** — **Anthropic Claude**, called through a small agent-loop wrapper that
  lets the model pause and ask the user mid-stream when it hits a judgment call.
- **Data** — **Postgres** as both the metadata store and each project's data DB,
  where template-DB clones make snapshots near-free; **Redis** backs the job
  queue and pub/sub.

## How it works

A project owns its own Postgres database. An import run moves through
**profile → propose schema → (review) → generate → execute → validate**, driven
by an arq worker that processes one job at a time and streams every step over
SSE. The agent can interrupt the run with a clarification (or, in auto mode,
answer its own question via a second model call and record the decision). Before
any script touches the project DB, a snapshot is taken so the whole run can be
rewound atomically.

The full design and decision log lives in [`PLAN.md`](./PLAN.md); a higher-level
component overview is in [`docs/architecture.md`](./docs/architecture.md).

## Getting started

### Prerequisites

- **Python 3.12+** and [`uv`](https://github.com/astral-sh/uv)
- **Node 20+** and `pnpm`
- **Postgres** (role with `CREATEDB`) and **Redis**
- An **Anthropic API key** (only needed once you actually run an import)

### 1. Bring up Postgres + Redis

The simplest path is the bundled compose stack (Postgres on `5434`, Redis on
`6381`, chosen to avoid colliding with a local cluster):

```bash
docker compose up -d
```

Prefer your own local services? Point the URLs in `.env` at them instead (e.g.
`postgresql:///postgres` and `redis://127.0.0.1:6379/0`).

### 2. Configure and install

```bash
cp .env.example .env       # edit if your Postgres/Redis aren't on the defaults
make install               # uv sync + pnpm install
make migrate               # creates the structai_meta DB and runs migrations
```

### 3. Run

```bash
make dev
```

That starts three processes:

- `uvicorn` API on http://127.0.0.1:8000 (OpenAPI docs at `/api/docs`)
- the `arq` worker (one job at a time)
- the Vite dev server on http://127.0.0.1:5173 (proxies `/api` to the backend)

Open http://127.0.0.1:5173, add your Anthropic key on the Settings page (or set
`STRUCTAI_ANTHROPIC_API_KEY` in `.env`), create a project, upload one of the
files in [`samples/`](./samples), and start an import.

### Configuration

All backend settings are read from `.env` (see `.env.example`):

| Variable | Purpose | Default |
| --- | --- | --- |
| `STRUCTAI_PG_URL` | Postgres URL; the role needs `CREATEDB` | compose stack on `5434` |
| `STRUCTAI_META_DB_NAME` | Name of the metadata database | `structai_meta` |
| `STRUCTAI_REDIS_URL` | Redis URL for the arq queue + pub/sub | compose stack on `6381` |
| `STRUCTAI_ANTHROPIC_API_KEY` | Anthropic key (also settable in the UI) | unset |
| `STRUCTAI_DEFAULT_MODEL` | Default Claude model (override per project) | `claude-sonnet-4-6` |
| `STRUCTAI_WORKSPACE` | Root for documents, run logs, snapshot metadata | `~/.local/share/structai` |

## Project layout

```
backend/     FastAPI + arq service (agent, pipeline, worker, api), managed with uv
frontend/    React + Vite + Tailwind SPA
deploy/      Provisioning, Caddy snippet, and systemd units (see deploy/README.md)
docs/        Architecture overview
samples/     Example CSV / TSV / JSON / XLSX inputs to try imports against
PLAN.md      Design & decision log
```

## Useful commands

```bash
make test    # backend unit tests (pytest)
make lint    # ruff check + mypy on the backend
make fmt     # ruff format the backend
```

## Deployment

The production setup runs the FastAPI app, the arq worker, Postgres, and Redis
under systemd behind Caddy. Full step-by-step instructions are in
[`deploy/README.md`](./deploy/README.md).
