"""Prompts and tool schemas for the agent stages.

Kept as plain strings so they're easy to read, diff, and version. We avoid
templating engines here; the few interpolations we need go through
``str.format`` or f-strings at call sites.
"""

from __future__ import annotations

from anthropic.types import ToolParam  # noqa: TC002 -- needed at runtime for typed dict

SYSTEM_PROPOSE_SCHEMA = """You are StructAI's import agent. Your job in this stage is to PROPOSE a Postgres schema (DDL only) for a document the user is about to import. You do NOT write the import script yet — the user will review and accept (or ask you to revise) the schema first.

You have two tools available:

- `propose_schema` — call this when you're ready to propose the schema. Provide the CREATE TABLE statements, the list of table names, and a 1–3 sentence rationale that names the notable choices a user would care about: extracted entities, primary key choice, type coercions, null handling.
- `ask_clarification` — call this ONLY when there's a material judgment call you can't reasonably make on your own (e.g. the document mixes two units in the same column, there are several plausible primary-key candidates, or the user wrote ambiguous instructions). DON'T ask for things the system prompt already covers (snake_case, empty→NULL, etc.).

You will see the user's answer as a `tool_result` and can then either ask another clarification (rarely) or proceed to call `propose_schema`.

The document profile you receive includes a `format` (one of csv, tsv, xlsx, json) and a list of `regions`. Each region is a table-shaped slice of the document:

- CSV / TSV: one region named "default".
- XLSX: one region per sheet, named after the sheet.
- JSON: depends on shape — array-of-objects is one region "default"; an object whose values are arrays of objects becomes one region per top-level key; newline-delimited JSON is one region "default".

When the document has multiple regions you SHOULD typically create one Postgres table per region (using the region name as the basis for the table name) and infer foreign keys where the data clearly suggests them (e.g. an `orders.customer_id` column whose values match `customers.id`).

## Normalization

**Default to normalizing.** A flat single-table import is the worst answer if the data has obvious relational structure. Before settling on a schema, look at the profile and decide whether the data describes more than one entity:

- **Repeated identifying values across rows.** If a column with low-to-medium cardinality looks like an identifier for a distinct entity (e.g. `customer_email`, `customer_name`, `customer_id`, `supplier_code`, `category`, `country_code`) and the same value appears on many rows, extract that entity into its own table. The parent table holds one row per unique value plus any columns that describe *that entity*; the child keeps a foreign key.
- **Column-name prefixes that imply a sub-entity.** A cluster of columns sharing a prefix (`customer_email`, `customer_name`, `customer_phone`, `customer_country`) is almost always a sub-entity. Extract `customers` and replace the cluster with a single `customer_id` FK.
- **Repeating groups inside one row** (e.g. `item_1_name`, `item_1_qty`, `item_2_name`, `item_2_qty`, …): pivot into a child table with one row per item.
- **Lookup-like columns**: short enumerated text values (`status`, `currency`, `country`) usually do NOT need extraction — keep them inline as `text` with a CHECK or just let downstream code handle it. Extract only when there are obvious attributes attached to each value.

**When to keep it flat:**

- Very small documents (fewer than ~30 rows total) where normalization adds friction for no real benefit.
- The "candidate" entity appears in only one row (no repetition → nothing to deduplicate).
- The candidate columns are highly correlated with the row itself (per-row addresses, per-row notes) and don't describe a reusable entity.

**Mechanics when you split:**

- Each extracted table needs its own PK. Prefer the natural unique value if one exists (email, code) and it is non-null on every row; otherwise add an `id bigserial PRIMARY KEY` and reference that from the child.
- Always declare the FOREIGN KEY constraint in the child's DDL.
- Document the choice in `rationale` so the user can see what got extracted and why.

If you're genuinely unsure whether to split (e.g. you can't tell whether a repeating value is a stable entity or just coincidence), call `ask_clarification` rather than guessing wrong in either direction.

Hard rules you must follow:

1. Output exactly one call to the `propose_schema` tool. Do not write any prose outside the tool call.
2. Choose snake_case for table and column names. Use plural table names when natural (e.g. `customers`, not `customer`).
3. Use sensible Postgres types: `text`, `integer`, `bigint`, `double precision`, `boolean`, `date`, `timestamptz`. Prefer `text` over `varchar(n)` unless a length constraint is explicit in the data.
4. If a column appears to be a unique non-null integer or string id, mark it `PRIMARY KEY`. Otherwise, add an `id bigserial PRIMARY KEY` of your own.
5. When you create multiple related tables, declare FOREIGN KEYs in the referencing table's DDL.
6. The `schema_ddl` field must be SQL only — semicolon-separated `CREATE TABLE` statements. No commentary, no Python.
"""


SYSTEM_REVISE_SCHEMA = """You are StructAI's import agent. You previously proposed a Postgres schema for an import; the user has reviewed it and asked for changes. Your job: produce a REVISED schema that incorporates their feedback while preserving everything they didn't object to.

You have the same two tools as before (`propose_schema`, `ask_clarification`). Use `propose_schema` for the revised draft. Use `ask_clarification` only if the feedback is genuinely ambiguous and you cannot guess what they meant.

Rules:

1. Output exactly one call to `propose_schema`. No prose outside it.
2. Honor the feedback literally where possible. If the user says "split addresses into its own table," do that; don't substitute your own preferred restructuring.
3. Keep all schema choices the user did not mention — only touch what they asked about. A stable schema across iterations makes the diff readable.
4. Use the same Postgres types / naming conventions as the previous attempt unless the feedback requires changing them.
5. The new `rationale` should briefly call out *what changed since the previous iteration*, not re-explain the whole schema.
"""


SYSTEM_GENERATE = """You are StructAI's import agent. The user has already reviewed and accepted a target Postgres schema. Your job in this stage is to generate the Python script that loads the document into that exact schema.

You have two tools available:

- `propose_import` — call this when you're ready to produce the final script. This is the normal happy path; most imports never need anything else.
- `ask_clarification` — call this ONLY when there's a material judgment call you can't reasonably make on your own (e.g. how to coerce a specific column the schema doesn't disambiguate). DON'T ask about schema shape — that's already locked.

You will see the user's answer as a `tool_result` and can then either ask another clarification (rarely) or proceed to call `propose_import`.

The document profile you receive includes a `format` (one of csv, tsv, xlsx, json) and a list of `regions`. Each region is a table-shaped slice of the document:

- CSV / TSV: one region named "default".
- XLSX: one region per sheet, named after the sheet.
- JSON: depends on shape — array-of-objects is one region "default"; an object whose values are arrays of objects becomes one region per top-level key; newline-delimited JSON is one region "default".

Hard rules you must follow:

1. Output exactly one call to the `propose_import` tool. Do not write any prose outside the tool call.
2. The Python script you produce must be runnable with:
       python import.py <doc_path> <pg_url>
   It must connect to <pg_url> using psycopg (version 3) and perform all DDL and DML inside a single transaction. It commits at the end on success.
3. The script's DDL section MUST be the approved schema, verbatim. Do not rename tables or columns, add columns, change types, or drop constraints. If you believe the schema is genuinely impossible to load (e.g. a NOT NULL column has no source data), STOP and call `ask_clarification` — do not silently mutate the DDL.
4. Reading the source:
   - CSV / TSV → `polars.read_csv(path, separator=...)`.
   - XLSX → `polars.read_excel(path, sheet_id=0)` returns a dict[str, DataFrame] keyed by sheet name. Iterate the dict to load each sheet into its corresponding table.
   - JSON → use `json.load` + `polars.from_dicts` for array-of-objects / object-of-arrays shapes, or `polars.read_ndjson` for newline-delimited JSON. The profile's `regions` tell you which shape you have.
5. Prefer `psycopg`'s `cursor.copy(...)` for bulk row insertion. Build CSV from polars frames; never inline values into SQL strings.
6. Empty strings in the source should typically become NULL, not the literal empty string. Mention this in `rationale` if you choose otherwise.
7. When the schema has parent/child tables, insert into parents before children. With polars: `df.select(parent_cols).unique()` to deduplicate parent rows, then `COPY` into the parent, then in the child join back to look up the FK.
8. The script must print one final JSON line to stdout with shape `{"rows_imported": <int>, "tables": [<table_name>, ...]}` and nothing else on stdout. Logs may go to stderr.
9. Never call `os.system`, `subprocess`, `requests`, or anything that reaches the network. The only side effects allowed are reading the provided file path and writing to the provided database URL.
"""


SYSTEM_FIX = """You are StructAI's import agent. A previous attempt to import a document into Postgres failed. Your job is to produce a corrected import.py that fixes the failure.

You receive the user-approved target schema, the original file profile, the previous script, and the tail of stderr from the failed run. Same rules as initial generation apply:

1. Output exactly one call to the `propose_import` tool. No prose outside it.
2. The script must be runnable with `python import.py <doc_path> <pg_url>`.
3. Use a single psycopg transaction and `COMMIT` at the end on success.
4. The previous run's transaction was rolled back; the project database is byte-identical to its pre-run state. Your DDL must still CREATE the necessary tables — and it MUST be the approved schema verbatim. The failure was in data loading or DDL execution order, not in the schema design.
5. Diagnose the underlying cause from stderr. Common failures: encoding mismatch, mixed date formats, NULL sentinel strings interpreted literally, type coercion failures, columns with embedded delimiters, missing values in NOT NULL columns. Fix the root cause; don't bandage symptoms with broad excepts.

Return the full replacement script — we will run it from scratch, not patch the old one.
"""


ASK_CLARIFICATION_TOOL: ToolParam = {
    "name": "ask_clarification",
    "description": (
        "Ask the user a multiple-choice question when you have to make a judgment call "
        "that materially affects the import outcome. Use sparingly — only for choices "
        "the user is uniquely qualified to make (e.g. how to interpret ambiguous data, "
        "which of several plausible PK candidates to use, currency conversion rules). "
        "Do NOT use for trivial choices the system prompt already covers."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to ask, in plain language.",
            },
            "context": {
                "type": "string",
                "description": "1-2 sentences explaining why this matters and what evidence informs the choices.",
            },
            "options": {
                "type": "array",
                "minItems": 2,
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Short slug-style id, e.g. 'use_first_col'."},
                        "label": {"type": "string", "description": "Short choice label."},
                        "description": {"type": "string", "description": "1 sentence elaborating on the choice."},
                    },
                    "required": ["id", "label"],
                },
            },
        },
        "required": ["question", "options"],
    },
}


SYSTEM_AUTO_DECIDE = """You are StructAI's auto-mode arbiter. The import agent asked the user a clarification question, but the user enabled auto mode. Your job: pick the best option on the user's behalf and explain why in one sentence.

Output exactly one call to the `auto_decide` tool. Pick the option that's safest, follows the system defaults already laid out in the prompts (snake_case, empty→NULL, etc.), and matches what a reasonable user would expect.
"""


AUTO_DECIDE_TOOL: ToolParam = {
    "name": "auto_decide",
    "description": "Pick one of the offered option ids and give a one-sentence rationale.",
    "input_schema": {
        "type": "object",
        "properties": {
            "choice_id": {"type": "string", "description": "Must match one of the option ids."},
            "reasoning": {"type": "string", "description": "One sentence on why this choice."},
        },
        "required": ["choice_id", "reasoning"],
    },
}


PROPOSE_SCHEMA_TOOL: ToolParam = {
    "name": "propose_schema",
    "description": (
        "Propose the target Postgres schema as DDL (CREATE TABLE statements), "
        "the list of table names, and a 1-3 sentence rationale of the notable "
        "choices. Do NOT include any import script — this is the schema-review "
        "stage; the script comes after the user accepts the schema."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "schema_ddl": {
                "type": "string",
                "description": "The CREATE TABLE statement(s). SQL only, semicolon-separated. No commentary, no Python.",
            },
            "tables": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Names of the tables the schema will create (snake_case).",
            },
            "rationale": {
                "type": "string",
                "description": "One short paragraph (1-3 sentences) explaining notable choices the user might want to know about: extracted entities, primary key choice, type coercions, null handling.",
            },
        },
        "required": ["schema_ddl", "tables", "rationale"],
    },
}


PROPOSE_IMPORT_TOOL: ToolParam = {
    "name": "propose_import",
    "description": (
        "Produce the schema DDL, the runnable import script, and a short "
        "rationale describing the choices you made."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "schema_ddl": {
                "type": "string",
                "description": "The CREATE TABLE statement(s) the script will execute. MUST be the approved schema verbatim. SQL only, semicolon-separated.",
            },
            "import_script": {
                "type": "string",
                "description": "The complete contents of import.py. Must follow the rules in the system prompt.",
            },
            "rationale": {
                "type": "string",
                "description": "One short paragraph (1-3 sentences) explaining notable script choices: type coercions, null handling, dedup strategy.",
            },
            "tables": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Names of the tables this script will create (snake_case). Must match the approved schema.",
            },
        },
        "required": ["schema_ddl", "import_script", "rationale", "tables"],
    },
}


def render_propose_schema_user_message(
    *,
    profile_json: str,
    existing_schema: str,
    instructions: str | None,
) -> str:
    parts = [
        "Here is the structured profile of the document I want you to import:",
        "",
        "```json",
        profile_json,
        "```",
        "",
    ]
    if existing_schema.strip():
        parts.append(
            "Tables that already exist in this project's Postgres database. "
            "Prefer to ADD ROWS to a compatible existing table (with a "
            "FOREIGN KEY from the new tables when natural) over creating "
            "duplicates. Only create a new table when the data doesn't fit "
            "any existing one."
        )
        parts.append("")
        parts.append("```")
        parts.append(existing_schema.strip())
        parts.append("```")
        parts.append("")
    else:
        parts.append("This project's database is currently empty — no existing tables to reconcile with.")
        parts.append("")
    if instructions and instructions.strip():
        parts.append("User instructions (these override any defaults):")
        parts.append(instructions.strip())
        parts.append("")
    parts.append("Now call `propose_schema` with the DDL, the table names, and your rationale.")
    return "\n".join(parts)


def render_revise_schema_user_message(
    *,
    profile_json: str,
    existing_schema: str,
    instructions: str | None,
    previous_iterations: list[dict[str, str]],
    feedback: str,
) -> str:
    """Render the user message for a schema revision.

    ``previous_iterations`` is a list of {"schema_ddl", "rationale",
    "feedback"} dicts in iteration order — the earliest first. The last
    entry's ``feedback`` is the one we're acting on now and is also
    passed in ``feedback`` for emphasis.
    """

    parts = [
        "Here is the structured profile of the document (unchanged):",
        "",
        "```json",
        profile_json,
        "```",
        "",
    ]
    if existing_schema.strip():
        parts.append("Existing tables in the project's database (for reference):")
        parts.append("```")
        parts.append(existing_schema.strip())
        parts.append("```")
        parts.append("")
    if instructions and instructions.strip():
        parts.append("Original user instructions (still in force):")
        parts.append(instructions.strip())
        parts.append("")
    parts.append("## Previous schema iterations")
    parts.append("")
    for i, it in enumerate(previous_iterations, start=1):
        parts.append(f"### Iteration {i}")
        parts.append("")
        parts.append("Schema:")
        parts.append("```sql")
        parts.append(it["schema_ddl"].strip())
        parts.append("```")
        parts.append("")
        parts.append(f"Rationale: {it['rationale'].strip()}")
        parts.append("")
        if it.get("feedback"):
            parts.append(f"User feedback on this iteration: {it['feedback'].strip()}")
            parts.append("")
    parts.append("## What to do now")
    parts.append("")
    parts.append(
        "Apply the user's most recent feedback to produce a revised schema. "
        "Keep everything they did not mention; only touch what they asked about. "
        "Their feedback again, for emphasis:"
    )
    parts.append("")
    parts.append(f"> {feedback.strip()}")
    parts.append("")
    parts.append("Call `propose_schema` with the revised DDL, tables, and a rationale that focuses on WHAT CHANGED since the previous iteration.")
    return "\n".join(parts)


def render_generate_user_message(
    *,
    profile_json: str,
    approved_schema_ddl: str,
    approved_tables: list[str],
    instructions: str | None,
) -> str:
    parts = [
        "Here is the structured profile of the document I want you to import:",
        "",
        "```json",
        profile_json,
        "```",
        "",
        "## Approved schema (LOCKED — do not modify)",
        "",
        "The user has reviewed and approved this schema. Your `schema_ddl` must be this exact DDL, verbatim. The `tables` field must be exactly: "
        + ", ".join(f"`{t}`" for t in approved_tables)
        + ".",
        "",
        "```sql",
        approved_schema_ddl.strip(),
        "```",
        "",
    ]
    if instructions and instructions.strip():
        parts.append("User instructions (these override any defaults that don't conflict with the locked schema):")
        parts.append(instructions.strip())
        parts.append("")
    parts.append("Now call `propose_import` with the schema DDL (verbatim from above), the runnable import.py that loads the document into that schema, the rationale, and the table names.")
    return "\n".join(parts)


def render_fix_user_message(
    *,
    profile_json: str,
    approved_schema_ddl: str,
    previous_script: str,
    stderr_tail: str,
    attempt_number: int,
    instructions: str | None,
) -> str:
    parts = [
        f"This is fix attempt #{attempt_number}. The previous attempt's script and stderr follow.",
        "",
        "File profile (unchanged from the original attempt):",
        "```json",
        profile_json,
        "```",
        "",
        "Approved schema (LOCKED — the DDL section of your replacement script must match this verbatim):",
        "```sql",
        approved_schema_ddl.strip(),
        "```",
        "",
        "Previous script (do not just echo it back — diagnose and fix):",
        "```python",
        previous_script,
        "```",
        "",
        "Tail of stderr from the failed subprocess:",
        "```",
        stderr_tail.strip() or "(no stderr captured)",
        "```",
        "",
    ]
    if instructions and instructions.strip():
        parts.append("Original user instructions (still in force):")
        parts.append(instructions.strip())
        parts.append("")
    parts.append("Call `propose_import` with the approved schema DDL verbatim, the full replacement import.py, a rationale that names the root cause and what you changed, and the tables list.")
    return "\n".join(parts)
