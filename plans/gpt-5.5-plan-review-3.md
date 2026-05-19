This version is  **substantially stronger** . The plan now has a sane MVP boundary, default PII redaction, immutable pipeline revisions, a concrete data model, job leases/heartbeats, a constrained IR lifecycle, a pre-`COPY` contract, and clear follow-on milestones for Excel, normalization, and reuse. That fixes almost all of the earlier architectural risks.

My review now is mostly about  **tightening the v1 implementation contract** .

## Verdict

I’d call this **architecturally credible** and much closer to buildable.

The best changes are:

* v1 is now CSV/TSV + single-table only.
* Excel, normalization, and reuse are correctly deferred.
* PII redaction is now default.
* Python export is clearly non-executable.
* IR revisions are immutable.
* Job leases, heartbeat, stale-job reaper, retries, cancellation, and idempotency are included.
* Schema review and IR validation are now lifecycle gates.
* `COPY FROM STDIN` has a pre-load validation contract.

The plan no longer feels like “cool demo that could become unsafe in production.” It feels like a real ingestion product design.

## Remaining issues to fix

### 1. The IR lifecycle has one missing transition

You list:

```text
proposed_ir
→ user_edited_ir
→ validated_ir
→ dry_run_passed
→ approved_for_execution
→ executed
```

But a user may approve an agent-generated IR without editing it. That means `proposed_ir` also needs to validate directly:

```text
proposed_ir
  ├─→ validated_ir
  └─→ user_edited_ir → validated_ir
```

Also, approval should probably produce a new immutable revision state rather than mutating the same row, unless `state` is allowed to change in place. You say `pipeline_revisions` is append-only, but the lifecycle implies state mutation. Pick one:

Option A: revision rows are immutable except `state`.

Option B: every state transition creates a new `pipeline_revisions` row.

I’d choose A for simplicity, but clarify it.

### 2. “All six load modes” is still too much for v1

For v1, I would only ship:

* `append`
* `replace`
* `fail_if_duplicate`
* maybe `upsert`

Defer these:

* `merge`
* `version`

`merge` semantics get subtle quickly: which columns update, what counts as a natural key, how nulls behave, how conflicts are reported. `version` also implies more table-design policy than a simple import tool needs at first.

Suggested v1 load modes:

```text
append
replace
upsert
fail_if_duplicate
```

Then add `merge` and `version` in v1.3 with reuse.

### 3. Target table creation needs its own section

The plan talks about schemas, staging tables, and `COPY`, but the target table lifecycle is under-specified.

You need to define:

* When does the target table get created?
* Does StructAI own the table DDL?
* What happens if the table already exists?
* What if the reviewed IR changes a column type?
* Are destructive DDL changes allowed?
* Are indexes and constraints created before or after load?
* How are Postgres reserved words and quoted identifiers handled at DDL time?

Add a section like:

```text
Target table policy:
- v1 creates tables only in a managed schema, e.g. structai_user.
- Existing table conflict requires user confirmation.
- v1 never drops user tables except in replace mode on managed tables.
- DDL is generated from validated IR.
- Constraints are applied after staging validation but before final commit.
```

### 4. PII redaction needs clearer semantics

This part is much improved, but clarify one thing:

The LLM sees placeholders, but the actual transform pipeline runs on raw local data.

That should be explicit:

```text
Redaction is prompt-bound only. The profile sent to the LLM contains placeholders. The local interpreter still reads the original file and applies approved transforms to raw values. Placeholder tokens never replace source data on disk or in Postgres.
```

Also, be careful with “name” and “address” detection in v1. Email/phone/IP/credit-card-like are feasible. Names and addresses are much noisier. I’d phrase it as:

```text
Best-effort detectors: name_like, address_like
```

rather than implying reliable coverage.

### 5. Date/time handling needs refinement

The pre-`COPY` contract says dates/timestamps are formatted as ISO-8601 with explicit timezone.

For PostgreSQL, distinguish:

* `date`
* `timestamp without time zone`
* `timestamp with time zone`

A plain `date` should not have a timezone. A source timestamp may be timezone-naive. You need a policy:

```text
date → YYYY-MM-DD
timestamp without time zone → ISO local timestamp, no offset
timestamp with time zone → ISO timestamp with offset
timezone-naive source → keep naive unless user/IR specifies timezone
```

Otherwise the system may accidentally invent timezones.

### 6. Job idempotency needs special handling for execution

You mention idempotency keys, which is good. But `execute_pipeline` needs extra care.

If a worker dies after `COPY` but before marking the job finished, retry behavior must be safe.

Recommended rule:

```text
Every execution has an import_run_id before any staging table is created.
Staging table names include import_run_id.
Final commit is transactional.
Retry checks import_runs status:
- committed → no-op / return existing result
- failed before commit → clean staging and retry
- running with expired lease → recover or mark failed
```

This should be part of Phase 4.

### 7. The expression DSL should probably be smaller in v1

Your `derive_column` DSL includes `case when`, comparisons, string funcs, arithmetic, etc. That is useful, but it increases implementation and test burden.

For v1, consider excluding `derive_column` entirely or making it very small:

```text
concat
substr
upper
lower
coalesce
literal
column reference
```

Add arithmetic and `case when` later. Most CSV imports do not need complex derivations on day one.

### 8. The profiler’s 30 KB target may conflict with wide files

You mention 500+ columns and column-group summaries, but for v1 it would help to add a deterministic truncation policy:

```text
If profile exceeds budget:
1. Always include file-level stats.
2. Always include all column names, safe names, inferred types, null rates, distinct counts.
3. Include rich stats only for top N columns by uncertainty/risk.
4. Agent can drill into omitted columns via tools.
```

Without this, profile budgeting becomes ad hoc.

### 9. The schema review UI should expose destructive warnings

For load modes like `replace`, the UI should show a scary but clear warning:

```text
This will truncate target table sales_q3 before loading new rows.
```

Also add warnings for:

* rows rejected in dry run
* nullable → non-nullable edits
* type narrowing
* destructive column drops
* replacing an existing table
* high PII columns being loaded

### 10. The eval harness is good, but add migration/DDL tests

You already have golden IR, profiler, prompt injection, PII, validation, script snapshot, and cost tests. Add:

* DDL generation snapshot tests
* identifier sanitization collision tests
* reserved-word tests
* load-mode SQL tests
* transaction rollback tests
* retry/idempotency tests
* pre-`COPY` contract tests

These are likely to catch more real bugs than the LLM tests.

## Small corrections

I’d change “macros are not executed; macro presence is flagged” to “macro streams are ignored if present.” That is more precise.

I’d also rename `pipeline_artifacts.kind = pipeline_py / manifest_json / dry_run_report` to include `ir_json` or make clear that the canonical IR lives only in `pipeline_revisions.ir_jsonb`.

For `event_cursors`, decide whether you need server-side cursors at all. Many SSE clients can resume with `Last-Event-ID`; storing per-client cursors may be unnecessary for v1 unless you have multi-device resume requirements.

## Final recommendation

This is now good enough to start building.

The only changes I’d make before implementation are:

1. Clarify whether pipeline revision `state` mutates or every state change creates a new row.
2. Add a target-table DDL/table-ownership policy.
3. Reduce v1 load modes to 3–4 modes.
4. Tighten date/time semantics.
5. Make execution idempotency explicit around `import_run_id`.
6. Shrink or defer `derive_column`.
7. Add DDL/load-mode/idempotency tests to the eval harness.

After those edits, the plan is not just conceptually solid; it is implementable in a disciplined way.
