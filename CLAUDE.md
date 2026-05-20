# Project guidance

## Source-of-truth documents

- `plans/plan.md` — the implementation plan. Architecture, tech choices, data model, IR semantics, phased build, security posture. Section references like `§6.4` in code, commits, or this file always point at the plan.
- `CHECKLIST.md` — phase-by-phase implementation checklist derived from the plan. Tracks progress with `[ ]` / `[~]` / `[x]` / `[-]`. Tick items in the **same commit** as the code change that lands them.
- `CHANGELOG.md` — user-facing changes, Keep-a-Changelog format.

When the plan and the checklist disagree, the plan wins; reconcile the checklist in the same commit that resolves the discrepancy.

## Maintaining the checklist

Whenever you finish work that maps to a `CHECKLIST.md` item:

- Flip the box from `[ ]` to `[x]` (or `[~]` if mid-flight) in the **same commit** as the code change.
- If you intentionally skip an item, mark it `[-]` with a one-line reason after the bullet.
- When you finish a whole phase, add a `*(done YYYY-MM-DD)*` tag to its heading.
- If a code change requires a new checklist item that the plan doesn't yet cover, update `plans/plan.md` first (with a CHANGELOG `Changed` bullet), then add the checklist item — never invent checklist items that aren't traceable to the plan.

## Maintaining the changelog

This repo uses [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) (see `CHANGELOG.md`) with [Semantic Versioning](https://semver.org/).

When you make a notable change:

- Add a bullet under `## [Unreleased]` in `CHANGELOG.md` **in the same commit as the code change** — not as a follow-up.
- Pick the right section: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, or `Security`. Create the heading if it doesn't exist yet under `[Unreleased]`.
- Keep entries short and user-facing — describe the impact, not the implementation.
- When cutting a release: rename `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD`, add a fresh empty `[Unreleased]` on top, and add a comparison link at the bottom of the file.

What counts as "notable": user-visible behavior changes, new features, dependency changes, breaking API changes, schema migrations, plan/architecture revisions in `plans/`. Pure refactors and internal-only changes can be skipped.

## Non-negotiable invariants

These hold regardless of which phase you're in (drawn from `plans/plan.md` §6, §7, §8, §14):

- **The IR is the only execution path.** No `eval`, no `exec`, no user-edited script is ever run server-side. The generated `pipeline.py` is a viewable artifact.
- **The agent never emits Python or SQL strings.** Only IR ops with the whitelisted DSL of §6.2.
- **`pipeline_revisions.ir_jsonb` is immutable per row.** User edits and agent re-emissions create new rows with `parent_id`; only `state` mutates in place.
- **PII redaction is prompt-bound only.** The interpreter and Postgres load see raw values; placeholders only appear in LLM-bound surfaces.
- **Managed schema only.** v1 writes only to `structai_user`. No `DROP TABLE` in v1.
- **`import_run_id` is allocated before any staging table.** Retry policy is keyed by `import_runs.status` (§8.4).
- **No `import_runs` job may be enqueued from a revision earlier than `approved_for_execution`** — enforce server-side.

A code change that would violate one of these is a plan revision, not a coding decision — update `plans/plan.md` first.
