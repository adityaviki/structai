# StructAI

AI-powered structured-data import. Drop messy CSV / TSV / XLSX / JSON files
in; an LLM agent profiles them, writes the import script, runs it inside a
transaction against a real Postgres database, and surfaces clarifications
when it has to make a judgment call.

See [`PLAN.md`](./PLAN.md) for the full design and decision log.

## Status

**Phase 3 — clarifications & auto mode.** The agent can now pause and ask
the user when it has to make a real judgment call (e.g. ambiguous data
shape, multiple plausible PK candidates). The run goes to status
``needs_clarification`` and waits for an answer via API or the UI's
clarification card. With ``auto_mode=true`` on the import, the agent
instead calls a second small LLM that picks one option on the user's
behalf and records it as an "auto decision" the user can review.

Earlier phase capabilities still apply:

- **Phase 2:** template-DB snapshots, fix loop (cap 5), stop/cancel,
  undo, retention sweeper, worker restart recovery.
- **Phase 1:** profile / generate / execute / validate over a single CSV
  with live SSE progress, project + document CRUD, paginated data tab.

Out of scope until later phases: XLSX/JSON/TSV and multi-table imports
(Phase 4), ER diagram (Phase 5), row filters / sort and settings UI
(Phase 6).

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

# Stop a still-running import:
curl -X POST http://127.0.0.1:8000/api/runs/$RUN/cancel
# Undo a completed import (the project DB rewinds atomically):
curl -X POST http://127.0.0.1:8000/api/runs/$RUN/undo
```

## Exercising Phase 2

- **Fix loop:** upload a CSV that will trip up a naïve script — e.g. a
  date column with mixed `MM/DD/YYYY` and `YYYY-MM-DD` formatting, or a
  numeric column containing `"N/A"` strings. The first execute attempt
  will fail; the run goes into `fixing`; the agent rewrites the script
  and the second attempt succeeds. The run detail view shows each
  attempt as its own step card.
- **Stop:** while a run is in `executing` (long file), click **Stop**
  on the run detail. The subprocess is killed, the snapshot is dropped,
  the live project DB is unchanged.
- **Undo:** on a completed import, click **Undo**. The project DB is
  restored to its pre-run state. Any imports that ran after the one you
  undid are also marked `reverted`.

## Exercising Phase 3

- **Clarification (manual):** add an instruction like
  *"ask me whether 'amount' should be cents or dollars"* and start an
  import. The status will move to `needs_clarification` and the run
  detail will show a card with options. Pick one (or write a custom
  instruction) and **Continue import** — the worker resumes with your
  answer.
- **Auto mode:** start an import with **Auto mode** enabled in the
  New Import modal. If the agent asks anything, the orchestrator
  synthesizes an answer via a second LLM call and records it under
  *Decisions the agent made on your behalf*.
- **API:**
  - `GET /api/runs/:id/clarifications` — list all clarifications.
  - `POST /api/runs/:id/clarifications/:cid/answer` body
    `{"choice_id": "...", "custom": "..."}` — answer manually.

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
