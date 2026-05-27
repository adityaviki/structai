"""Prompts and tool schemas for the agent stages.

Kept as plain strings so they're easy to read, diff, and version. We avoid
templating engines here; the few interpolations we need go through
``str.format`` or f-strings at call sites.
"""

from __future__ import annotations

from anthropic.types import ToolParam  # noqa: TC002 -- needed at runtime for typed dict

SYSTEM_GENERATE = """You are StructAI's import agent. You generate Python scripts that load a single document into a Postgres database.

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
