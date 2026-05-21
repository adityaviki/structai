"""Column-name sanitization for the managed `structai_user` schema.

Plan §5 line 176 + CHECKLIST.md lines 101-102. Deterministic rewrite of
raw header strings into Postgres-safe identifiers:

    trim → NFKC normalize → replace `[^0-9a-zA-Z]+` with `_` → strip
    edges → lowercase → leading-digit prepend → empty fallback → PG
    reserved-word `_col` suffix → 63-char truncate (NAMEDATALEN-1).

`sanitize_columns` then resolves safe-name collisions across positions
with `_2`, `_3`, … suffixes (truncating the base if needed to keep the
total ≤ 63).
"""

from __future__ import annotations

import re
import unicodedata

# PostgreSQL 16 reserved words (`SELECT word FROM pg_get_keywords() WHERE
# catcode = 'R'`). Frozenset literal so `structai-core` doesn't pick up a
# runtime dep on `psycopg` just to know what the reserved set is.
POSTGRES_RESERVED: frozenset[str] = frozenset(
    {
        "all", "analyse", "analyze", "and", "any", "array", "as", "asc",
        "asymmetric", "both", "case", "cast", "check", "collate", "column",
        "constraint", "create", "current_catalog", "current_date",
        "current_role", "current_time", "current_timestamp", "current_user",
        "default", "deferrable", "desc", "distinct", "do", "else", "end",
        "except", "false", "fetch", "for", "foreign", "from", "grant",
        "group", "having", "in", "initially", "intersect", "into", "lateral",
        "leading", "limit", "localtime", "localtimestamp", "not", "null",
        "offset", "on", "only", "or", "order", "placing", "primary",
        "references", "returning", "select", "session_user", "some",
        "symmetric", "system_user", "table", "then", "to", "trailing",
        "true", "union", "unique", "user", "using", "variadic", "when",
        "where", "window", "with",
    }
)

MAX_IDENTIFIER_LEN = 63  # Postgres NAMEDATALEN (64) - 1
_NON_ALPHANUM = re.compile(r"[^0-9a-zA-Z]+")


def sanitize(raw: str) -> str:
    s = raw.strip()
    s = unicodedata.normalize("NFKC", s)
    s = _NON_ALPHANUM.sub("_", s)
    s = s.strip("_").lower()
    if not s:
        s = "_col"
    if s[0].isdigit():
        s = "_" + s
    if s in POSTGRES_RESERVED:
        s = s + "_col"
    if len(s) > MAX_IDENTIFIER_LEN:
        s = s[:MAX_IDENTIFIER_LEN]
    return s


def sanitize_columns(raw_names: list[str]) -> dict[str, str]:
    """Map raw header names → Postgres-safe identifiers. Resolves
    safe-name collisions across positions with `_2` / `_3` / … suffixes
    so every output value is unique.

    Note: if `raw_names` contains literal duplicates, only the last
    occurrence survives in the returned dict (dict keys must be unique).
    Phase 1 CSV fixtures don't exercise that case; we accept it as a
    known limitation rather than complicating the public type.
    """
    used: set[str] = set()
    result: dict[str, str] = {}
    for raw in raw_names:
        base = sanitize(raw)
        candidate = base
        n = 2
        while candidate in used:
            suffix = f"_{n}"
            base_room = MAX_IDENTIFIER_LEN - len(suffix)
            candidate = base[:base_room] + suffix
            n += 1
        used.add(candidate)
        result[raw] = candidate
    return result
