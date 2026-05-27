"""Prompts and tool schemas for the agent stages.

Kept as plain strings so they're easy to read, diff, and version. We avoid
templating engines here; the few interpolations we need go through
``str.format`` or f-strings at call sites.
"""

from __future__ import annotations

from anthropic.types import ToolParam  # noqa: TC002 -- needed at runtime for typed dict

SYSTEM_GENERATE = """You are StructAI's import agent. You generate Python scripts that load a single document into a Postgres database.

You have two tools available:

- `propose_import` — call this when you're ready to produce the final script. This is the normal happy path; most imports never need anything else.
- `ask_clarification` — call this ONLY when there's a material judgment call you can't reasonably make on your own. Examples of when to ask: the document mixes two units in the same column, there are several plausible primary-key candidates, or the user wrote ambiguous instructions. DON'T ask for things the system prompt already covers (snake_case, empty→NULL, etc.).

You will see the user's answer as a `tool_result` and can then either ask another clarification (rarely) or proceed to call `propose_import`.

Hard rules you must follow:

1. Output exactly one call to the `propose_import` tool. Do not write any
   prose outside the tool call.
2. The Python script you produce must be runnable with:
       python import.py <doc_path> <pg_url>
   It must connect to <pg_url> using psycopg (version 3) and perform all
   DDL and DML inside a single transaction. It commits at the end on
   success.
3. Use `polars` for reading the source file and prefer `psycopg`'s
   `cursor.copy(...)` for bulk row insertion.
4. Choose snake_case for table and column names. Use plural table names
   when natural (e.g. `customers`, not `customer`).
5. Use sensible Postgres types: `text`, `integer`, `bigint`, `double
   precision`, `boolean`, `date`, `timestamptz`. Prefer `text` over
   `varchar(n)` unless a length constraint is explicit in the data.
6. If a column appears to be a unique non-null integer or string id, mark
   it `PRIMARY KEY`. Otherwise, add an `id bigserial PRIMARY KEY` of your
   own.
7. Empty strings in the source should typically become NULL, not the
   literal empty string. Mention this in `rationale` if you choose
   otherwise.
8. The script must print one final JSON line to stdout with shape
   `{"rows_imported": <int>, "tables": [<table_name>, ...]}` and nothing
   else on stdout. Logs may go to stderr.
9. Never call `os.system`, `subprocess`, `requests`, or anything that
   reaches the network. The only side effects allowed are reading the
   provided file path and writing to the provided database URL.

You are running in Phase 1, which means single-CSV / single-table imports
are the common case. Multi-table imports are out of scope for now, but if
the file naturally splits into multiple related tables you may still
propose them.
"""


SYSTEM_FIX = """You are StructAI's import agent. A previous attempt to import a document into Postgres failed. Your job is to produce a corrected import.py that fixes the failure.

You receive the original file profile, the previous script, and the tail of stderr from the failed run. Same rules as initial generation apply:

1. Output exactly one call to the `propose_import` tool. No prose outside it.
2. The script must be runnable with `python import.py <doc_path> <pg_url>`.
3. Use a single psycopg transaction and `COMMIT` at the end on success.
4. The previous run's transaction was rolled back; the project database is byte-identical to its pre-run state. Your DDL must still CREATE the necessary tables.
5. Diagnose the underlying cause from stderr. Common failures: encoding mismatch, mixed date formats, NULL sentinel strings interpreted literally, type coercion failures, columns with embedded delimiters, missing values in NOT NULL columns. Fix the root cause; don't bandage symptoms with broad excepts.
6. Keep the schema close to the previous attempt unless the schema itself was wrong. Stable schemas make the user's mental model easier.

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
                "description": "The CREATE TABLE statement(s) the script will execute. SQL only, semicolon-separated.",
            },
            "import_script": {
                "type": "string",
                "description": "The complete contents of import.py. Must follow the rules in the system prompt.",
            },
            "rationale": {
                "type": "string",
                "description": "One short paragraph (1-3 sentences) explaining notable choices the user might want to know about: type coercions, primary key choice, null handling.",
            },
            "tables": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Names of the tables this script will create (snake_case).",
            },
        },
        "required": ["schema_ddl", "import_script", "rationale", "tables"],
    },
}


def render_generate_user_message(*, profile_json: str, existing_tables: list[str], instructions: str | None) -> str:
    parts = [
        "Here is the structured profile of the document I want you to import:",
        "",
        "```json",
        profile_json,
        "```",
        "",
    ]
    if existing_tables:
        parts.append("Tables that already exist in this project's database (avoid name clashes unless you intend to extend them):")
        parts.append(", ".join(existing_tables))
        parts.append("")
    if instructions and instructions.strip():
        parts.append("User instructions (these override any defaults):")
        parts.append(instructions.strip())
        parts.append("")
    parts.append("Now call `propose_import` with the schema DDL, the runnable import.py, the rationale, and the table names.")
    return "\n".join(parts)


def render_fix_user_message(
    *,
    profile_json: str,
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
    parts.append("Call `propose_import` with the corrected schema DDL, the full replacement import.py, a rationale that names the root cause and what you changed, and the tables list.")
    return "\n".join(parts)
