from __future__ import annotations

import re

from ulid import ULID

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def new_id() -> str:
    """Return a fresh ULID string (sortable, URL-safe)."""

    return str(ULID())


def slugify(name: str, max_len: int = 32) -> str:
    """Lowercase ASCII slug; collapses non-alphanumerics to underscores."""

    out = _SLUG_RE.sub("_", name.lower()).strip("_")
    if not out:
        out = "project"
    return out[:max_len]


def project_db_name(slug: str, project_id: str) -> str:
    """Build the Postgres database name for a project.

    Format: structai_<slug>_<short_id>. The short id is the first 8 chars of
    the project's ULID to ensure uniqueness without exceeding PG's 63-char
    identifier limit.
    """

    short = project_id[:8].lower()
    base = f"structai_{slug}_{short}"
    return base[:63]
