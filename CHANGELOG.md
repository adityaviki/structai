# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial implementation plan in `plans/plan.md` covering architecture, tech choices, phased build, and open questions.
- `.gitignore` for Python tooling and local agent state.
- This changelog.
- `CLAUDE.md` with project guidance, including how to maintain this changelog.
- `CHECKLIST.md` — phase-by-phase implementation checklist derived from `plans/plan.md`, plus a cross-cutting invariants section that mirrors the non-negotiables in `CLAUDE.md`.
- `CLAUDE.md` now lists `plans/plan.md` / `CHECKLIST.md` / `CHANGELOG.md` as the three source-of-truth documents, documents how to keep the checklist in sync (same commit as the code change), and pins the non-negotiable invariants (IR-only execution, no Python/SQL emission, immutable `ir_jsonb`, prompt-bound PII redaction, managed-schema-only writes, `import_run_id` allocated before staging, no run job before `approved_for_execution`).
- Phase 0 repo scaffold: root `pyproject.toml` (uv workspace with members `apps/api`, `apps/worker`, `packages/core`), `pnpm-workspace.yaml` (covers `apps/web`), `docker-compose.yml` (Postgres 16 only), `Makefile` (`make install / db-up / migrate / dev / lint / test / openapi-gen`), `.env.example` (DB URLs, `STRUCTAI_USER_SCHEMA`, `STRUCTAI_ALLOW_RAW_LLM_SAMPLES`, worker lease/heartbeat tunables), `.python-version` pinned to 3.12, root `package.json` (biome + concurrently + openapi-typescript), `biome.json`, and ruff config under `[tool.ruff]`. `/data/`, `node_modules/`, and `*.tsbuildinfo` added to `.gitignore`.

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
