"""Stage 3: execute the generated import script in a subprocess.

Phase 1 implementation. Phase 2 will wrap this in a per-run snapshot and a
real transaction (D15), and Phase 2 also adds the fix loop on failure.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(slots=True)
class ExecuteResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    rows_imported: int | None
    tables_reported: list[str]
    timed_out: bool


def _write_script(workdir: Path, source: str) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    path = workdir / "import.py"
    path.write_text(source)
    return path


def _build_env() -> dict[str, str]:
    """Curated env allowlist (D6). Drop secrets; keep what Python needs."""

    keep = {"PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TMPDIR"}
    base = {k: v for k, v in os.environ.items() if k in keep}
    base.setdefault("PYTHONUNBUFFERED", "1")
    base.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    return base


def _parse_summary(stdout: str) -> tuple[int | None, list[str]]:
    """The script prints one final JSON line per the prompt contract."""

    last = None
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            last = line
    if not last:
        return None, []
    try:
        obj = json.loads(last)
    except json.JSONDecodeError:
        return None, []
    rows = obj.get("rows_imported")
    tables = obj.get("tables") or []
    if isinstance(rows, int) and isinstance(tables, list):
        return rows, [str(t) for t in tables]
    return None, []


async def execute_script(
    *,
    script: str,
    doc_path: Path,
    pg_url: str,
    workdir: Path,
    timeout_seconds: int = 300,
    python_executable: str | None = None,
) -> ExecuteResult:
    """Run the generated script as a subprocess.

    Returns the result regardless of exit code; the caller decides how to
    react to failures.
    """

    script_path = _write_script(workdir, script)
    env = _build_env()
    # Hand the script the inputs it needs via argv; never via env, to make
    # the contract explicit.
    cmd = [
        python_executable or sys.executable,
        "-u",
        str(script_path),
        str(doc_path),
        pg_url,
    ]

    start = asyncio.get_event_loop().time()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=workdir,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    timed_out = False
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        timed_out = True
        proc.terminate()
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=3)
        except TimeoutError:
            proc.kill()
            stdout_b, stderr_b = await proc.communicate()

    duration_ms = int((asyncio.get_event_loop().time() - start) * 1000)
    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    rows, tables = _parse_summary(stdout)

    return ExecuteResult(
        exit_code=proc.returncode if proc.returncode is not None else -1,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        rows_imported=rows,
        tables_reported=tables,
        timed_out=timed_out,
    )
