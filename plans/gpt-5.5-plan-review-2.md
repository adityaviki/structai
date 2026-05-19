This update is  **much stronger** . You fixed the biggest structural problems: the executable artifact is now a typed IR instead of Python, FastAPI is orchestration-only, heavy work moved to a worker, SSE is backed by an event log, `COPY FROM STDIN` replaced `to_sql`, schema review is explicit, and prompt-injection defenses are now first-class. Those are all major improvements.

The remaining issues are now mostly  **scope, edge-case semantics, and production hardening** .

## Biggest remaining issue: v1 is still too ambitious

Your v1 definition still includes XLSX upload, agent inference, normalization, IR generation, schema review, execution, validation, rejected rows, table browser, pipeline viewer, and reuse for next-quarter files. That is a lot for a first shippable version.

I would redefine v1 as:

> CSV/TSV only, single-table only, no normalization, IR-based transforms, schema review, dry-run, `COPY` load to Postgres, validation report, generated Python preview.

Then make **Excel + normalization + reuse** v1.1/v1.2. Your current plan is closer to a strong v2.

## PII is still the biggest product risk

You explicitly defer PII redaction while still sending raw emails, phones, and addresses to the model in v1. You document it clearly and constrain v1 to single-user/local-only, which is honest, but I would still avoid making raw PII the default.

Better middle ground:

```text
v1 default:
- detect PII
- replace samples with typed placeholders before LLM calls
- keep raw values only in local profiling artifacts
- add a dev flag: STRUCTAI_ALLOW_RAW_LLM_SAMPLES=true
```

Example:

```json
{
  "name": "email",
  "pattern_hits": ["email"],
  "sample_values": ["<EMAIL_1>", "<EMAIL_2>", "<EMAIL_3>"],
  "semantic_hint": "looks like email address"
}
```

That keeps the local-only MVP usable without normalizing a risky habit into the architecture.

## The Postgres-backed job queue needs more detail

`SELECT ... FOR UPDATE SKIP LOCKED` is a fine v1 choice, but add the missing operational pieces:

* `locked_at`
* `locked_by`
* `lease_expires_at`
* heartbeat updates
* max attempts
* retryable vs terminal errors
* cancellation state
* stale-job reaper
* idempotency key per job
* event-log cursor per session

Without leases, a crashed worker can strand jobs forever. Without idempotency, retries can duplicate imports.

## The IR needs stronger semantics

The IR shape is good, but several ops are underspecified. The risky ones are:

* `derive_column`
* `reject_row`
* `map_enum`
* `split_table`
* `set_foreign_key`
* `merge`

For each op, define:

```text
input columns
output columns
allowed expression language, if any
null behavior
error behavior
whether it can change row count
whether it can create rejected rows
whether it is reversible/auditable
```

Especially avoid letting `derive_column` become a backdoor for arbitrary expressions. Use a tiny expression DSL, not Python snippets.

## Schema-review edits need their own validation flow

You say user edits write a new IR revision and the agent is not re-invoked unless requested. Good. But after any manual edit, the system should immediately re-run IR validation:

* all referenced source columns exist
* op ordering is valid
* target columns are produced before use
* FK references point to real tables/columns
* load mode has required keys
* type changes are compatible with existing ops
* rejected-row rules still make sense

I would add an explicit state machine:

```text
proposed_ir
→ user_edited_ir
→ validated_ir
→ dry_run_passed
→ approved_for_execution
→ executed
```

No run should start from merely “edited” IR.

## Excel handling may still be too early

The Excel fixture list is excellent, but it also reveals why Excel should probably not be in the first end-to-end version. You include hidden sheets, merged cells, `.xlsm`, `.xlsb`, formula-only cells, and 1904 dates.

Two specific changes:

1. Treat `.xlsm` as data-only and explicitly ignore macros.
2. Add a “sheet/header confirmation” UI step before profiling complex workbooks.

For v1, I’d support CSV/TSV first, then add Excel once the IR/execution pipeline is stable.

## `COPY` loading needs a pre-COPY contract

Since `COPY` can fail the whole load on malformed rows, define the exact boundary:

```text
Polars transform → validated typed frame → serialized temp CSV/Arrow → COPY
```

Before `COPY`, guarantee:

* correct column order
* no unexpected nulls for non-null columns
* strings escaped safely
* dates formatted deterministically
* rejected rows already separated
* staging schema exactly matches serialized data

Otherwise failures will appear late and be harder to explain.

## Normalization should be conservative by default

You now have evidence cards and split rejection, which is great. But I would add a hard policy:

```text
Default mode: propose normalization, do not auto-enable it.
Execution default: single-table unless user accepts specific splits.
```

This prevents the first successful run from surprising users with five tables when they expected one.

## Reuse should not promise “no schema rediscovery”

The v1 definition says next quarter’s file can pin a prior pipeline and avoid schema rediscovery. I’d soften that. Even with a prior IR, the system still needs compatibility checks:

* missing columns
* new columns
* changed date formats
* changed enum values
* type drift
* primary-key drift
* null-rate drift

Better wording:

> The registry surfaces the prior pipeline; StructAI runs a compatibility check and either reuses it directly, adapts it with the agent, or asks for review.

## Add a data-model section

The plan would benefit from concrete tables. Add something like:

```sql
files
profiles
jobs
event_log
agent_sessions
pipeline_revisions
pipeline_artifacts
import_runs
import_run_tables
rejected_row_artifacts
```

Especially important: `pipeline_revisions`. You will want immutable revisions, not in-place mutation.

## Minor wording/implementation fixes

* “Sandboxed execution by design” is slightly misleading. It is not sandboxing; it is constrained interpretation. I’d say **“constrained execution by design.”**
* If the worker is doing heavy Postgres `COPY`, consider using `psycopg3` in the worker even if the API uses SQLAlchemy/asyncpg.
* Store both `source_sha256` and `profile_sha256`.
* Include schema/IR versioning from day one: `ir_version: "2026-05-structai-v1"`.
* Add explicit column-name sanitization rules and collision handling.
* Add reserved-word handling for Postgres identifiers.
* Add a “raw source archive retention policy,” even for local-only.

## My suggested final edits

1. Move PII redaction from “deferred” to “minimal default redaction in v1.”
2. Shrink v1 to CSV/TSV + single-table + IR + dry-run + load.
3. Make Excel and normalization separate milestones.
4. Add job lease/heartbeat/retry semantics.
5. Add `pipeline_revisions` and immutable IR revisions.
6. Define op semantics for every IR operation.
7. Add post-edit IR validation before dry-run.
8. Make normalization opt-in per split.
9. Add compatibility checks before reusing prior pipelines.
10. Rename “sandboxed execution” to “constrained IR execution.”

Overall: this is now a credible architecture. The main thing I’d change is not the direction, but the  **MVP boundary** . The plan is safest if you first prove the IR → review → dry-run → COPY → validate loop on simple files, then add the agentic/normalization/Excel complexity on top.
