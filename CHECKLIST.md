# StructAI — Implementation Checklist

Tracks progress against [`plans/plan.md`](plans/plan.md). Phase numbering and section references (§N) are the plan's. Tick items in the **same commit** as the change that lands them, and add a corresponding `CHANGELOG.md` bullet under `[Unreleased]` for anything user-visible.

**Status keys:** `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` intentionally skipped (leave a note).

---

## Phase 0 — Monorepo scaffold + data model *(plan §10, 1 day)*

### Repo & tooling
- [x] `pyproject.toml` at root configured as a `uv` workspace, with members `apps/api`, `apps/worker`, `packages/core`
- [x] `pnpm-workspace.yaml` covering `apps/web` (and any shared TS packages)
- [x] `docker-compose.yml` with Postgres 16 only (no Redis)
- [x] `Makefile` or `mise.toml` providing `make dev` (Postgres up, API + worker + web in watch mode)
- [x] `ruff` config + format/lint scripts (Python)
- [x] `biome` config + format/lint scripts (TypeScript)
- [ ] OpenAPI generator wired so `apps/web/src/api/` consumes types emitted from `apps/api`
- [x] `.env.example` documenting required env vars (DB URL, anthropic key, `STRUCTAI_ALLOW_RAW_LLM_SAMPLES`)

### App skeletons
- [x] `apps/api/src/structai_api/main.py` — FastAPI app with `/healthz` ping
- [~] `apps/api/src/structai_api/deps.py` — DB session, settings *(settings wired; async session lands with migrations)*
- [x] `apps/api/src/structai_api/stream.py` — SSE plumbing stub backed by `event_log`
- [x] `apps/api/src/structai_api/routes/` — empty modules for `files`, `sessions`, `jobs`, `schemas`, `pipelines`, `runs`, `tables`
- [~] `apps/worker/src/structai_worker/main.py` — polling loop skeleton *(boot + signal handling; FOR UPDATE SKIP LOCKED poll arrives in commit 4)*
- [~] `apps/worker/src/structai_worker/lease.py` — heartbeat + reaper hooks *(stub; impl in commit 4)*
- [x] `apps/worker/src/structai_worker/tasks.py` — dispatch into `packages/core`
- [x] `apps/web` — Vite + React 18 + TS bootstrapped; root route renders "ok"
- [x] `packages/core/src/structai_core/` — empty namespace packages for `io`, `profile`, `agent`, `ir`, `schema`, `script`, `execute`, `store`, `eval`

### Postgres migrations *(plan §4)*
All migrations land in Phase 0 so every later phase writes to a stable schema.

- [ ] `files` — `id`, `original_name`, `bytes`, `source_sha256`, `quarantine_path`, `live_path`, `uploaded_at`, `retention_until`
- [ ] `profiles` — `id`, `file_id` FK, `profile_sha256`, `profile_jsonb`, `created_at`
- [ ] `agent_sessions` — `id`, `file_id` FK, `created_at`, `cost_tokens_in`, `cost_tokens_out`, `status`
- [ ] `pipeline_revisions` — `id`, `session_id` FK, `parent_id` FK, `ir_version`, `ir_jsonb`, `ir_sha256`, `state`, `created_by` (`agent` / `user_edit`), `created_at`; **append-only content invariant** documented in code
- [ ] `pipeline_artifacts` — `id`, `revision_id` FK, `kind` (`pipeline_py` / `manifest_json` / `dry_run_report`), `path`, `sha256`
- [ ] `jobs` — `id`, `kind`, `payload_jsonb`, `idempotency_key`, `status`, `locked_at`, `locked_by`, `lease_expires_at`, `heartbeat_at`, `attempts`, `max_attempts`, `error_class` (`retryable` / `terminal`), `last_error`, `cancel_requested`, `created_at`, `finished_at`
- [ ] `event_log` — `id` bigserial (monotonic), `session_id` FK, `kind`, `payload_jsonb`, `created_at`
- [ ] `event_cursors` *(optional, not wired in v1)* — `session_id` FK, `client_id`, `last_event_id`, `updated_at`
- [ ] `import_runs` — `id`, `revision_id` FK, `status`, `started_at`, `finished_at`, `dry_run_only`
- [ ] `import_run_tables` — `id`, `run_id` FK, `table_name`, `load_mode`, `rows_inserted`, `rows_updated`, `rows_rejected`
- [ ] `rejected_row_artifacts` — `id`, `run_id_table_id` FK, `path`, `count`
- [ ] `pipeline_registry` *(used in v1.3)* — `id`, `fingerprint`, `revision_id` FK, `last_seen_file_id` FK
- [ ] Managed user schema `structai_user` created by migration (configurable name)

### Worker job-queue plumbing
- [ ] Poller using `SELECT ... FOR UPDATE SKIP LOCKED`
- [ ] Lease acquisition: set `locked_at`, `locked_by`, `lease_expires_at` atomically
- [ ] Heartbeat task refreshes `heartbeat_at` and extends `lease_expires_at` while job runs
- [ ] Stale-job reaper recycles jobs whose `lease_expires_at` has passed
- [ ] Idempotency-key dedup on enqueue (returns existing job if key collides)
- [ ] Retryable vs terminal error classification, with `attempts` / `max_attempts` policy
- [ ] `cancel_requested` flag honored at step boundaries; cancellation path tested

---

## Phase 1 — CSV/TSV profiler + file manager *(plan §10, 3 days)*

### `packages/core/io/`
- [ ] `sniff.py` — encoding detection, delimiter detection, header detection (CSV/TSV only)
- [ ] `readers.py` — unified `Reader` interface; CSV and TSV implementations (Excel deferred to v1.1)

### `packages/core/profile/` — deterministic profile *(plan §5)*
- [ ] `columns.py` — per-column compute: `name`, `position`, `inferred_type`, `null_count`, `null_rate`, empty-string-vs-null distinction
- [ ] `columns.py` — `distinct_count` over full data, `cardinality_class`, `min`, `max`, quantiles (`p1`, `p50`, `p99`)
- [ ] `columns.py` — top-K (K=10) with counts for low-cardinality columns
- [ ] `columns.py` — string length stats (min, max, p50, p99)
- [ ] `types.py` — type inference incl. **leading-zero detection** (ZIPs, SKUs stay `string`)
- [ ] `types.py` — **decimal / thousands separator detection** (`1.234,56` vs `1,234.56`)
- [ ] `types.py` — currency / percent / unit detection
- [ ] `types.py` — **type-preservation rule**: number-looking columns that fail PK / range but pass leading-zero or fixed-width checks stay `string`
- [ ] `patterns.py` — regex bank, `pattern_hits` per column
- [ ] `patterns.py` — **date format candidates** with parse success rates
- [ ] `patterns.py` — timezone hints (offsets seen, naive vs aware)
- [ ] `heuristics.py` — **PK score** (uniqueness + non-null + stable-looking ID)
- [ ] `heuristics.py` — outlier examples (extreme values; redacted if PII)
- [ ] `pii.py` — high-confidence detectors: `email`, `phone`, `ip`, `national_id`, `cc_like`
- [ ] `pii.py` — best-effort detectors: `name_like`, `address_like` (surfaced as warnings, not guarantees)
- [ ] `pii.py` — **default redaction** for any LLM-bound surface: typed placeholders (`<EMAIL_1>`, `<PHONE_3>`) on sample values **and** top-K values
- [ ] `pii.py` — raw values written only to local profile artifacts under `./data/profiles/`
- [ ] `pii.py` — honors `STRUCTAI_ALLOW_RAW_LLM_SAMPLES=true` dev opt-out
- [ ] **Wide-file truncation policy** (plan §5): file-level stats always; compact column index always; rich stats only for top-N highest-uncertainty columns; omitted columns listed by name with reason; target <30 KB

### `packages/core/schema/`
- [ ] `identifiers.py` — column-name sanitization: trim, NFKC normalize, replace non-alphanum with `_`, collapse repeats, lowercase, prepend `_` if starts with digit, suffix `_N` on collisions, reject Postgres reserved words (rewrite with `_col` suffix)
- [ ] Raw→safe column-name mapping persisted on the profile so the UI and IR both see it

### File-level profile fields
- [ ] `row_count`, `duplicate_row_count`, `encoding`, `delimiter`, `has_header`, `source_sha256`, `profile_sha256`, `profile_version`

### Worker task
- [ ] `profile_file` task in `apps/worker/tasks.py` dispatching into `packages/core/profile/`

### API
- [ ] `POST /files` — multipart upload, lands in `./data/uploads/quarantine/`, then moves to live area after sniffing succeeds
- [ ] `POST /files` — enforces upload size limit (default 200 MB, configurable)
- [ ] `GET /files` — list with status
- [ ] `GET /files/:id/profile` — returns the profile JSON

### UI
- [ ] `apps/web/src/components/FileManager.tsx` — drag-drop upload
- [ ] File list with profiling status
- [ ] Profile drawer showing per-column stats with PII placeholders visible

### Fixture suite — CSV/TSV only
- [ ] BOM
- [ ] Semicolon-delimited
- [ ] Mixed-types column
- [ ] All-null column
- [ ] Single-row file
- [ ] German decimals (`1.234,56`)
- [ ] Leading-zero IDs
- [ ] Embedded newlines in quoted fields
- [ ] Ragged rows

---

## Phase 2 — Agent loop + IR (single-table) + chat sidebar *(plan §10, 4 days)*

### `packages/core/ir/` — pydantic models *(plan §6.1, §6.2)*
- [ ] `model.py` — IR root with `ir_version: "2026-05-structai-v1"`, `source`, `tables`
- [ ] `model.py` — `Column` model (`name`, `type`, `pk`, `nullable`)
- [ ] `model.py` — `Table` model (`name`, `load_mode`, `upsert_key`, `columns`, `ops`)
- [ ] `ops.py` — `rename`
- [ ] `ops.py` — `drop_column`
- [ ] `ops.py` — `cast` with `on_error` (default `reject`; `null` / `fail` opt-in)
- [ ] `ops.py` — `parse_date` / `parse_datetime` (format string only)
- [ ] `ops.py` — `normalize_string` (trim/case flags only — no DSL)
- [ ] `ops.py` — `map_enum` (static dict; `on_unmapped` optional reject)
- [ ] `ops.py` — `derive_column` with **whitelisted DSL** (v1 allowed: column refs, string/numeric literals, `concat`, `substr`, `upper`, `lower`, `coalesce`)
- [ ] `ops.py` — `reject_row` with predicate DSL
- [ ] `ops.py` — `dedupe`
- [ ] `ops.py` — `set_pk`
- [ ] `ops.py` — `set_upsert_key`
- [ ] `ops.py` — **always disallowed in DSL**: arbitrary attribute access, imports, function defs, regex compilation
- [ ] `validate.py` — op-semantics validators: each op declares input/output columns, null/error behavior, row-count effect, rejected-row eligibility
- [ ] `validate.py` — null-behavior uniformity: any op reading null produces null unless schema says otherwise
- [ ] `lifecycle.py` — state machine type (`proposed_ir`, `user_edited_ir`, `validated_ir`, `dry_run_passed`, `approved_for_execution`, `executed`); legal transitions enforced

### `packages/core/agent/` — LangGraph state machine *(plan §7)*
- [ ] `graph.py` — LangGraph state machine using `langchain-anthropic`
- [ ] `graph.py` — Haiku-first routing (`claude-haiku-4-5`), Opus escalation (`claude-opus-4-7`) on low-confidence
- [ ] `tools.py` — `get_column_samples(column, n, strategy)` with strategies `random`, `nulls`, `extremes`, `regex_match`; output redacted by default
- [ ] `tools.py` — `count_values(column, where=None)`
- [ ] `tools.py` — `match_regex(column, pattern)`
- [ ] `tools.py` — `parse_as(column, target_type, format=None)` reporting failure rate
- [ ] `tools.py` — `propose_pipeline(ir)` — terminator, schema-validated against IR pydantic model
- [ ] `prompts.py` — system prompt explicitly marks profile contents as untrusted
- [ ] `prompts.py` — profile sent as structured JSON, never inlined as prose
- [ ] `injection.py` — defenses: schema-validated terminator, tool-arg pydantic validation, no Python/SQL strings ever emitted
- [ ] `decisions.py` — per-decision evidence captured (used by Schema Review)
- [ ] **Cost tracking** per session — `cost_tokens_in` / `cost_tokens_out` updated on `agent_sessions`
- [ ] **Mock-LLM mode** for tests (canned tool traces)

### Worker task
- [ ] `run_agent_session` task

### SSE event stream
- [ ] `apps/api/src/structai_api/stream.py` — SSE endpoint backed by `event_log`
- [ ] LangGraph callbacks emit `tool_call_start`, `tool_call_result`, `message_delta`, `pipeline_proposed`, `cost_update`
- [ ] Resume via `Last-Event-ID` header from `event_log` (per-client `event_cursors` deferred)

### UI
- [ ] `apps/web/src/components/ChatSidebar.tsx` — streams tool calls + messages
- [ ] Free-text nudge input feeds next agent turn

### Eval harness boots *(plan §15)*
- [ ] `packages/core/eval/` skeleton with `pytest -m eval` marker
- [ ] Golden IR fixture loader; human-readable diff
- [ ] Prompt-injection fixture cases (malicious column names + sample values)
- [ ] PK-score regression cases
- [ ] Profiler regression tests (hand-labeled column types and PK scores)
- [ ] PII detection cases (must-fire and must-not-fire)
- [ ] Per-fixture cost tracking; CI fails on >20% regression

---

## Phase 3 — Schema review + IR validation + pipeline viewer *(plan §10, 3 days)*

### IR lifecycle wiring *(plan §6.4)*
- [ ] State transition `proposed_ir → validated_ir` when agent terminates and validator passes (no edit needed)
- [ ] State transition on user edit → new `pipeline_revisions` row with `parent_id`, starts at `user_edited_ir`
- [ ] State transition `user_edited_ir → validated_ir` on validator pass
- [ ] **No `import_runs` job may be enqueued** from a state earlier than `approved_for_execution` — enforced server-side

### IR validator
- [ ] All referenced source columns exist
- [ ] Op ordering valid (target columns produced before use)
- [ ] Load mode has required keys (e.g. `upsert_key` present when `load_mode = upsert`)
- [ ] Type changes compatible with downstream ops
- [ ] Rejected-row rules still make sense
- [ ] FK references point to real tables/columns *(deferred to v1.2)*

### API
- [ ] `GET /sessions/:id/pipeline` — current revision
- [ ] `PATCH /pipelines/:id` — apply user edits → write new revision row → re-validate

### IR → Python generator
- [ ] `packages/core/script/templates.py`
- [ ] `packages/core/script/generator.py` — IR → readable `pipeline.py` (pandas), stored as `pipeline_artifacts` row
- [ ] Output is **not executed by the server** (artifact only); contract documented in code

### UI
- [ ] `apps/web/src/components/SchemaReview.tsx` — editable cards per table/column
- [ ] Rename tables / columns
- [ ] Change SQL types
- [ ] Mark / unmark primary keys
- [ ] Choose load mode per table
- [ ] Approve / reject each transformation op
- [ ] Show confidence + evidence for every agent decision
- [ ] **Destructive-action warnings** as required confirmations *(plan §6.6)*:
  - [ ] `replace` mode → "this will `TRUNCATE` the target table `X`"
  - [ ] Overwriting an existing managed table → "target table `X` already exists"
  - [ ] `nullable: true → false` when dry-run shows nulls → "M rows have null `X` and will be rejected"
  - [ ] Type narrowing (e.g. `text → int`, `timestamp → date`) → "this cast may lose precision; dry-run rejected M rows"
  - [ ] Dropping a column that exists in source → "column `X` will not be loaded"
  - [ ] PII column being loaded raw → "column `X` is detected as `email`; stored in raw form"
  - [ ] Dry-run rejected rows → "M rows will be rejected on load"
- [ ] `apps/web/src/components/PipelineViewer.tsx` — read-only Python with syntax highlighting; banner: "this script is generated from the IR and isn't editable"

---

## Phase 4 — Execute + validate + COPY load (single-table) *(plan §10, 3 days)*

### `packages/core/execute/`
- [ ] `interpreter.py` — runs v1 op set against Polars frames
- [ ] `interpreter.py` — dry-run pass: per-op `rows_in`, `rows_rejected`, reasons; **no DB writes**; advances revision to `dry_run_passed`
- [ ] `contract.py` — **pre-COPY contract** *(plan §8.3)*:
  - [ ] Column order matches staging table DDL exactly
  - [ ] No nulls in non-nullable columns (rejected before serialization)
  - [ ] Strings escaped per chosen `COPY` format (default `CSV`, `QUOTE '"'`, `ESCAPE '"'`)
  - [ ] **Date / time formatting** *(plan §8.3.4)*:
    - [ ] `date` → `YYYY-MM-DD`, no time, no offset
    - [ ] `timestamp` (no tz) → ISO-8601 local, **no offset suffix**; naive stays naive
    - [ ] `timestamptz` → ISO-8601 with offset (`...+00:00`); naive sources **rejected** unless IR applies a timezone
  - [ ] Numeric columns use `.` decimal separator regardless of source locale
  - [ ] Rejected rows already separated and counted
  - [ ] Staging schema exists and matches serialized header
- [ ] `copy.py` — psycopg3 `COPY FROM STDIN` from a temp Arrow/CSV file
- [ ] `modes.py` — `append` (`INSERT ... SELECT` from staging)
- [ ] `modes.py` — `replace` (`TRUNCATE` target, then insert; **does not** `DROP TABLE`)
- [ ] `modes.py` — `upsert` (`INSERT ... ON CONFLICT (upsert_key) DO UPDATE`)
- [ ] `modes.py` — `fail_if_duplicate` (`INSERT`, fail on any key conflict)
- [ ] `validate.py` — row counts vs source
- [ ] `validate.py` — null-rate tolerances vs profile
- [ ] `validate.py` — PK uniqueness
- [ ] `validate.py` — sample round-trip

### Target table policy *(plan §8.2)*
- [ ] All target tables live in managed schema (default `structai_user`)
- [ ] DDL generated deterministically from validated IR with column-name sanitization (§5)
- [ ] Table created in commit transaction if missing; PK / `NOT NULL` at creation; secondary indexes after `COPY`, same transaction
- [ ] **Existing managed table** → run stops; schema review surfaces conflict; user must pick `replace` or rename target
- [ ] **Tables outside managed schema**: v1 never writes or drops (no IR path to arbitrary schema)
- [ ] **No `DROP TABLE`** anywhere in v1
- [ ] Type changes on existing managed tables **rejected by validator** in v1 (schema evolution → v1.3)

### Execution idempotency *(plan §8.4)*
- [ ] `import_run_id` allocated and `import_runs` row inserted **before** any staging table
- [ ] Staging tables named `stage_<import_run_id>_<table>`
- [ ] Final commit is a single transaction (no partial loads)
- [ ] Retry policy keyed by `import_runs.status`:
  - [ ] `committed` → no-op, return existing result
  - [ ] `failed_before_commit` → drop leftover `stage_<import_run_id>_*` tables, re-execute from step 1
  - [ ] `running` + expired lease → reaper marks `failed_before_commit`; above path applies
  - [ ] `running` + live lease → retry refuses to start
- [ ] `cancel_requested` checked at every step boundary; cancellation rolls back staging and marks run `cancelled`

### Loaded-row metadata + rejected-rows
- [ ] Every loaded row carries `import_run_id` (FK to `import_runs`)
- [ ] Rejected rows written to `./data/rejected_rows/<run_id>.parquet`
- [ ] `rejected_row_artifacts` row inserted with count + path

### Worker task
- [ ] `execute_pipeline` task

### API
- [ ] `POST /runs` — accepts **only** revisions in `approved_for_execution` (server-enforced)
- [ ] SSE progress streamed via `event_log`

### UI
- [ ] Dry-run report (per-op rejection counts + reasons)
- [ ] Destructive-action warning modals from §6.6
- [ ] Run button gated on `dry_run_passed`
- [ ] Validation panel post-run
- [ ] Rejected-rows drawer (sample + count + download link)

### Eval cases added in this phase
- [ ] DDL generation snapshots per fixture IR
- [ ] Identifier sanitization & collision tests (Unicode, leading-digit, repeated punctuation, two columns sanitizing to same name)
- [ ] Postgres reserved-word tests (`select`, `order`, `from`, `user`)
- [ ] Per-mode load-mode SQL tests (`append`, `replace`, `upsert`, `fail_if_duplicate`) with asserted row counts + final-state queries
- [ ] Transaction rollback tests (inject post-`COPY` validator failure; assert no rows landed, staging cleaned)
- [ ] Retry / idempotency tests (kill worker between `COPY` and commit; restart; assert §8.4 matrix)
- [ ] Pre-COPY contract tests (nulls in non-null cols, wrong column order, naive ts into `timestamptz`, locale-formatted numbers — each caught before `COPY`)

---

## Phase 5 — Table browser *(plan §10, 1 day)*

- [ ] API: `GET /tables` — Postgres introspection of `structai_user` schema
- [ ] API: `GET /tables/:name/rows?page=...` — paginated rows
- [ ] UI: `apps/web/src/components/TableBrowser.tsx` — tables list, paginated rows, column types displayed

### v1 Definition of Done *(plan §13)*
Verify by walking the full flow end-to-end:
- [ ] Open the web app
- [ ] Upload `sales_q3.csv` via the file manager
- [ ] See deterministic profile; PII detected and redacted in any LLM-bound preview
- [ ] Start an agent session
- [ ] Watch agent propose a **single-table** IR with streamed tool calls
- [ ] Schema review: per-decision evidence visible; can nudge agent in chat; can edit names/types/load mode; approve
- [ ] Trigger dry-run; see per-op rejection counts + validation summary
- [ ] Trigger run: data flows through staging via `COPY FROM STDIN`; validators run; rows commit
- [ ] Browse new table; paginate rows; see rejected rows + validation report
- [ ] Open pipeline viewer; see generated Python; banner clarifies it's non-executable

**🎯 v1 ships here.**

---

## v1.1 — Excel support *(plan §10, 3 days)*

### Reader integration
- [ ] `calamine` integration in the `Reader` interface — `.xls`, `.xlsx`, `.xlsm`, `.xlsb`, `.ods`
- [ ] `openpyxl` fallback for formula-only cells
- [ ] `.xlsm` / `.xlsb` treated as **data-only**: macro streams (`vbaProject.bin`) **ignored, never extracted, never executed**
- [ ] Macro presence flagged in the profile so Schema Review shows a warning

### Excel-specific profile fields
- [ ] `sheet_name`, `sheet_count`, `hidden_sheets`
- [ ] 1900 vs 1904 date system detection
- [ ] Formula vs value cells distinguished

### Sheet & header confirmation UI
- [ ] Before profiling a multi-sheet or merged-cell workbook, user picks sheet + header row
- [ ] Defaults inferred but never silently committed

### Fixture suite
- [ ] Multi-sheet
- [ ] Hidden sheets
- [ ] Merged cells
- [ ] Multi-row headers
- [ ] Excel serial dates
- [ ] 1900 vs 1904 date system
- [ ] `.xlsm` (macro stream must be ignored)
- [ ] `.xlsb`
- [ ] Formula-only cells

---

## v1.2 — Normalization *(plan §10, 4 days)*

### IR additions
- [ ] `split_from` on `Table`
- [ ] `natural_key` on `Table`
- [ ] `foreign_keys` on `Table`
- [ ] `split_table` op
- [ ] `set_foreign_key` op
- [ ] FK references validated against real tables/columns (extends Phase 3 validator)

### Agent
- [ ] `cross_tab(col_a, col_b)` tool for functional-dependency detection

### Surrogate keys *(plan §6.3)*
- [ ] Identity-based generation in staging tables (never `df.index + 1`)
- [ ] `INSERT ... ON CONFLICT (natural_key) DO NOTHING RETURNING id` for stable FK resolution across re-imports

### Validators
- [ ] FK integrity between split tables

### UX — opt-in normalization
- [ ] Default execution mode stays single-table even when agent proposes splits
- [ ] Each proposed split rendered as a Schema Review card with: FD strength, conflict count, sample rows
- [ ] User must accept each split explicitly; first successful run never surprises with five tables when one was expected

### Profile additions
- [ ] **FK / dimension score** per column (low cardinality + repeated across columns)

### Eval cases
- [ ] Normalization false-positive cases (correlation looks like FD but conflict count too high)
- [ ] Known-good multi-table splits with expected IRs

---

## v1.3 — Reuse & iteration + extended load modes + DSL extensions *(plan §10, 3 days)*

### Fingerprinting & registry
- [ ] Every successful run computes a fingerprint: column-name set + inferred types + sample-hash + file shape
- [ ] `pipeline_registry` populated on successful runs
- [ ] Pipeline artifacts archived under `./data/pipelines/<dataset>/<revision_id>/` as `(ir.json, manifest.json, pipeline.py)`
- [ ] New uploads run a fingerprint match; UI surfaces matches

### Compatibility check *(plan §9)*
- [ ] Missing columns (in prior IR but not new file)
- [ ] New columns (in new file but not prior IR)
- [ ] Changed date formats
- [ ] Changed enum values
- [ ] Type drift
- [ ] PK drift (uniqueness lost)
- [ ] Null-rate drift

### Pin-prior-pipeline flow
- [ ] **Compatible** → straight to `approved_for_execution` after user confirm
- [ ] **Drifted but adaptable** → agent invoked with prior IR + rationale + compatibility report; emits new revision
- [ ] **Incompatible** → fresh agent run with prior context

### Revision pass on failure
- [ ] On validation failure, agent gets the failure diff as a new turn; re-emits IR

### Extended load modes
- [ ] `merge` — natural-key match → update, else insert
- [ ] `version` — insert with new `import_run_id`; never overwrites prior rows

### Schema evolution
- [ ] Additive column changes on existing managed tables via the compatibility flow

### DSL extensions for `derive_column`
- [ ] Arithmetic (`+`, `-`, `*`, `/`)
- [ ] Comparisons
- [ ] `case when`

### UI
- [ ] Cost tracker per session, surfaced in UI

---

## Hardening *(plan §10, ongoing)*

- [ ] Concurrency limits per workspace
- [ ] Cancellation + retries on jobs (Phase 0 plumbing; this phase tunes policy)
- [ ] Snapshot tests on generated Python
- [ ] Raw-source archive retention policy enforced (default 30 days; explicit purge endpoint)
- [ ] Audit-log surfacing in UI (who/what/when/revision/load mode/row counts/rejected count per `import_run`)
- [ ] Full PII detector coverage beyond v1 set
- [ ] Reversible tokenization with stored mappings for round-trip display
- [ ] Eval harness green every commit; nightly real-LLM run

---

## Cross-cutting invariants — never violated regardless of phase

- [ ] **IR is the only execution path.** No `eval`, no exec, no user-edited script ever runs server-side.
- [ ] **Agent never emits Python or SQL strings.** Only IR ops with the whitelisted DSL of §6.2.
- [ ] **`pipeline_revisions.ir_jsonb` is immutable per row.** Edits create new rows; only `state` mutates in place.
- [ ] **PII redaction is prompt-bound only.** The interpreter and Postgres load see raw values; placeholders never replace data on disk or in the database.
- [ ] **Managed schema only.** v1 never writes to or drops tables outside `structai_user`. No `DROP TABLE` in v1.
- [ ] **`import_run_id` allocated before staging.** Staging table names embed it. Retry policy keyed by `import_runs.status`.
- [ ] **Profile sent as structured JSON, not prose.** System prompt frames it as untrusted.
- [ ] **Tool args + IR terminator schema-validated.** Anything that doesn't match is rejected, agent retries.
- [ ] **Jobs always carry a lease.** Heartbeat refreshes it; reaper recycles expired ones.
- [ ] **`event_log` is monotonic per session.** SSE resumes via `Last-Event-ID`.
- [ ] **CHANGELOG.md updated in the same commit as the code change** (per `CLAUDE.md`).

---

## Maintenance

- Update this checklist in the same commit as the code change that ticks an item.
- When you finish a phase, mark its heading with a date tag (e.g. `## Phase 1 — … *(done 2026-06-01)*`).
- If you intentionally skip an item, mark it `[-]` with a one-line reason.
- If the plan changes, sync the checklist in the **same commit** as the `plans/plan.md` edit, and add a CHANGELOG bullet under `Changed`.
