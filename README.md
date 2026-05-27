# StructAI

AI-powered structured-data import. Drop messy CSV / TSV / XLSX / JSON files
in; an LLM agent profiles them, writes the import script, runs it inside a
transaction against a real Postgres database, and surfaces clarifications
when it has to make a judgment call.

See [`PLAN.md`](./PLAN.md) for the full design and decision log.

## Status

**Phase 1 — vertical slice.** Full pipeline runs end-to-end for a single
CSV: create a project, upload a file, the agent profiles it, writes an
import script, executes it against the project's Postgres database, and
validates the result. Imports are visible live (SSE) and the imported
tables show up in the Data tab.

Out of scope until later phases: fix-on-error loop, undo, clarifications,
XLSX/JSON/TSV, ER diagram, row filters/sort, settings UI.

## Prerequisites

You install Postgres and Redis yourself (decision D2a, D9).

```bash
# Arch
sudo pacman -S postgresql redis
sudo systemctl enable --now postgresql redis
# Or as a user service if you prefer
```

Create a Postgres role with `CREATEDB`. On a fresh Arch install the default
role is `postgres`; the easiest path is to create a role matching your OS
user so peer auth on the local socket just works:

```bash
sudo -u postgres createuser -s "$USER"   # superuser is convenient for dev
# Or, against an existing role:
# sudo -u postgres psql -c "ALTER ROLE myuser CREATEDB"
```

Then set `STRUCTAI_PG_URL` in `.env` to a URL the new role can authenticate
with — e.g. `postgresql:///postgres` (Unix socket, current user, default
database).

Toolchain:

- Python 3.12+
- [`uv`](https://github.com/astral-sh/uv)
- Node 20+ and `pnpm`

## First-time setup

```bash
cp .env.example .env       # edit if your PG/Redis aren't on the defaults
make install               # uv sync + pnpm install
make migrate               # creates structai_meta and schema_migrations
```

## Run

```bash
make dev
```

That runs three processes:

- `uvicorn` API on http://127.0.0.1:8000 (docs at `/api/docs`)
- `arq` worker (one job at a time)
- Vite dev server on http://127.0.0.1:5173 (proxies `/api` to the backend)

Quick checks:

```bash
curl http://127.0.0.1:8000/api/healthz             # → {"status":"ok"}
curl -X POST http://127.0.0.1:8000/api/_dev/enqueue-noop   # worker logs "worker.noop.fired"
```

## End-to-end test (Phase 1)

Requires a valid Anthropic API key. Add it to `.env`:

```
STRUCTAI_ANTHROPIC_API_KEY=sk-ant-...
```

Restart `make dev` (so the worker picks up the new env), then in a browser:

1. Open http://127.0.0.1:5173.
2. Click **New project** → name it (e.g. "Smoke test") → Create.
3. Go to the **Documents** tab → upload `samples/people.csv`.
4. Click **New import** → pick the file → optionally write an instruction
   (e.g. *"use snake_case"*) → **Start import**.
5. Watch the four steps run live (profile → generate → execute → validate).
   The generated `import.py` shows up in the run detail panel.
6. When the run completes, switch to the **Data** tab and inspect the
   imported rows.

The same flow from the command line (handy for debugging):

```bash
PROJECT=$(curl -s -X POST -H 'content-type: application/json' \
  -d '{"name":"Smoke test"}' http://127.0.0.1:8000/api/projects | jq -r .id)
DOC=$(curl -s -F "file=@samples/people.csv" \
  http://127.0.0.1:8000/api/projects/$PROJECT/documents | jq -r .id)
RUN=$(curl -s -X POST -H 'content-type: application/json' \
  -d "{\"document_id\":\"$DOC\"}" \
  http://127.0.0.1:8000/api/projects/$PROJECT/imports | jq -r .id)
# Watch SSE:
curl -N http://127.0.0.1:8000/api/runs/$RUN/events
```

## Layout

```
backend/             # FastAPI + arq, managed with uv
frontend/            # React + Vite + Tailwind (started from the prototype)
designs-archive/     # pristine pre-implementation prototype, read-only reference
migrations/          # SQL migrations for the structai_meta DB (inside backend/)
PLAN.md              # design & decision log
```

## Useful commands

```bash
make test            # backend unit tests (pytest)
make lint            # ruff check + mypy on the backend
make fmt             # ruff format the backend
```
