"""Stage 3: execute the generated import script in a subprocess."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003 -- used at runtime in helper signatures


@dataclass(slots=True)
class ExecuteResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    rows_imported: int | None
    tables_reported: list[str]
    timed_out: bool
    cancelled: bool = False


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
    for raw in stdout.splitlines():
        line = raw.strip()
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
    cancel_event: asyncio.Event | None = None,
) -> ExecuteResult:
    """Run the generated script as a subprocess.

    Returns the result regardless of exit code; the caller decides how to
    react to failures. If ``cancel_event`` is provided and gets set during
    execution, the subprocess is terminated promptly and ``cancelled`` is
    set on the result.
    """

    script_path = _write_script(workdir, script)
    env = _build_env()
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
    cancelled = False

    communicate_task = asyncio.create_task(proc.communicate())
    aux_tasks: list[asyncio.Task[object]] = [
        asyncio.create_task(asyncio.sleep(timeout_seconds), name="timeout"),
    ]
    if cancel_event is not None:
        aux_tasks.append(asyncio.create_task(cancel_event.wait(), name="cancel"))

    done, _pending = await asyncio.wait(
        {communicate_task, *aux_tasks},
        return_when=asyncio.FIRST_COMPLETED,
    )

    # Always cancel the aux tasks — we never need them once one of them fires.
    for t in aux_tasks:
        if not t.done():
            t.cancel()

    if communicate_task in done:
        stdout_b, stderr_b = communicate_task.result()
    else:
        for t in done:
            if t.get_name() == "cancel":
                cancelled = True
            elif t.get_name() == "timeout":
                timed_out = True
        proc.terminate()
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                asyncio.shield(communicate_task), timeout=3
            )
        except TimeoutError:
            proc.kill()
            stdout_b, stderr_b = await communicate_task

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
        cancelled=cancelled,
    )
