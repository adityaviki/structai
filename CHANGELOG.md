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

### Changed
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
- Six explicit load modes per table (`append`, `replace`, `upsert`, `merge`, `fail_if_duplicate`, `version`) with an `import_runs` audit table.
- Expanded deterministic profiler: top-K values, string-length percentiles, leading-zero detection, decimal/thousands separator detection, currency/percent/unit hints, timezone hints, outlier examples, PK/FK scoring, full-data uniqueness, empty-string-vs-null distinction.
- **Schema review screen** as a mandatory human-in-the-loop step before any run, with per-decision evidence and accept/reject controls for normalization splits.
- Prompt-injection defenses (structured JSON framing, untrusted-data system prompt, schema-validated terminator, no code emission) plus a fixture-based prompt-injection test suite.
- Evaluation harness (`packages/core/eval/`): golden IR tests, profiler regression tests, normalization false-positive cases, Excel chaos fixtures, generated-script snapshots, per-fixture cost tracking.
- Security & privacy section in the plan covering in-scope items (single-user local default, file size limits, upload quarantine, audit log, sandboxed-by-design execution) and explicitly deferred items (PII redaction, auth/workspaces, macro/virus scanning, data deletion/export).
- Persisted SSE event log so reconnecting clients can replay agent events.
- Haiku-first LLM routing with per-session cost tracking; escalate to Opus only on low-confidence decisions.

[Unreleased]: https://github.com/adityaviki/structai/commits/main
