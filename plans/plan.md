# StructAI — Implementation Plan

## 1. Problem framing

Build an agent that takes an arbitrary tabular file (CSV/TSV/XLSX/XLS), figures out what's in it, infers a target schema, and produces a reusable import script that loads the data into a database. Combine **deterministic profiling** (cheap, exact, reproducible) with **LLM reasoning** (used only where judgment is needed: semantics, naming, relationships, ambiguity resolution).

The core principle: the LLM never touches raw data row-by-row. It receives compact, deterministic *summaries* and emits *decisions* (column meanings, type choices, transformations). Scripts are the artifact — code the user can read, version, edit, and rerun without the agent.


## 2. Tech choices

| Concern           | Choice                                                                                  | Why                                                                           |
| ----------------- | --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Language          | Python 3.12                                                                             | Ecosystem (pandas, polars, openpyxl, SQLAlchemy) is unmatched for this domain |
| Package/env       | `uv` + `pyproject.toml`                                                             | Fast, modern, lockfile-based                                                  |
| Data engine       | **Polars** for profiling, **pandas** for compatibility in generated scripts | Polars is fast and lazy; pandas is what users expect to edit                  |
| Excel             | `openpyxl` (xlsx), `xlrd==1.2.0` (xls), `calamine` (fast fallback)                | Covers full xls/xlsx range                                                    |
| DB layer          | SQLAlchemy 2.x + DB-API drivers                                                         | Lets the same generated script target Postgres, SQLite, MySQL, DuckDB         |
| Initial DB target | **Postgres**                                                                      | Postgres for the realistic case                                               |
| LLM               | Anthropic SDK,`claude-opus-4-7` for inference, `claude-haiku-4-5` for cheap routing | Tool-use API is a natural fit for the deterministic-tools + reasoning split   |
| Agent loop        | Hand-rolled tool-use loop (not LangChain)                                               | Predictable, debuggable; this domain doesn't need an agent framework          |
| CLI               | `typer`                                                                               | Subcommands, type-driven                                                      |
| Tests             | `pytest` + small fixture files                                                        | Real CSV/XLSX samples in `tests/fixtures/`                                  |
| Lint/format       | `ruff`                                                                                | One tool, fast                                                                |

Web UI is deferred — CLI-first.

## 3. Architecture

```
                      ┌────────────────────────┐
   input file ───────▶│  Ingestion Pipeline    │
                      └──────────┬─────────────┘
                                 │
        ┌────────────────────────┴──────────────────────┐
        ▼                                                ▼
┌────────────────┐                              ┌──────────────────┐
│ Deterministic  │   profile JSON               │   Agent loop      │
│   analyzers    │──────────────────────────────▶  (Claude + tools) │
│ (sniff, type   │                              │                   │
│  infer, stats) │◀─────── tool calls ──────────│                   │
└────────────────┘                              └─────────┬─────────┘
                                                          │ decisions
                                                          ▼
                                                ┌──────────────────┐
                                                │ Script generator │
                                                │  (Jinja2 → .py)  │
                                                └─────────┬────────┘
                                                          ▼
                                                ┌──────────────────┐
                                                │  Executor +      │
                                                │  validator       │
                                                └─────────┬────────┘
                                                          ▼
                                                ┌──────────────────┐
                                                │ Script store +   │
                                                │ run history      │
                                                └──────────────────┘
```

### Module layout

```
structai/
├── pyproject.toml
├── src/structai/
│   ├── __init__.py
│   ├── cli.py                 # typer entry point
│   ├── pipeline.py            # orchestrates a single ingestion run
│   ├── io/
│   │   ├── sniff.py           # encoding, delimiter, header, sheet detection
│   │   └── readers.py         # uniform Reader interface over csv/tsv/xls/xlsx
│   ├── profile/
│   │   ├── columns.py         # per-column stats, null rate, cardinality
│   │   ├── types.py           # type inference (int/float/date/bool/enum/text)
│   │   ├── patterns.py        # regex-based format detection (email, phone, ISO date, currency)
│   │   └── relations.py       # multi-file: FK candidate detection
│   ├── agent/
│   │   ├── loop.py            # tool-use loop
│   │   ├── tools.py           # tools exposed to the LLM
│   │   ├── prompts.py         # system + task prompts
│   │   └── decisions.py       # typed decision schema (pydantic)
│   ├── schema/
│   │   ├── model.py           # internal IR: Table, Column, Constraint
│   │   └── ddl.py             # IR → CREATE TABLE for each dialect
│   ├── script/
│   │   ├── templates/         # Jinja2 templates for generated scripts
│   │   └── generator.py       # decisions + IR → standalone .py
│   ├── execute/
│   │   ├── runner.py          # dry-run + real run of generated script
│   │   └── validate.py        # post-load row count, type, anomaly checks
│   └── store/
│       ├── registry.py        # save/load scripts + run history
│       └── fingerprint.py     # file→script matching (column-set hash)
└── tests/
    ├── fixtures/              # sample files
    └── ...
```

## 4. The deterministic profile

Before any LLM call, produce a compact JSON profile per file. Keep it small enough to fit in one prompt comfortably (target <30 KB).

For each column, capture:

- `name` (raw), `position`
- `inferred_type` (one of: `int`, `float`, `bool`, `date`, `datetime`, `string`, `enum`, `json`)
- `null_count`, `null_rate`
- `distinct_count`, `cardinality_class` (`unique` / `low` / `high`)
- `min`, `max` (for ordered types)
- 5 `sample_values` (drawn to maximize diversity, not just head)
- `pattern_hits`: list like `["iso_date", "email"]` from regex matchers
- `format_examples`: a couple of literal samples for any detected format

File-level: row count, encoding, delimiter, has_header, sheet name (xlsx), file hash.

This profile is the contract between deterministic land and the LLM.

## 5. The agent loop

A single tool-use loop with Claude. Tools the agent can call:

| Tool                                        | Purpose                                                             |
| ------------------------------------------- | ------------------------------------------------------------------- |
| `get_column_samples(column, n, strategy)` | More samples (`random`, `nulls`, `extremes`, `regex_match`) |
| `count_values(column, where=None)`        | Cardinality, top-K values                                           |
| `match_regex(column, pattern)`            | Test a hypothesis ("are these all phone numbers?")                  |
| `cross_tab(col_a, col_b)`                 | Check FK candidacy or functional dependency                         |
| `parse_as(column, target_type)`           | Try parsing and report failure rate                                 |
| `propose_schema(tables)`                  | Submit the final decision (terminates the loop)                     |

The LLM's job: starting from the profile, ask targeted questions via tools until it can commit to a `propose_schema` call. The schema submission is a strongly-typed pydantic object (column name, target SQL type, nullable, PK/unique, transformation rule, semantic label, comment). No free-form output goes downstream.

**Why tools, not a big prompt:** type inference is cheap, the agent only needs *judgment* — which column is the natural key, which two text columns are really the same enum, whether `2024-03` means a month or an ID. Tools let the model verify its hypotheses against the actual data without us pre-computing everything.

## 6. Script generation

Generated scripts are **standalone, runnable Python files** — not opaque agent artifacts. A user should be able to open one, read it top to bottom, edit a transformation, and rerun it without the agent.

Template structure (Jinja2):

```python
"""
Generated by structai for: customers_2024.csv
Source SHA256: ...
Target: postgresql://.../customers
"""
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime

SOURCE = "customers_2024.csv"
TABLE  = "customers"

def transform(df):
    df = df.rename(columns={...})
    df["signup_date"] = pd.to_datetime(df["signup_date"], format="%Y-%m-%d", errors="coerce")
    df["country"] = df["country"].str.upper().str.strip()
    # ... agent-generated transforms, each one obvious
    return df

def main(engine_url):
    df = pd.read_csv(SOURCE, encoding="utf-8")
    df = transform(df)
    engine = create_engine(engine_url)
    df.to_sql(TABLE, engine, if_exists="append", index=False, chunksize=10_000)

if __name__ == "__main__":
    import sys
    main(sys.argv[1])
```

Plus a sibling `.sql` file with `CREATE TABLE` and indexes. Both go in `scripts/<dataset>/<timestamp>/`.

## 7. Execution & validation

- **Dry-run mode**: run `transform()` only; report row count, dropped rows, coerce failures per column.
- **Staging**: load to a `_stage_<table>` table first, validate, then `INSERT ... SELECT` into the real table. (Postgres only initially.)
- **Validation checks**:
  - row count delta vs. source
  - null rates within tolerance of profile
  - PK uniqueness
  - sample round-trip (read back N rows, compare)
- On failure, surface a diff to the user and to the agent for a revision pass.

## 8. Reuse & iteration

- Each script is stored under `~/.structai/scripts/` with metadata: file fingerprint (column-name set + types + sample-hash), DB target, success status, run log.
- On a new file, the registry checks for a matching fingerprint. If found, the agent is shown the existing script as a starting point: "this file looks like the one you imported on 2024-09-12 — adapt or regenerate?"
- User feedback (free text + edits to the generated script) feeds the next agent call as context, so the script converges across runs.

## 9. Phased build

I'd cut this into 6 phases, each independently demoable.

### Phase 0 — Scaffold (½ day)

- `uv init`, pyproject, ruff, pytest, basic CLI shell
- `structai analyze <file>` → prints "hello" with file path resolved

### Phase 1 — Deterministic profiler (2–3 days)

- File sniffing: encoding (`charset-normalizer`), delimiter, header, xlsx sheet pick
- Unified `Reader` over CSV/TSV/XLS/XLSX
- Column profiling: types, nulls, cardinality, samples, regex pattern bank (~15 common patterns)
- `structai profile <file>` → emits JSON profile to stdout
- Tests against fixture files covering edge cases: BOM, semicolon delim, mixed-type column, all-null column, single-row file, German decimals, dates as Excel serials

### Phase 2 — Agent loop (2–3 days)

- Anthropic SDK tool-use loop with the tools listed in §5
- Pydantic `SchemaDecision` model as the loop's terminating output
- Prompts in `prompts.py`, versioned
- `structai infer <file>` → runs profiler + agent, prints decision JSON
- Mock-LLM mode for tests (canned tool-call sequences) so the suite runs offline

### Phase 3 — Schema + script generation (2 days)

- IR: `Table`/`Column`/`Constraint`
- DDL emitter for SQLite + Postgres
- Jinja2 templates for the import script
- `structai generate <file>` → writes `scripts/<dataset>/<ts>/{import.py,schema.sql,manifest.json}`

### Phase 4 — Execute + validate (2 days)

- Runner with `--dry-run` and `--target sqlite:///foo.db`
- Staging-table flow for Postgres
- Post-load validators
- `structai run <script-dir> --target <url>`

### Phase 5 — Reuse + feedback (2 days)

- Script registry under `~/.structai/`
- Fingerprint matching
- Feedback intake (`structai run ... --feedback "country should be ISO-2"`) → re-invokes the agent with prior script + feedback as context, emits a new revision

### Phase 6 — Optional web UI (later)

- Streamlit or a thin FastAPI + minimal SPA. Not in initial scope.

## 10. Open questions for you

Before I start, I'd want to nail down:

1. **Single-table or multi-file imports in v1?** Multi-file (with FK detection) is meaningfully harder — I'd default to single-table for Phase 1–4 and add multi-file in Phase 5.
2. **Target database for v1** — SQLite for everyone, Postgres for everyone, or both from day one? Both is cheap if we go through SQLAlchemy from the start (recommended).
3. **Where does the user provide the desired schema, if at all?** Three modes: (a) fully inferred, (b) target schema provided and agent maps to it, (c) hybrid. I'd build (a) first, (b) is a small extension.
4. **PII handling** — should the profiler avoid sending sample values that look like emails/phones/SSNs to the LLM? Worth a flag on day one.

## 11. Risks & how I'd manage them

- **LLM hallucinates a transformation that silently corrupts data.** Mitigations: dry-run with per-row coercion-failure counts; staging tables; round-trip sampling; the generated script is human-readable so review is realistic.
- **Excel is a swamp** (merged cells, multi-row headers, formulas, dates-as-numbers). Mitigation: detect these in the sniffer and either normalize or hard-fail with a clear message rather than silently mis-parsing.
- **Profile bloat** for wide files (500+ columns). Mitigation: token-budget the profile; for very wide files, the agent gets a column-group summary first and can drill in via tools.
- **Cost.** A single ingestion shouldn't cost more than a few cents. Route the easy decisions through Haiku and only escalate to Opus when the profile is ambiguous (low confidence in deterministic type inference, or many free-text columns).

## 12. Definition of done for v1

A user can run:

```
structai ingest sales_q3.xlsx --target postgresql://localhost/warehouse
```

and end up with:

- a `scripts/sales_q3/<ts>/` directory containing a readable `import.py`, `schema.sql`, and `manifest.json`,
- the data loaded into a sensibly-named table with sensible types,
- a validation report,
- and the script saved so re-running on `sales_q4.xlsx` next quarter requires zero or near-zero LLM calls.
