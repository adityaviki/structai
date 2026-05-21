# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Phase 1 dependencies: `polars>=1.0` and `charset-normalizer>=3.0` in `packages/core` (profiler + sniffer), `python-multipart>=0.0.9` in `apps/api` (FastAPI multipart upload).
- `uv.lock` checked in to pin the resolved workspace dependency set across environments.
- `structai_core.io.sniff` — CSV/TSV sniffer: BOM detection, encoding via `charset-normalizer` (ASCII normalized to UTF-8 for downstream), delimiter via per-line vote across `,;\t|` cross-checked with `csv.Sniffer`, header heuristic via per-column numeric-vs-string comparison, CRLF / LF line terminator detection. `SniffError` on empty / undecodable input.
- 9 CSV/TSV fixtures under `tests/fixtures/csv/`: BOM, semicolon-delimited, mixed-types column, all-null column, single-row file, German decimals (`1.234,56`), leading-zero IDs, embedded newlines in quoted fields, ragged rows.
- `structai_core.io.readers` — `Reader` ABC + `CSVReader` / `TSVReader` over Polars `scan_csv`. `infer_schema_length=0` reads every column as Utf8 so leading zeros and European decimals survive into the profiler's type inference. Ragged rows raise `RaggedRowError` with the offending Polars message. `open_reader(path, sniff)` picks CSV vs TSV by delimiter.
- `structai_core.profile.models` — pydantic shape for the deterministic profile (plan §5). `InferredType`, `CardinalityClass`, `PiiClass` enums; `TopKEntry`, `LengthStats`, `Quantiles`, `ColumnProfile`, `OmittedColumn`, `FileProfile`, `ProfileResult`; `PROFILE_VERSION = "v1"`. Single source of truth for the redacted JSONB artifact, the raw-on-disk artifact, and the `GET /files/:id/profile` response.
- Initial implementation plan in `plans/plan.md` covering architecture, tech choices, phased build, and open questions.
- `.gitignore` for Python tooling and local agent state.
- This changelog.
- `CLAUDE.md` with project guidance, including how to maintain this changelog.
- `CHECKLIST.md` — phase-by-phase implementation checklist derived from `plans/plan.md`, plus a cross-cutting invariants section that mirrors the non-negotiables in `CLAUDE.md`.
- `CLAUDE.md` now lists `plans/plan.md` / `CHECKLIST.md` / `CHANGELOG.md` as the three source-of-truth documents, documents how to keep the checklist in sync (same commit as the code change), and pins the non-negotiable invariants (IR-only execution, no Python/SQL emission, immutable `ir_jsonb`, prompt-bound PII redaction, managed-schema-only writes, `import_run_id` allocated before staging, no run job before `approved_for_execution`).
- Phase 0 repo scaffold: root `pyproject.toml` (uv workspace with members `apps/api`, `apps/worker`, `packages/core`), `pnpm-workspace.yaml` (covers `apps/web`), `docker-compose.yml` (Postgres 16 only), `Makefile` (`make install / db-up / migrate / dev / lint / test / openapi-gen`), `.env.example` (DB URLs, `STRUCTAI_USER_SCHEMA`, `STRUCTAI_ALLOW_RAW_LLM_SAMPLES`, worker lease/heartbeat tunables), `.python-version` pinned to 3.12, root `package.json` (biome + concurrently + openapi-typescript), `biome.json`, and ruff config under `[tool.ruff]`. `/data/`, `node_modules/`, and `*.tsbuildinfo` added to `.gitignore`.
- Phase 0 app skeletons: `apps/api` (FastAPI with `/healthz` + empty routers for files/sessions/jobs/schemas/pipelines/runs/tables, `deps.get_settings`, SSE stub), `apps/worker` (boot loop with SIGINT/SIGTERM handling; full queue plumbing arrives in the next commit), `apps/web` (Vite + React 18 + TS rendering "ok"; `/api/*` proxied to `localhost:8000`), `packages/core` with `Settings` (pydantic-settings) and namespace packages `io`, `profile`, `agent`, `ir`, `schema`, `script`, `execute`, `store`, `eval` each carrying a docstring tying it to its plan section.
- Alembic configured with sync (psycopg) migration runner. Initial migration `20260520_0001` creates every table from plan §4 (`files`, `profiles`, `agent_sessions`, `pipeline_revisions`, `pipeline_artifacts`, `jobs`, `event_log`, `event_cursors`, `import_runs`, `import_run_tables`, `rejected_row_artifacts`, `pipeline_registry`) plus the managed `structai_user` schema. Vocabularies (states, kinds, load modes, error classes) enforced via CHECK constraints. SQLAlchemy 2.x typed models live in `packages/core/src/structai_core/db/models.py` with invariant notes attached to `pipeline_revisions`, `jobs`, `event_log`, and `import_runs`. `apps/api` now exposes `get_session` / `get_engine` / `get_sessionmaker` via `deps.py`.
- Postgres-backed job queue (no Redis): `packages/core/jobs/` exposes `enqueue` (with idempotency-key dedup via `ON CONFLICT DO NOTHING`), `claim_one` (`SELECT … FOR UPDATE SKIP LOCKED` + lease acquisition), `heartbeat` (refreshes `lease_expires_at`, surfaces `cancel_requested` and lease loss), `complete` / `fail` / `cancel`, and a `RetryableError` / `TerminalError` taxonomy plus a `CancellationToken` for cooperative cancellation at step boundaries (plan §8.4). `packages/core/jobs/reaper.py` recycles leased-but-expired rows (back to `queued` while attempts remain; `failed` once exhausted). `apps/worker` now runs the full poll → claim → heartbeat → dispatch → finalize → reap lifecycle and gates dispatch through a `TaskFn` registry (Phase 1+ register concrete tasks). Tunables: `STRUCTAI_WORKER_HEARTBEAT_SECS` / `_LEASE_SECS` / `_POLL_INTERVAL_SECS`.
- OpenAPI codegen wired end-to-end: `apps/api/src/structai_api/export_openapi.py` prints the FastAPI schema to stdout (no running server required), `make openapi-gen` pipes it through `openapi-typescript` into `apps/web/src/api/schema.ts`, and `apps/web/src/api/client.ts` exports an `openapi-fetch` instance typed against those `paths`. Initial scaffold covers `/healthz`; `apps/web/src/App.tsx` calls it to prove the round-trip works end-to-end.

### Changed
- Tests are now a first-class deliverable on `CHECKLIST.md`. Every phase (Phase 0 through Hardening) gained an explicit `### Tests` subsection; an implementation item cannot go to `[x]` until its tests pass, and a phase is not "done" until the whole Tests subsection is green. `CLAUDE.md` documents the test layout (`tests/<package>/` mirrors source, web tests under `apps/web/src/__tests__/`), the cadence (`make test-py` / `make test-ts` on every commit; `pytest -m eval` slower track), and the `structai_test` database convention. Phase 0 implementation already shipped, but its Tests subsection is `[ ]` and gates closing out the phase.
- `make test-py` now depends on `make db-up` so the test conftest can reach Postgres; `psycopg[binary]` added to the root dev group.

### Added
- Phase 0 test infrastructure: top-level `conftest.py` drops + recreates the `structai_test` database once per session, runs Alembic migrations to head, and exposes per-test `engine` / `sessionmaker` / `db_session` fixtures (TRUNCATE-between-tests rather than transaction-per-test so the queue's concurrent-claim test can use real transactions).
- `tests/test_config.py` — `Settings` env / `.env` precedence, defaults, required-field error, bool parsing for `STRUCTAI_ALLOW_RAW_LLM_SAMPLES`, user-schema and worker-tunable overrides.
- `tests/jobs/test_cancellation.py` — `CancellationToken` semantics (idempotent cancel, raise-on-cancel, repeated raising).
- Phase 0 tests (2/2): `tests/jobs/test_queue.py` covers enqueue dedup, `claim_one` + lease, concurrent claim under `FOR UPDATE SKIP LOCKED`, heartbeat ownership/cancel signalling, retryable/terminal fail policy, complete/cancel/request_cancel. `tests/jobs/test_reaper.py` covers expired-lease recycling and terminal-failure handoff. `tests/db/test_migrations.py` covers upgrade/downgrade round-trip, managed-schema creation, and CHECK-constraint vocabularies. `tests/db/test_models.py` covers `pipeline_revisions` state/created_by round-trips and the `files → profiles → agent_sessions → pipeline_revisions → pipeline_artifacts` cascade. `tests/worker/test_main_loop.py` covers the end-to-end enqueue→claim→dispatch→complete loop, retry-up-to-max, terminal-error stop, and cooperative cancel between heartbeat ticks — closing Phase 0.
- `plans/initial-idea` checked in as the pre-plan project sketch (historical context).

### Changed
- v1 load modes reduced from six to four (`append`, `replace`, `upsert`, `fail_if_duplicate`); `merge` and `version` deferred to v1.3 alongside reuse.
- `derive_column` DSL shrunk for v1 to column refs, literals, `concat`, `substr`, `upper`, `lower`, `coalesce`; arithmetic, comparisons, and `case when` deferred to v1.3.
- IR lifecycle clarified: `ir_jsonb` is immutable per row, only `state` mutates in place; a new revision row is created whenever IR content changes. Added a direct `proposed_ir → validated_ir` path so an agent-proposed IR doesn't have to pass through `user_edited_ir`.
- PII redaction scope made explicit as **prompt-bound only**: the IR interpreter still reads raw values and loads them to Postgres; placeholders only appear in LLM-bound surfaces. `name`/`address` detectors reclassified as best-effort (`name_like`, `address_like`).
- v1 scope tightened to the CSV/TSV single-table loop (profile → IR → review → dry-run → COPY → validate → browse). Excel becomes v1.1, multi-table normalization becomes v1.2, and pipeline reuse across files becomes v1.3. Phased build restructured around these milestones.
- PII handling flipped from "deferred" to **detect + redact by default** in v1: typed placeholders replace raw samples and top-K values on every LLM-bound surface; raw values stay in local profile artifacts. A `STRUCTAI_ALLOW_RAW_LLM_SAMPLES` dev flag opts back in.
- Reuse no longer promises "skip schema rediscovery." Pinning a prior pipeline runs a compatibility check (missing/new columns, format drift, type drift, PK drift, null-rate drift) and either reuses, adapts via the agent, or asks for review.
- Normalization (v1.2) defaults to single-table execution; each split is opt-in via the schema review screen with evidence cards.
- "Sandboxed execution" renamed to "constrained IR execution" for accuracy.
- `COPY` loader specified to run through **psycopg3** in the worker (the API keeps SQLAlchemy/asyncpg).
- Plan revised to a monorepo (`apps/api`, `apps/web`, `apps/worker`, `packages/core`) with a React + Vite + TypeScript frontend and a FastAPI backend; the web UI (file manager, chat sidebar, schema review, pipeline viewer, table browser) is now in scope from day one rather than deferred.
- Agent loop switched from a hand-rolled tool-use loop to LangChain + LangGraph (`langchain-anthropic`).
- Database target narrowed to PostgreSQL only (no SQLite path).
- Ingestion scope clarified: one file at a time, but the agent may decompose it into multiple normalized tables with foreign keys.
- Phased build restructured so each phase ships an end-to-end vertical slice (backend + matching UI) instead of leaving the UI for the final phase.
- Agent's executable output is now a typed **Transformation IR** (JSON), not Python. The generated `pipeline.py` becomes a viewable, non-executable artifact for transparency and as agent context on future runs.
- Execution moved into a separate **worker process** with a Postgres-backed job queue (`FOR UPDATE SKIP LOCKED`); FastAPI orchestrates only.
- Bulk loads switched to PostgreSQL `COPY FROM STDIN`; `to_sql` dropped as the default loader.
- Excel reading consolidated on `calamine` (covers `.xls` / `.xlsx` / `.xlsm` / `.xlsb` / `.ods`); `xlrd` dropped.
- Surrogate keys generated via Postgres identity columns and `ON CONFLICT` natural-key resolution instead of `df.index + 1`.

### Added
- **Target-table policy** (§8.2): managed `structai_user` schema, deterministic DDL from validated IR, existing-table conflict requires explicit `replace`, no `DROP TABLE` in v1, schema evolution deferred to v1.3.
- **Execution idempotency policy** (§8.4): `import_run_id` allocated before staging; staging table names embed `import_run_id`; retry behavior keyed by `import_runs.status` (committed → no-op, failed-before-commit → clean staging and retry, etc.); cancellation checkpoints between steps.
- **Wide-file profile truncation policy** (§5): always include file-level stats and a compact per-column index; rich stats only for the top-N highest-uncertainty columns; omitted columns listed by name so the agent can drill in via tools.
- **Destructive-action warnings** in the schema review screen for `replace`, existing-target overwrite, nullable→non-nullable edits with rejected rows, type narrowing, column drops, PII columns being loaded raw, and any dry-run rejections.
- **Date/time formatting policy** in the pre-COPY contract: per Postgres type (`date` no offset; `timestamp` keeps naive; `timestamptz` requires explicit timezone in the IR). Prevents the system from inventing timezones on naive sources.
- **Extra eval cases**: DDL snapshot tests, identifier sanitization & collision tests, Postgres reserved-word tests, per-mode load-mode SQL tests, transaction rollback tests, retry/idempotency tests, pre-COPY contract tests.
- **Data model** section in the plan with concrete Postgres tables: `files`, `profiles`, `agent_sessions`, `pipeline_revisions` (immutable, append-only), `pipeline_artifacts`, `jobs` (with leases, heartbeat, idempotency key, retryable/terminal error class, cancellation), `event_log`, `event_cursors`, `import_runs`, `import_run_tables`, `rejected_row_artifacts`, `pipeline_registry`.
- **Per-op semantics table** for the IR: input/output columns, null behavior, error behavior, row-count effects, rejected-row eligibility, reversibility, and a whitelisted expression DSL for `derive_column` (no Python snippets).
- **IR lifecycle state machine** (`proposed_ir → user_edited_ir → validated_ir → dry_run_passed → approved_for_execution → executed`) with post-edit IR validation as a hard gate.
- **Pre-COPY contract** spec: column-order check, non-null guarantee, escaping rules, deterministic date/numeric formatting, rejected-rows separation, staging-schema match — all enforced before `COPY` runs.
- `ir_version` tag in every IR document; both `source_sha256` and `profile_sha256` stored on profiles.
- Column-name sanitization rules (NFKC normalize, replace, collapse, lowercase, leading-digit handling, Postgres reserved-word rewriting) with the raw→safe mapping persisted on the profile.
- Raw-source archive retention policy (`retention_until` on `files`, default 30 days locally, explicit purge endpoint).
- PII detector set (`email`, `phone`, `address`, `name`, `ip`, `national_id`, `cc_like`) with `pii_class` recorded per column.
- Six explicit load modes per table (`append`, `replace`, `upsert`, `merge`, `fail_if_duplicate`, `version`) with an `import_runs` audit table.
- Expanded deterministic profiler: top-K values, string-length percentiles, leading-zero detection, decimal/thousands separator detection, currency/percent/unit hints, timezone hints, outlier examples, PK/FK scoring, full-data uniqueness, empty-string-vs-null distinction.
- **Schema review screen** as a mandatory human-in-the-loop step before any run, with per-decision evidence and accept/reject controls for normalization splits.
- Prompt-injection defenses (structured JSON framing, untrusted-data system prompt, schema-validated terminator, no code emission) plus a fixture-based prompt-injection test suite.
- Evaluation harness (`packages/core/eval/`): golden IR tests, profiler regression tests, normalization false-positive cases, Excel chaos fixtures, generated-script snapshots, per-fixture cost tracking.
- Security & privacy section in the plan covering in-scope items (single-user local default, file size limits, upload quarantine, audit log, sandboxed-by-design execution) and explicitly deferred items (PII redaction, auth/workspaces, macro/virus scanning, data deletion/export).
- Persisted SSE event log so reconnecting clients can replay agent events.
- Haiku-first LLM routing with per-session cost tracking; escalate to Opus only on low-confidence decisions.

[Unreleased]: https://github.com/adityaviki/structai/commits/main
