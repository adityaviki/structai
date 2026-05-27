# StructAI v2 — Implementation Plan & Decisions

A living document. We add a decision here as soon as it's made, and revise the
plan when later decisions force earlier ones to change.

---

## 1. Product summary

StructAI lets a user import arbitrary structured data (CSV, TSV, XLSX, JSON)
into a real database with the help of an LLM agent.

Mental model from the design prototype (`designs/`):

- A **project** is its own database. The user can have many projects.
- Inside a project, the user uploads **documents** (one file = one document).
- An **import** runs the agentic pipeline against one document. Selecting
  multiple documents starts one import pipeline per document.
- Pipeline steps: `profile → generate (import script) → execute → (fix on
  error, loop) → validate`. The agent may also ask **clarifying questions**
  when it has to make a judgment call (or it can run in "auto mode" and
  record its own decisions instead of pausing).
- The project page has tabs:
  1. **Data** — left: list of tables; right: rows in the selected table.
  2. **Imports** — list of runs and a detail view of each run.
  3. **Schema** — ER-style schema diagram.
  4. **Documents** — uploaded files.
- Only one import runs at a time per project (queue).

Frontend is already designed in `designs/` as a React + Vite + Tailwind app
with `react-router-dom` and `lucide-react`. We will adapt this prototype as
the real frontend, not rebuild it from scratch.

---

## 2. Decision log (chronological)

### D1 — Deployment & runtime model: **Local single-user app**

We build a localhost backend + the existing React frontend. The user runs it
on their own machine and accesses it from their own browser.

Consequences:

- **No auth.** Backend binds to `127.0.0.1` only by default.
- **Files and DBs live on the local filesystem.** A workspace directory holds
  every project's database file + uploaded documents + run logs.
- **LLM API key** lives in a local config file or env var; we never proxy a
  shared key.
- **Packaging:** target a `pip install` / `uv` invocation or a single binary;
  no Docker/SaaS infra required. Defer "real" desktop packaging (Electron,
  Tauri) until the web build works.
- Embedded databases (SQLite, DuckDB) become very attractive — no server to
  run alongside the app.

### D2 — Imported-data database: **PostgreSQL**

Each project maps to its own Postgres **database** inside a single Postgres
**instance**. So if the user has projects "marketing" and "hr", the instance
contains two databases: `structai_marketing` and `structai_hr` (names
slugified from the project, plus a uuid suffix to avoid collisions).

Consequences / things still to settle:

- We need a running Postgres process. **How it's provisioned is the next
  sub-decision** (user installs it / we auto-launch a bundled binary /
  Docker).
- Strong typing + real FKs are now a given — the agent's generated import
  script is expected to produce a properly-typed schema with FKs where it
  can infer them.
- Schema-diagram tab can lean on Postgres' rich `information_schema` /
  `pg_catalog` for introspection.
- Bulk ingest will use `COPY ... FROM STDIN` for speed, not row-by-row
  inserts.
- Backups: each project's database can be `pg_dump`'d to a file.

### D2a — Postgres provisioning: **User installs it themselves**

The user is responsible for having a running Postgres instance. The app reads
a connection URL from its local config (env var `STRUCTAI_PG_URL` or a
config file entry). The configured role needs `CREATEDB` (so we can create a
new DB when a project is created) and superuser is **not** required.

Consequences:

- First-run wizard / docs must clearly tell the user: install Postgres,
  create a role with `CREATEDB`, paste the URL into config.
- We must handle "Postgres unreachable" / "role lacks CREATEDB" errors
  gracefully — surface them in the UI, don't crash.
- We don't ship a Postgres binary or a Docker dependency. Smaller install,
  fewer cross-platform headaches.
- We can still expose a "Test connection" button in settings.

### D3 — Metadata layout: **Dedicated `structai_meta` DB + one DB per project**

The role's `CREATEDB` privilege is used to provision:

- `structai_meta` — created on first launch. Holds all app-level tables:
  `projects`, `documents`, `import_runs`, `pipeline_steps`,
  `clarifications`, `tables_catalog` (denormalized view of which tables live
  in which project DB), `app_settings`, etc.
- `structai_<slug>_<short-uuid>` — created when the user creates a project.
  Holds only the agent-imported tables.

Consequences:

- Backend must manage **two connection pools per project page**: one to
  `structai_meta`, one to the active project DB. Or one pool keyed by DB
  name with switching.
- Deleting a project is `DROP DATABASE structai_<slug>_<uuid>` + delete its
  rows from the meta tables. Cheap and atomic from the user's POV.
- "Project = a database" is literally true in the UI and on disk.
- We need an idempotent migration runner for the meta DB (so adding a new
  metadata column on app upgrade works cleanly). Initial choice:
  hand-rolled SQL migrations in a `migrations/` folder, applied in order
  with a `schema_migrations` tracking table. We can switch to Alembic etc.
  later if it becomes painful.

### D4 — Backend stack: **Python + FastAPI**

Concretely:

- **Language**: Python 3.12+.
- **Web framework**: FastAPI (async, Pydantic models for request/response).
- **DB driver**: `asyncpg` for Postgres. `psycopg[binary]` available as a
  fallback for sync paths (e.g. inside the import-script executor).
- **Data libs**: `polars` first (faster + leaner than pandas, lazy frames are
  great for profiling). `openpyxl` / `pyarrow` for XLSX. `chardet` or
  `charset-normalizer` for encoding detection.
- **LLM SDK**: `anthropic` (Python SDK). Will use prompt caching for the
  system prompt + per-document profile context.
- **Toolchain**: `uv` for env + dependency management, `ruff` for lint and
  format (single tool), `pytest` for tests, `mypy --strict` for type
  checking.
- **Server**: `uvicorn` for dev; bundled the same way for production
  (single-user, so no need for Gunicorn workers).
- **Process model**: FastAPI app process + a background worker (asyncio task
  inside the same process is enough at single-user scale — see D9).

### D5 — Agent orchestration: **Hybrid (deterministic outer pipeline + agentic inner loop)**

Pipeline stages are owned by deterministic Python code; only the messy /
generative parts call the LLM.

**Stages:**

1. **`profile`** _(deterministic)_ — Python code reads the document with
   polars / openpyxl / a CSV sniffer. Produces a structured `FileProfile`:
   delimiter, encoding, header row, sheet names (XLSX), column candidates
   with inferred type + null rate + sample values + cardinality, total
   bytes, total rows, sniffed quoting, etc. **No LLM call.**

2. **`generate`** _(LLM, single call by default, can loop)_ — Sends
   `FileProfile` + project schema context (existing tables, optional user
   instructions) to the model. Asks for:
   - a proposed table schema (DDL),
   - the body of an `import.py` script that takes the file path and a
     Postgres URL and ingests the rows,
   - a short rationale shown to the user.
   The model may call `ask_clarification(question, options)` *inside this
   step* and pause the run.

3. **`execute`** _(deterministic)_ — Runs the generated `import.py` in a
   sandboxed subprocess (see D6) with a timeout. Captures stdout, stderr,
   exit code, rows inserted.

4. **`fix`** _(LLM, looped, bounded retries)_ — On non-zero exit or
   exception, sends the error + the previous script + the file profile back
   to the model with tools `read_file_preview`, `query_db` (read-only on the
   project DB), `propose_schema_change`, `write_import_script`,
   `mark_unfixable`. Re-runs `execute`. **Hard cap: 5 fix attempts** to keep
   cost bounded — emit `failed` after that and surface the trace.

5. **`validate`** _(mostly deterministic, one optional LLM summary call)_ —
   Python checks: row counts match expectations, no orphan FKs, no
   all-NULL columns where data was expected, type sanity (no '12abc' in an
   integer column). The LLM is only called to write a human-readable
   summary of validation findings; it does not gate completion.

**Clarification handling:** when the model calls `ask_clarification`, the
import run transitions to status `needs_clarification`. The run's asyncio
task awaits a future that the API resolves when the user answers in the
UI. If `autoMode` is on, the run instead synthesizes an answer with an LLM
call (recorded as an `autoDecision`) and continues.

**Step boundaries in the UI:** the deterministic stages and the LLM stages
both emit `PipelineStep` rows with `status`, `summary`, optional `code`,
`attempts`, `errors`. The frontend types are already defined in
`designs/src/types.ts` and we'll keep that contract.

### D5a — Model: **User-configurable, default Claude Sonnet 4.6**

- Default model: `claude-sonnet-4-6`.
- Settings page exposes:
  - Model picker (Sonnet / Opus, and any future Anthropic models we
    whitelist).
  - Per-project override (optional; falls back to global default).
- API key source: env var `STRUCTAI_ANTHROPIC_API_KEY`, with a settings UI
  fallback that writes it to the local config file (chmod 600).
- **Provider scope (v1)**: Anthropic only. We wrap LLM calls in a thin
  `LlmClient` interface so a future OpenAI/Gemini provider can be added,
  but we don't build that abstraction beyond a single method until we need
  it.
- **Prompt caching**: the system prompt + tool schemas + (where it fits) the
  `FileProfile` for a given document are cached. Within a single run's fix
  loop, we cache the conversation prefix so each fix retry only pays for
  the new error message + new script delta.

### D6 — Import-script execution: **Subprocess, restricted but unsandboxed**

For each `execute` attempt:

- We write the generated script to
  `<workspace>/runs/<run_id>/attempt-<n>/import.py`.
- We spawn `python -u import.py <doc_path> <db_url>` as a subprocess with:
  - **CWD**: the attempt directory.
  - **Env**: only a curated allowlist (PATH, HOME, LANG, plus the
    `STRUCTAI_PG_URL_PROJECT` and `STRUCTAI_DOC_PATH` we set). No
    `STRUCTAI_ANTHROPIC_API_KEY` or other secrets are inherited.
  - **stdin/stdout/stderr**: captured.
  - **Timeout**: 5 minutes default, configurable per project.
  - **Resource limits**: `resource.setrlimit` for CPU time + virtual memory
    on Unix (best-effort).
  - **Network**: not blocked. Documented in the README: the script can hit
    the network if the LLM decides to (e.g. to look up a country code list).
    At single-user-on-your-own-machine scope this is an acceptable trust
    model, and many real import recipes need it. If we ever expose this
    over a network, we revisit with bubblewrap / Docker.
- We always **show the script in the run-detail UI** before execution starts
  (the UI already supports rendering `code` on a `PipelineStep`). We don't
  block on user approval by default — the run proceeds — but a planned
  "review-before-run" toggle lets the user gate it.

**Import-script language: Python.** The script uses `polars` (or `openpyxl`
for XLSX) to read, transforms in memory, and bulk-loads via psycopg's
`COPY FROM STDIN`. Pure SQL is too rigid for the messy cases (encoding
fixes, splitting one CSV into multiple tables, type coercion); a mixed
Python+COPY pattern is the right primitive.

### D7 — Auth: **None (inherited from D1)**

Server binds to `127.0.0.1` only. No login. A simple shared secret in the
config can optionally gate the API for users who want it on a LAN, but
that's a v1.x feature, not v1.

### D8 — File storage: **Local workspace directory (inherited from D1)**

```
$STRUCTAI_WORKSPACE/      # default: ~/.local/share/structai
  config.toml             # API key, PG url, model defaults
  documents/<doc_id>/<filename>     # original uploaded files, immutable
  runs/<run_id>/
    attempt-<n>/import.py           # each generated script
    attempt-<n>/stdout.log
    attempt-<n>/stderr.log
    profile.json                    # the FileProfile from stage 1
    transcript.jsonl                # full LLM transcript for debugging
```

Filenames stored in the metadata DB so renames don't break references.

### D9 — Queue & worker: **Redis + arq**

We use [`arq`](https://arq-docs.helpmanual.io/) as the async task queue,
backed by Redis. The FastAPI app enqueues jobs; an `arq` worker process
runs them.

- **Redis provisioning** follows the same model as Postgres: **user installs
  Redis themselves**. `STRUCTAI_REDIS_URL` in config (default
  `redis://127.0.0.1:6379/0`). Docs explain `pacman -S redis` /
  `brew install redis` / etc.
- **Process model**: two processes during development — `uvicorn` for the
  API and `arq worker structai.worker.WorkerSettings` for jobs. Both started
  by a single `make dev` (or equivalent) command. In production we ship the
  same two processes; a small `systemd --user` unit per process is fine for
  the local-app model.
- **One-at-a-time semantics**: `arq` is configured with
  `max_jobs=1`. The 'one import at a time' UX promise is then guaranteed
  by the worker, not by the API layer.
- **Run state of truth**: the `import_runs` row in Postgres is canonical.
  arq stores the job ID; the worker updates Postgres rows as steps advance.
  If the worker dies mid-run, on restart the worker sees a row in status
  `executing`/`fixing` with no live job — it marks it `failed` with an
  "interrupted" reason and the user can re-queue.
- **Pub/sub for live updates**: we also use Redis pub/sub channels
  (`run:<run_id>`) to push step transitions to subscribed HTTP clients
  (see realtime decision below).

### D10 — Realtime updates: **Server-Sent Events**

- `GET /api/runs/<run_id>/events` returns `text/event-stream`. Each event is
  JSON: `{ "type": "step_update", "step": {...} }`, `{ "type":
  "needs_clarification", "clarification": {...} }`, `{ "type":
  "completed" }`, etc.
- The endpoint subscribes to the Redis channel `run:<run_id>` and forwards
  messages to the client. On connect it also sends a snapshot event so the
  UI hydrates state immediately without an extra request.
- The browser uses `EventSource` (built-in, auto-reconnects). On reconnect
  we re-send the snapshot.
- For the **homepage's "active imports"** strip and the **Imports tab**
  list view, a single `GET /api/runs/active?stream=1` SSE endpoint emits
  list-level deltas (`run_started`, `run_progress`, `run_finished`) — one
  connection per page, not one per run.

### D11 — API conventions: **REST + JSON, versioned at `/api`**

- All endpoints under `/api/...`. Mirrors the existing frontend route shape
  where possible (`/api/projects`, `/api/projects/:id/documents`,
  `/api/projects/:id/imports`, `/api/projects/:id/tables/:tableId`, etc.).
- Pydantic models define request/response schemas; an OpenAPI doc is served
  at `/api/docs` (FastAPI default).
- IDs: ULIDs (sortable, URL-safe). Generated server-side.
- Errors: RFC 9457 problem details JSON (`type`, `title`, `status`,
  `detail`, `instance`).
- Pagination: cursor-based (`?cursor=...&limit=...`) for table data;
  offset-based for short admin lists (projects, documents).
- Timestamps: ISO-8601 UTC strings (`...Z`). The frontend already expects
  these.

### D12 — Repo layout: **Monorepo, `designs/` archived as reference**

```
structai-v2/
  backend/
    pyproject.toml          # managed with uv
    src/structai/
      api/                  # FastAPI routers (one file per resource)
      agent/                # LLM client, tools, prompts, orchestrator
      pipeline/             # profile / generate / execute / fix / validate
      db/                   # asyncpg pool, metadata models, migrations
      workspace/            # file storage helpers
      worker/               # arq worker entry + job functions
      schemas/              # Pydantic request/response models
      main.py               # FastAPI app factory
    migrations/             # SQL migrations for the meta DB
    tests/
  frontend/                 # copied from designs/ and evolved
    package.json
    src/
      api/                  # generated/handwritten typed client
      pages/, components/, hooks/, ...
  designs-archive/          # pristine prototype, read-only reference
  PLAN.md                   # this file
  README.md
  Makefile                  # `make dev`, `make test`, `make fmt`, `make lint`
  initial-idea.md
```

- Top-level `Makefile` orchestrates both sides:
  - `make dev` → starts Postgres-check, Redis-check, `uvicorn --reload`,
    `arq worker`, and `pnpm --filter frontend dev` concurrently (via a
    process manager like `overmind` or a simple `&` + trap).
  - `make test` → runs `pytest` and `pnpm test`.
  - `make fmt` / `make lint` → `ruff`, `mypy`, `pnpm lint`.
- Frontend package manager: **pnpm** (faster, stricter than npm).
- The first implementation step is to copy `designs/` → `frontend/` and
  rename the original to `designs-archive/`.

### D13 — Schema-diagram library: **ReactFlow + dagre**

- `@xyflow/react` for the diagram. Custom `TableNode` component renders the
  table name + a list of columns, each column row exposing a left- and
  right-side `Handle` so FK edges can connect column-to-column.
- `dagre` for initial auto-layout (`rankdir=LR`).
- We persist the user's manual node positions per-project so the layout is
  stable across reloads (`schema_layouts` table in the meta DB).
- Schema introspection (server-side): `information_schema.tables`,
  `columns`, `key_column_usage`, `referential_constraints` for the active
  project DB → returned as a normalized JSON blob the frontend renders.

### D14 — Data tab: **Read-only, server-paginated, sort + basic filters**

- UI: **TanStack Table v8** (headless), with our own Tailwind cell renderers
  matching the prototype's style.
- Server pagination: cursor on the table's primary key.
  `GET /api/projects/:id/tables/:table/rows?cursor=...&limit=100`.
- Sort: single-column for v1 (`?sort=col&dir=asc`). The query plan is
  trivial since we have a PK; multi-column sort is easy to add later.
- Filters: per-column. v1 supports equality, contains (text), and range
  (number/date) — encoded as `?filter=col:op:value&filter=...`. Backend
  builds parameterized SQL safely (never string-substitutes values).
- No editing in v1. We add an `editable: false` flag in the table-detail
  response so the UI can show the read-only state explicitly and we can
  flip the flag later when we ship editing.

### D15 — Undo: **Per-run template-DB snapshot + transactional execute**

Every successful import is undoable. The mechanism combines a transaction
around the script (cheap rollback on failure) with a Postgres template-DB
clone (per-run snapshot, used for user-initiated undo after the fact).

**Per-run flow:**

1. Before `execute` starts:
   - Drain the project DB connection pool.
   - `CREATE DATABASE structai_<slug>_snap_<run_id> TEMPLATE structai_<slug>;`
     (PG does a fast file-level copy; the source DB must have no other
     connections during the copy, which holds because imports are
     one-at-a-time and the pool is drained.)
   - Re-open the pool to the live DB.
   - Record `import_runs.snapshot_db = 'structai_<slug>_snap_<run_id>'`.
2. The script subprocess is given the **live** project DB URL and is
   expected to open a single connection, start a transaction, and do all
   work inside it. The prompt and the script scaffold enforce this — we
   provide the connection-opening boilerplate and the agent fills in the
   body.
3. After the subprocess exits:
   - Exit 0 + `validate` passes → `COMMIT`. Snapshot is kept as the undo
     point.
   - Exit non-zero, exception, or `validate` fails → `ROLLBACK`. Drop the
     snapshot DB; the run goes into `fixing` (or `failed` after the cap).
     The live DB is byte-identical to before the run, so the snapshot
     wasn't needed and we don't keep it.

**Undo flow (user clicks "Undo" on a completed run):**

1. Confirmation dialog:
   - "Undo last import" (LIFO case) — single confirmation.
   - "Undo an older import" — explicitly warns that all imports run *after*
     this one will also be reverted (because we're restoring to that
     run's pre-state). User must check a box to confirm.
2. Drain the pool.
3. Rename: `ALTER DATABASE structai_<slug> RENAME TO structai_<slug>_undone_<ts>;`
   then `ALTER DATABASE structai_<slug>_snap_<run_id> RENAME TO structai_<slug>;`.
   (Atomic from PG's POV — the project DB name is always either the old or
   the new, never half-renamed.)
4. Mark the undone run(s) as `status = 'reverted'` in metadata.
5. Schedule the `_undone_<ts>` DB for cleanup (immediate drop, or kept for
   a short grace period configurable in settings — default: drop
   immediately, since the snapshot we just promoted *is* the previous
   state).
6. Drop snapshot DBs belonging to any runs *after* the undone one (their
   snapshots are no longer valid rollback points because the DB they
   branched from no longer exists).

**Retention & disk:**

- Configurable in settings:
  - `undo.keep_last_n_per_project` (default: 10)
  - `undo.max_age_days` (default: 30)
  - `undo.disk_budget_gb_per_project` (default: unlimited)
- Background sweeper drops the oldest snapshots when limits are exceeded.
  When a snapshot is dropped, the corresponding run's "Undo" button is
  disabled and tagged "snapshot expired".
- A per-snapshot "Pin" toggle prevents auto-cleanup of a specific run's
  snapshot the user wants to keep around.

**Cost / trade-offs we accept:**

- Disk usage scales with kept snapshots × project DB size. For typical
  spreadsheet-shaped data this is small; we surface "snapshot disk used"
  in settings.
- "Undo an older import" reverts later imports too. This is the standard
  history-rewind semantics; we don't attempt per-table surgical undo.
- The agent is asked (via the script scaffold + prompt) to do all work
  inside a single transaction on the provided connection. If a malicious
  or buggy script bypasses this (opens its own connection, uses
  autocommit), the transaction guarantee weakens but the **snapshot still
  works for undo** — so we don't fail catastrophically, we just lose
  cheap-rollback-on-failure for that run.

### D17 — Stop / cancel: **Available at any time; pause deferred**

Any in-flight run can be cancelled by the user. Pause is **explicitly out
of scope for v1** (see rationale below).

**API & state:**

- New column `import_runs.cancel_requested boolean default false`.
- New statuses on top of the existing ones in
  `designs/src/types.ts`: `cancelling`, `cancelled`. (We'll extend the
  `ImportStatus` union in `frontend/`; `reverted` from D15 is also added.)
- `POST /api/runs/:id/cancel`:
  - Sets `cancel_requested = true`.
  - Publishes `run:<id>:cancel` on Redis pubsub so a blocked await wakes
    immediately.
  - Returns 202; the worker performs the actual cancellation work.

**Worker-side cancellation logic:**

The worker wraps each stage in `asyncio` tasks and checks
`cancel_requested` at every awaitable boundary. On cancel request:

- **`profile` / `validate`** (deterministic Python): the wrapper task is
  cancelled; the polars/pyarrow call is short and we let it finish or
  break the loop at the next iteration. Cheap.
- **`generate` / `fix`** (LLM call in-flight): the httpx stream is closed
  via task cancellation. Any partial output is discarded.
- **`execute`** (subprocess running): `proc.terminate()` → 3-second grace
  → `proc.kill()`. The subprocess's Postgres connection drops; PG rolls
  back the open transaction automatically. We then `DROP DATABASE` the
  per-run snapshot DB (it's now an orphan rollback point, never used).
- **`needs_clarification`** (suspended awaiting the user): the future is
  resolved with a `Cancelled` sentinel; the worker proceeds to cleanup.

After cleanup:

- Mark `import_runs.status = 'cancelled'`, set `finished_at`.
- Append a final `PipelineStep` with status `warning` and a summary
  describing what stage was interrupted.
- Emit an SSE `cancelled` event so the UI updates immediately.

Because of the transaction wrapper + snapshot cleanup, **the project DB is
guaranteed byte-identical to its pre-run state after cancel** — same
contract as a failed run. No special data-consistency handling needed.

**UI:**

- A "Stop" button on the run-detail view, visible whenever
  `status ∈ {queued, profiling, generating, executing, fixing,
  validating, needs_clarification}`.
- Click → confirmation dialog ("Stop this import? The project database
  will revert to its state before the import started."). Confirm →
  `POST /api/runs/:id/cancel`.
- While `cancelling`, the button is disabled and shows "Stopping…". The
  status badge in the imports list shows the same.
- Once `cancelled`, the run is final and not resumable. The user can start
  a new import from the same document if they want to retry.

**Edge cases:**

- Cancelling a `queued` run that hasn't started: trivial — dequeue
  (`arq.abort_job`) and mark `cancelled` immediately.
- Cancelling during snapshot creation: `CREATE DATABASE ... TEMPLATE`
  isn't cleanly cancellable mid-copy. We allow it to finish (small window,
  seconds) and *then* honor the cancel. The snapshot DB is dropped as
  part of cleanup.
- Double-cancel: idempotent — the second call returns 200 and does
  nothing.
- App restart while `cancelling`: on worker startup, any run found in
  `cancelling` or in an active stage is treated like a crashed run —
  marked `cancelled` (or `failed` if `cancel_requested` was not set),
  snapshots cleaned up.

**Why pause is deferred to "out of scope":**

- Pause inside `execute` is the only stage where a user would meaningfully
  want it (long-running on big files), and it isn't safely possible — we
  can't hold a Postgres transaction open for hours.
- Pause "between stages" is technically clean but cheap-feature: the only
  real interactive judgement moment is `needs_clarification`, which
  already pauses naturally. Adding pause everywhere else mostly buys a
  toggle for "I changed my mind", and `cancel` already covers that.
- We can revisit if users report a concrete workflow where stop + restart
  isn't good enough.

---

## 3. Decisions index

All of the foundational decisions are settled. Each links to the detail
section above.

| ID  | Decision                                  | Status |
| --- | ----------------------------------------- | ------ |
| D1  | Deployment & runtime model                | ✅      |
| D2  | Imported-data database                    | ✅      |
| D2a | Postgres provisioning                     | ✅      |
| D3  | Metadata layout                           | ✅      |
| D4  | Backend stack                             | ✅      |
| D5  | Agent orchestration shape                 | ✅      |
| D5a | LLM model defaults                        | ✅      |
| D6  | Import-script execution sandbox           | ✅      |
| D7  | Auth (inherited)                          | ✅      |
| D8  | File storage (inherited)                  | ✅      |
| D9  | Queue & worker                            | ✅      |
| D10 | Realtime updates                          | ✅      |
| D11 | API conventions                           | ✅      |
| D12 | Repo layout                               | ✅      |
| D13 | Schema-diagram library                    | ✅      |
| D14 | Data tab UX                               | ✅      |
| D15 | Undo / snapshots                          | ✅      |
| D16 | Implementation phasing                    | ✅      |
| D17 | Stop / cancel (pause deferred)            | ✅      |

Decisions that we *intentionally* defer until they bite us:

- Migration tooling (hand-rolled SQL is fine until it isn't; Alembic later).
- Multi-provider LLM abstraction (single Anthropic client until we ship a
  second provider).
- Bundled Postgres / Redis (only if users complain about setup).
- LAN-shared mode with a shared secret (Phase 7+ if anyone asks).

---

## 4. Architecture (summary)

A picture of what we just decided, end-to-end.

```
                                                    ┌──────────────────────┐
                                                    │  Anthropic API       │
                                                    │  (Claude Sonnet 4.6) │
                                                    └──────────┬───────────┘
                                                               │
┌──────────────┐    HTTP/JSON    ┌───────────────────────┐     │
│  React +     │ ──────────────► │  FastAPI (uvicorn)    │ ◄───┘
│  Vite        │ ◄────SSE─────── │  - REST under /api    │
│  (frontend/) │                 │  - SSE for run events │
└──────────────┘                 │  - Enqueues arq jobs  │
                                 └───────┬───────────────┘
                                         │ enqueue          ┌──────────────┐
                                         ▼                  │  Redis       │
                                 ┌───────────────────────┐  │  - arq queue │
                                 │  arq worker process   │◄─┤  - pubsub    │
                                 │  - runs pipeline      │  └──────────────┘
                                 │  - profile/generate/  │
                                 │    execute/fix/       │
                                 │    validate           │
                                 │  - publishes events   │
                                 └───┬─────────────┬─────┘
                                     │             │
                                     │             ▼
                                     │     ┌───────────────────────┐
                                     │     │  subprocess           │
                                     │     │    python import.py   │
                                     │     │    (sandbox-lite)     │
                                     │     └─────┬─────────────────┘
                                     │           │
                                     ▼           ▼
                              ┌────────────────────────────────────┐
                              │  PostgreSQL (user-installed)       │
                              │   - structai_meta                  │
                              │   - structai_<slug>_<uuid>  × N    │
                              │   - structai_<slug>_snap_<run> × N │
                              └────────────────────────────────────┘

   Local workspace: ~/.local/share/structai/{config.toml, documents/, runs/}
```

Process model in dev: `make dev` starts uvicorn + arq worker +
`pnpm --filter frontend dev`. All three on `127.0.0.1`.

---

## 5. Implementation phases

Each phase is end-to-end runnable on its own. We don't move on until the
previous phase's golden path works in a real browser.

### Phase 0 — Scaffolding (foundation, no product features yet)

Goal: `make dev` brings up an empty but real app skeleton.

- [ ] Move `designs/` → `designs-archive/` (read-only reference).
- [ ] Copy contents into `frontend/`, drop the mock-data wiring, leave the
      pages reachable but empty/loading.
- [ ] Create `backend/` with `pyproject.toml` (uv), FastAPI app factory,
      `/api/healthz`, ruff + mypy + pytest configured.
- [ ] `backend/migrations/001_init.sql` creates `structai_meta` with just
      a `schema_migrations` table.
- [ ] Startup check: confirm Postgres connectable, Redis connectable; print
      friendly errors and exit if not.
- [ ] `Makefile`: `dev`, `test`, `fmt`, `lint`, `migrate`.
- [ ] Vite proxy: `/api` → `http://127.0.0.1:8000` in dev.
- [ ] Single arq worker process boots with one no-op job.

### Phase 1 — Vertical slice: single CSV → table you can view

Goal: user creates a project, uploads one well-formed CSV, runs an import,
sees the table appear under the Data tab. No fix loop, no clarifications,
no XLSX/JSON, no schema diagram, no undo yet.

Backend:

- [ ] Meta DB migrations: `projects`, `documents`, `import_runs`,
      `pipeline_steps`.
- [ ] `POST /api/projects` — creates project + `CREATE DATABASE` for it.
- [ ] `GET /api/projects` / `GET /api/projects/:id`.
- [ ] `POST /api/projects/:id/documents` — multipart upload, stores file
      under `workspace/documents/<doc_id>/`.
- [ ] `POST /api/projects/:id/imports` — enqueues an arq job.
- [ ] Pipeline `profile`: polars-based CSV sniffer producing `FileProfile`.
- [ ] Pipeline `generate`: single LLM call. Returns DDL + `import.py` body.
- [ ] Pipeline `execute`: writes script, spawns subprocess with env
      allowlist + 5-min timeout, captures logs.
- [ ] Pipeline `validate`: row count match + no all-null columns.
- [ ] `GET /api/runs/:id` — full run state.
- [ ] `GET /api/runs/:id/events` — SSE stream of step transitions.
- [ ] `GET /api/projects/:id/tables` — introspect via `information_schema`.
- [ ] `GET /api/projects/:id/tables/:name/rows` — cursor-paginated.

Frontend:

- [ ] Typed API client (handwritten or generated from OpenAPI).
- [ ] Home page wired to real `/api/projects`, "New project" works.
- [ ] Project page Documents tab supports CSV upload.
- [ ] "New import" modal — pick uploaded doc → start.
- [ ] Imports tab list + run-detail view consume the SSE stream.
- [ ] Data tab lists tables and shows rows (read-only, no filters yet).

Exit criteria: download a standard sample CSV, walk through the full UX,
see the imported table.

### Phase 2 — Robustness: fix loop, transactional execute, undo

Goal: imports survive realistic CSV messiness; the user can undo a
completed import.

- [ ] `execute` opens a transaction; script template forces the agent to
      use the supplied connection.
- [ ] On failure: ROLLBACK, then enter `fix` stage. Fix loop with hard cap
      (5 attempts), each attempt is a separate `PipelineStep` with the
      latest stderr + previous script as input.
- [ ] Before execute: `CREATE DATABASE ... TEMPLATE` snapshot (pool drained
      and restored). Snapshot DB name recorded on the run.
- [ ] On failure path: drop the unused snapshot.
- [ ] `POST /api/runs/:id/undo` — drain pool, atomic rename swap, mark run
      `reverted`, drop snapshots of later runs.
- [ ] Frontend: "Undo" button on completed runs with confirmation dialog.
      "Reverted" status badge.
- [ ] Background sweeper job: enforces `keep_last_n` retention.
- [ ] **Stop / cancel** (D17): `cancel_requested` column, `POST
      /api/runs/:id/cancel`, Redis pubsub wake, worker cancellation at
      every stage boundary, subprocess termination + snapshot cleanup on
      cancel. UI: "Stop" button + "Stopping…" / "Cancelled" status.
- [ ] Worker restart recovery: crashed/cancelling-on-restart runs marked
      `failed` or `cancelled` and their snapshots dropped.

### Phase 3 — Clarifications & auto mode

Goal: agent can pause and ask the user when it has to make a judgment
call; or, with auto mode on, records its own decision and continues.

- [ ] Agent tool `ask_clarification(question, options[])`.
- [ ] On tool call: run transitions to `needs_clarification`, persists the
      question, suspends the worker job (await asyncio.Future, woken by
      `POST /api/runs/:id/clarifications/:cid/answer`).
- [ ] Frontend: clarification UI inside run-detail panel.
- [ ] `autoMode` flag at import creation. When set, the worker synthesizes
      an answer with a follow-up LLM call (separate, cached) and records
      it as an `autoDecision` instead of pausing.

### Phase 4 — XLSX / JSON / TSV & multi-table generation

Goal: support every format from the type union, and let the agent split a
file into multiple related tables with FKs.

- [ ] Profile stage: sheet enumeration for XLSX (pick one or "all"),
      JSON-structure detection (object-of-arrays, array-of-objects,
      newline-delimited), TSV sniffing.
- [ ] Generator prompt and script template support producing multiple
      `CREATE TABLE`s and `COPY`s in one script.
- [ ] Documents tab shows previews specific to format (sheet picker, JSON
      tree).

### Phase 5 — Schema diagram tab

Goal: live ER diagram of the project DB.

- [ ] `GET /api/projects/:id/schema` — tables + columns + FKs from
      `information_schema` / `pg_catalog`.
- [ ] `schema_layouts` table for persisted node positions per project.
- [ ] `@xyflow/react` + custom `TableNode` with per-column handles.
- [ ] `dagre` for initial layout; drag-to-rearrange persists positions.

### Phase 6 — Polish, settings, retention UX

Goal: the product feels finished.

- [ ] Data tab: per-column sort + filters (equality / contains / range).
- [ ] Settings page: API key, default model, per-project model override,
      `STRUCTAI_WORKSPACE` location, snapshot retention knobs.
- [ ] Snapshot dashboard per project: disk used, list of snapshots, pin /
      drop controls.
- [ ] Project deletion: confirmation, drops all project + snapshot DBs,
      removes workspace files.
- [ ] Documents tab: previews, rename, delete (with safety if referenced
      by an import).
- [ ] First-run onboarding screen: walks through PG URL, Redis URL, API
      key configuration.

### Out of scope for v1 (parking lot)

- Multi-user / auth.
- Editing rows in the Data tab.
- Cross-project queries.
- Cloud sync / backup.
- Multiple LLM providers (OpenAI, Gemini).
- Bundled Postgres / Redis.
- Desktop packaging (Electron / Tauri).
- **Pause / resume of in-flight imports** (D17). Stop + restart covers the
  common cases; `needs_clarification` already gives the only natural
  "wait for the human" pause point. Revisit if a real workflow needs it.
