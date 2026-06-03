# StructAI — Architecture

> **StructAI** is an AI-powered structured-data import system. You upload a messy
> document (CSV/TSV/XLSX/JSON/NDJSON); an LLM agent profiles it, proposes a
> relational schema (with a human approval gate), generates a Python import
> script, runs it with an automatic fix loop, and validates the result — with a
> Postgres snapshot as a one-click rollback point.

This document is written in plain text — no diagrams. Concrete details (file
paths, ports, table columns) reflect the code as of this writing; treat them as a
map, not a spec.

---

## How to read this document

Pick the entry point that matches what you need:

| If you want to…                            | Read…                                              |
| ------------------------------------------ | -------------------------------------------------- |
| Understand what the product *does*, fast   | **The big picture** + **A guided tour**            |
| See how the running pieces fit together    | §1 *System topology* and §4 *Request & event flow* |
| Find your way around the backend code      | §2 *Backend layers* + **Where things live in code**|
| Understand the import lifecycle / statuses | §3 *The import pipeline*                            |
| Understand the database layout             | §5 *Data model* and §6 *Snapshot & rollback*       |
| Just grab versions/ports                   | **Tech stack at a glance** (bottom)                |

---

## The big picture (plain language)

**The one-sentence version:** you hand StructAI a messy data file, and it figures
out a sensible set of database tables, asks you to sign off, writes and runs the
code to load your data into those tables, and fixes its own bugs along the
way — with a safety net that can undo the whole thing.

**The core idea.** Loading arbitrary spreadsheets into a clean relational
database is normally manual, fiddly work. StructAI hands that work to an LLM
*agent* but keeps two human checkpoints and a one-click rollback, so the
automation never does anything irreversible without a safety net.

**The five moving parts:**

1. **The browser app** — a React single-page app where you upload files, watch
   progress live, approve the proposed schema, and answer the agent's questions.
2. **The API** (FastAPI) — handles HTTP requests, streams live progress back to
   the browser, and hands long jobs off to the worker.
3. **The worker** (arq) — runs the actual import *pipeline* in the background,
   one at a time, talking to the LLM.
4. **Postgres** — stores both StructAI's own bookkeeping (the "meta DB") and a
   *separate database per project* where your imported tables actually live.
5. **Redis** — a job queue (API → worker) plus a live event bus (worker →
   browser).

**Glossary — terms used throughout this doc:**

- **Run / import run** — one attempt to import one document. Everything (status,
  steps, snapshot, results) hangs off a run. It moves through a series of stages
  (§3).
- **Pipeline** — the ordered stages a run goes through: *profile → propose schema
  → generate → snapshot → execute → (fix → execute)… → validate*.
- **Agent / agentic loop** — the LLM calling tools in a loop (e.g. "look at the
  data", "ask the user", "emit the schema") until it produces a result.
- **Human gate** — a point where the run *pauses* and waits for a person:
  approving the proposed schema, or answering a clarifying question. In
  **`auto_mode`** the system decides for itself instead of waiting.
- **Snapshot** — a full copy of the project database taken *before* the generated
  script runs, using Postgres `CREATE DATABASE … TEMPLATE`. It's the rollback
  point. No external backup tool involved.
- **Meta DB** (`structai_meta`) — StructAI's own tables: projects, documents,
  runs, steps, etc. Your imported data is *not* here.
- **Per-project DB** — one Postgres database per project, holding the user tables
  that get created by the import.
- **Fix loop** — when the generated script fails, the agent reads the error and
  rewrites the script, retrying up to **5** times before giving up.

---

## A guided tour: what happens when you import a file

Follow one file from drop to done. (The detailed version is in §3; this is the
story.)

1. **Upload.** You drag a CSV/XLSX/JSON file into the browser. It's `POST`ed to
   the API, which saves it to the local workspace folder and records a
   `documents` row. Nothing has been analyzed yet.
2. **Kick off an import.** You start an import on that document. The API inserts
   an `import_runs` row with status `queued` and drops a job on the Redis queue,
   then immediately returns a `run_id`. The browser opens a live connection
   (`GET /runs/{id}/events`) and starts showing progress.
3. **Profile** *(worker)*. The worker picks up the job and the orchestrator
   begins. First it uses **Polars** to profile the file — columns, types, null
   counts, row counts — without involving the LLM yet.
4. **Propose a schema** *(LLM)*. The agent looks at the profile and proposes a
   relational schema (tables + DDL). The run **pauses** at the
   `awaiting_schema_approval` human gate. You can **accept**, or **revise** with
   feedback (which re-proposes). *(In `auto_mode`, it auto-accepts.)*
5. **Generate the loader** *(LLM)*. Once approved, the agent writes a Python
   script (`import.py`) that reads your file and loads it into the proposed
   tables. At any LLM stage it may **pause again** to ask you a clarifying
   question (`needs_clarification`).
6. **Snapshot.** Right before running anything, StructAI snapshots the project
   DB. This is the rollback point.
7. **Execute.** The script runs as a subprocess in a curated environment with a
   300-second timeout. If it exits cleanly, great. If it errors or times out…
8. **Fix loop** *(LLM)*. …the agent reads the error output and rewrites the
   script, then re-executes — up to 5 attempts. If it never succeeds, the run is
   marked `failed` and the snapshot is restored (your DB is untouched).
9. **Validate.** On success, StructAI checks the result: do the expected tables
   exist? Are row counts in the right ballpark? Any all-NULL columns to warn
   about? On pass the run is `completed`; on fail it restores the snapshot and
   marks `failed`.
10. **Undo (any time later).** Pinned snapshots let you revert a completed import
    with one click, which creates a new `reverted` run.

Throughout, every stage writes its progress to the `pipeline_steps` table and
publishes an event to Redis, which the API relays to your browser live (§4).

---

## 1. System topology / deployment

**In one line:** two long-running processes — the **API** (answers the browser)
and the **worker** (does the slow import work) — coordinate through **Redis** and
share state through **Postgres**. The browser only ever talks to the API.

**The processes and services, and how they connect:**

- **Browser (SPA)** — React 18 + Vite + TypeScript + Tailwind, with a light/dark
  theme stored in `localStorage`. It talks to the API over HTTP (plain REST plus
  Server-Sent Events for live updates). In dev, Vite runs on `:5173` and proxies
  `/api` to the backend on `:8000`; in prod the frontend is a static build served
  by any host.
- **API** — a FastAPI app on uvicorn at `127.0.0.1:8000`, all routes under
  `/api`. Runs as the `structai-api` systemd unit (hardened with
  `ProtectHome=read-only`, `PrivateTmp`, etc.). It does three things: enqueue
  import jobs onto Redis (via arq), read/write the database (via asyncpg), and
  relay live events to the browser.
- **Worker** — an arq worker (`structai.worker.main`) running as the
  `structai-worker` systemd unit. It pulls jobs off Redis and runs the import
  pipeline. Key settings: `max_jobs=1` (one import at a time) and
  `job_timeout=8h` (imports can be long because of the human gates). It recovers
  in-progress runs on restart and runs an hourly sweep of stale snapshots.
- **Redis 7** (`:6381`) — used for two distinct jobs on the same instance: the
  **arq job queue** (API → worker) and a **pub/sub event bus** on channels named
  `run:{id}` (worker → API → browser).
- **PostgreSQL 16** (`:5434`) — holds the **meta DB** (`structai_meta`), one
  **per-project DB** per project (`<project.db_name>`, where the imported tables
  live), and transient **snapshot DBs** (`<db>_snap_<tail>`, made with
  `CREATE DATABASE … TEMPLATE`).
- **Anthropic Claude API** — the LLM the worker calls; default model
  `claude-sonnet-4-6`, overridable per project.
- **Workspace (local filesystem)** — `$STRUCTAI_WORKSPACE` (under
  `~/.local/share/…`). Stores uploaded files at `documents/{doc_id}/{filename}`
  and per-run artifacts at `runs/{run_id}/attempt-N/{import.py, *.log}`.

In dev, Postgres and Redis run via docker-compose (`postgres:16-alpine`,
`redis:7-alpine`).

---

## 2. Backend component layers

The backend is a layered FastAPI service with **no ORM** — raw `asyncpg` is used
deliberately so the pipeline can issue `CREATE DATABASE … TEMPLATE` for snapshots.

**The four layers, top to bottom (higher layers call down, never up):**

1. **`api/` — the HTTP layer.** Handles requests/responses, SSE streaming, and
   validation. One module per area: `projects`, `documents`, `runs`,
   `clarifications`, `schema_proposals`, `tables`, `schema`, `snapshots`,
   `settings`, `healthz`, `dev`, plus shared `errors`.
2. **`pipeline/` + `agent/` — orchestration and the LLM.**
   - `pipeline/` drives the import. `orchestrator.run_import()` walks a run
     through the stages `profile → propose_schema → generate → execute → fix →
     validate` (one file per stage).
   - `agent/` wraps the LLM: `client.py` (the `AsyncAnthropic` client plus
     `call_tool()` / the agentic loop), `prompts.py` (system prompt + renderers),
     `events.py` (Redis pub/sub), `decide.py` (the auto-mode decision logic).
3. **`db/` + `workspace/` — storage.**
   - `db/` is data access over asyncpg: `pools.py` (the meta pool + per-project
     pools), the repositories (`runs_repo`, `clarifications_repo`,
     `schema_proposals_repo`, `settings_repo`), `snapshots.py` (template copy +
     restore), `schema_intro.py` (introspection), `migrate.py`, `ids.py` (ULIDs),
     `health.py`.
   - `workspace/storage.py` handles file I/O (`document_dir`, `run_dir`,
     `write_document`).
4. **`schemas/` + config — the shared foundation.** `schemas/` holds the Pydantic
   models (`run`, `project`, `document`, `table`, `settings`, `diagram`).
   `settings.py` is pydantic-settings (env prefix `STRUCTAI_`, plus `.env`);
   `logging.py` is structlog; `cli.py` is the entry point.

SQL migrations live in `migrations/` as plain `.sql` files (`00*.sql`), tracked
in the `schema_migrations` table.

---

## 3. The import pipeline (the stages a run goes through)

The orchestrator drives one run through an ordered set of stages. Two stages can
**pause** the run waiting for a human (or auto-decide in `auto_mode`). The fix
loop retries a failing script up to `MAX_FIX_ATTEMPTS` (**5**). A pre-execute
**snapshot** is the rollback point; on validation failure the project DB is
restored from it.

**The stages, in order:**

1. **PROFILE** *(status `profiling`)* — Polars reads the file and produces a
   `DocumentProfile`: columns, types, null counts, row counts. No LLM yet.
2. **PROPOSE_SCHEMA** — the LLM agentic loop produces a `SchemaProposal` (DDL +
   tables). Then it **pauses at a human gate** (`awaiting_schema_approval`):
   - **accept** → continue to generate;
   - **revise(feedback)** → re-propose a new iteration;
   - in `auto_mode`, it auto-accepts.
3. **GENERATE** *(status `generating`)* — the LLM agentic loop writes `import.py`,
   the Python load script.
4. **SNAPSHOT** — `CREATE DATABASE <db>_snap_<run-tail> TEMPLATE <db>`, recorded
   on `import_runs.snapshot_db`. This is the rollback point.
5. **EXECUTE** *(status `executing`)* — runs the script as a subprocess in a
   curated environment with a 300-second timeout.
6. **FIX** *(status `fixing`)* — if execute exits non-zero or times out, the LLM
   rewrites the script using the stderr tail and loops back to EXECUTE. After
   `MAX_FIX_ATTEMPTS` (5) without success, the run is marked **`failed`** and the
   snapshot is restored.
7. **VALIDATE** *(status `validating`)* — checks that tables exist, row counts
   look right, and warns on all-NULL columns. On pass → **`completed`** (snapshot
   dropped, or pinned for undo). On fail → restore snapshot, mark **`failed`**.

**The clarification gate (can fire during any LLM stage).** Via the
`ask_clarification` tool the agent can pause with status `needs_clarification`,
presenting a question + options. The user answers (`POST …/answer`) and the run
resumes. In `auto_mode`, `decide.py` picks an answer automatically.

**Side channels (any time):**

- **Cancel** — `POST /runs/{id}/cancel` sets `cancel_requested=true`; a watchdog
  stops the run (`cancelling` → `cancelled`).
- **Undo** — `POST /runs/{id}/undo` restores a pinned snapshot in a new run
  (status `reverted`).

**The full status enum:** `queued`, `profiling`, `generating`, `executing`,
`fixing`, `validating`, `needs_clarification`, `awaiting_schema_approval`,
`completed`, `failed`, `cancelling`, `cancelled`, `reverted`.

---

## 4. Request & live-event flow

How a single import is driven and streamed back to the UI. The key trick: the
browser opens **one long-lived SSE connection** and the worker pushes progress
into it via Redis, so the UI updates live without polling.

**Step by step:**

1. **Upload.** Browser `POST /documents` → API writes the file to
   `workspace/documents/` and returns `201` with the document.
2. **Start the import.** Browser `POST /projects/{id}/imports` → API inserts an
   `import_runs` row (`status=queued`), enqueues `import_job` on Redis, and
   returns `202 {run_id}`. The worker dequeues it and starts `run_import()`.
3. **Open the live stream.** Browser `GET /runs/{id}/events` (SSE, kept open) →
   API `SUBSCRIBE`s to the Redis `run:{id}` channel.
4. **Per stage.** The worker updates the DB (`pipeline_steps` + run status) and
   `PUBLISH`es a step/status event to Redis. The API relays each event to the
   browser as an SSE message, so the UI animates in real time.
5. **At a human gate.** The browser `POST`s to `/runs/{id}/accept`, `…/answer`,
   or `…/revise`. The API updates the schema proposal / clarification row. The
   worker, which polls the DB roughly every second, notices and resumes.
6. **Finish.** The worker publishes a final `completed` event, which the API
   relays to the browser.

So: HTTP requests flow browser → API; live updates flow worker → Redis → API →
browser; and the only thing the user actively does mid-run is approve/answer at a
gate.

---

## 5. Data model (meta DB)

Core entities in `structai_meta`. Your imported table *data* lives in the
separate per-project databases, **not** here. IDs are ULIDs (sortable, time-ordered).
Foreign keys cascade on delete from the parent.

**The tables and how they relate:**

- **`projects`** — the top-level entity. Columns: `id` (PK, ULID), `name`,
  `description`, `emoji`, `color`, `db_name` (UNIQUE — points at the project's
  own Postgres database holding the imported tables), `model_override` (nullable),
  `created_at`, `updated_at`. A project **has many** documents and runs.
- **`documents`** — an uploaded file. Columns: `id` (PK), `project_id` (→
  projects), `name`, `ext`, `size_bytes`, `storage_path`, `status`,
  `last_import_id`, `uploaded_at`. A document **has many** runs.
- **`import_runs`** — one import attempt; the center of the model. Columns: `id`
  (PK, ULID), `project_id` (→ projects), `document_id` (→ documents), `title`,
  `status`, `progress` (0–100), `instructions`, `auto_mode`, `rows_imported`,
  `total_rows`, `created_tables[]`, `error_message`, `cancel_requested`,
  `snapshot_db`, `snapshot_pinned`, `reverted_at`, `reverted_by_run_id` (→
  import_runs, a self-reference), `started_at`, `finished_at`. A run **has many**
  steps, clarifications, and schema proposals.
- **`pipeline_steps`** — one row per stage execution of a run. Columns: `id`,
  `run_id` (→ runs), `step_key`, `status`, `title`, `summary`, `code`,
  `language`, `attempts`, `errors[]`, `started_at`, `duration_ms`. Unique on
  `(run_id, step_key, attempts)`. `step_key` ∈ {`profile`, `propose_schema`,
  `generate`, `execute`, `fix`, `validate`}; step `status` ∈ {`pending`,
  `running`, `success`, `error`, `warning`}.
- **`clarifications`** — questions the agent asked. Columns: `id`, `run_id` (→
  runs), `question`, `context`, `options` (jsonb), `answer_choice_id`,
  `answer_custom`, `auto_decision`, `auto_reasoning`, `created_at`, `answered_at`.
- **`schema_proposals`** — schema versions offered for approval. Columns: `id`,
  `run_id` (→ runs), `iteration`, `schema_ddl`, `tables[]`, `rationale`, `status`
  (`pending` / `accepted` / `superseded`), `feedback`, `auto_accepted`,
  `created_at`, `decided_at`. Unique on `(run_id, iteration)`.

**Two standalone tables:**

- **`settings`** — global key/value config. `key` (PK) e.g. `anthropic_api_key`,
  `default_model`; `value` (JSON); `updated_at`.
- **`schema_migrations`** — which migrations have run. `version` (PK),
  `filename`, `applied_at`.

---

## 6. Snapshot & rollback model

**In plain terms:** before touching your data, StructAI makes a frozen copy of
the whole project database using a Postgres template-DB copy. That copy is the
atomic rollback point — no external backup system involved.

**The three scenarios:**

- **Before EXECUTE.** The project DB is `app_<id>`. StructAI runs
  `CREATE DATABASE app_<id>_snap_<tail> TEMPLATE app_<id>`, producing a frozen
  copy.
- **On success.** The live `app_<id>` now holds the newly imported data. The
  snapshot is dropped — *unless* it's pinned for later undo.
- **On failure / undo.** The live `app_<id>` is dropped and recreated with
  `CREATE DATABASE app_<id> TEMPLATE app_<id>_snap_<tail>`, restoring the project
  to its exact pre-import state.

**Lifecycle notes.** Pinned snapshots survive for one-click **undo** (which
creates a new `reverted` run). An hourly worker cron sweeps stale, unpinned
snapshot DBs so they don't accumulate.

---

## Where things live in the code

A concept → file map for when you want to go from "I read about X" to "show me
the code." Backend paths are under `backend/src/structai/`.

| Concept                              | Start here                                                       |
| ------------------------------------ | --------------------------------------------------------------- |
| App entry / routing wiring           | `main.py` (FastAPI app), `api/*.py` (one module per router)      |
| The pipeline orchestration           | `pipeline/orchestrator.py` (`run_import`, `MAX_FIX_ATTEMPTS`)    |
| Individual stages                    | `pipeline/{profile,propose_schema,generate,execute,fix,validate}.py` |
| LLM calls & the agentic loop         | `agent/client.py`, prompts in `agent/prompts.py`                |
| Auto-mode decision logic             | `agent/decide.py`                                                |
| Live events (Redis pub/sub)          | `agent/events.py`                                                |
| DB connection pools                  | `db/pools.py` (meta pool + per-project pools)                    |
| Reading/writing runs, clarifications | `db/runs_repo.py`, `db/clarifications_repo.py`, `db/schema_proposals_repo.py` |
| Snapshot create / restore            | `db/snapshots.py`                                                |
| Schema introspection                 | `db/schema_intro.py`                                             |
| SQL migrations                       | `migrations/00*.sql` (tracked in `schema_migrations`)           |
| File storage (uploads, run artifacts)| `workspace/storage.py`                                           |
| Background worker config & recovery  | `worker/main.py` (`max_jobs=1`, `job_timeout=8h`)               |
| Hourly snapshot sweep                | `worker/sweeper.py`                                              |
| Config / env vars                    | `settings.py` (prefix `STRUCTAI_`)                               |
| Shared data models                   | `schemas/*.py` (Pydantic)                                        |
| Frontend                             | `frontend/src/` (pages, components, React Flow schema diagram)   |

---

## Tech stack at a glance

| Layer           | Choice                                                                   |
| --------------- | ------------------------------------------------------------------------ |
| Frontend        | React 18, Vite 5, TypeScript, Tailwind 3, React Router, React Flow       |
| API             | FastAPI on uvicorn (ASGI), Pydantic, structlog                           |
| Worker / queue  | arq (Redis-backed); `max_jobs=1`, `job_timeout=8h`                       |
| LLM             | Anthropic Claude (`AsyncAnthropic`), default `claude-sonnet-4-6`         |
| Data access     | raw `asyncpg` (no ORM) — needed for `CREATE DATABASE … TEMPLATE`         |
| Databases       | PostgreSQL 16 (meta DB + per-project DBs + snapshot DBs)                  |
| Queue / pub-sub | Redis 7 (arq jobs + `run:{id}` event channels)                           |
| File storage    | local workspace dir (`$STRUCTAI_WORKSPACE`)                              |
| Profiling       | Polars                                                                    |
| Config          | pydantic-settings, env prefix `STRUCTAI_` (+ `.env`)                     |
| Deploy          | systemd (`structai-api`, `structai-worker`) + docker-compose infra       |
| Dev ports       | frontend `5173` → API `8000` · Postgres `5434` · Redis `6381`            |
