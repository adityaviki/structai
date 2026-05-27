"""Orchestrates the import pipeline as an arq job.

Phase 1 sequence:

    profile  →  generate  →  execute  →  validate  →  completed

No fix loop, no clarifications yet (those land in Phase 2 / Phase 3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..agent import events
from ..agent.client import call_tool  # noqa: F401  (imported to surface errors early)
from ..db import runs_repo
from ..db.pool import with_database
from ..logging import log
from ..settings import get_settings
from ..workspace.storage import run_dir, workspace_root
from .execute import execute_script
from .generate import generate_import
from .profile import profile_document
from .validate import validate_project


def _now() -> datetime:
    return datetime.now(UTC)


async def _emit_step(
    run_id: str,
    *,
    step_key: str,
    status: str,
    title: str,
    summary: str | None = None,
    code: str | None = None,
    language: str | None = None,
    started_at: datetime | None = None,
    duration_ms: int | None = None,
    errors: list[str] | None = None,
) -> None:
    await runs_repo.upsert_step(
        run_id=run_id,
        step_key=step_key,
        status=status,
        title=title,
        summary=summary,
        code=code,
        language=language,
        started_at=started_at,
        duration_ms=duration_ms,
        errors=errors,
    )
    await events.publish(
        run_id,
        {
            "type": "step",
            "step_key": step_key,
            "status": status,
            "title": title,
            "summary": summary,
            "duration_ms": duration_ms,
            "errors": errors,
        },
    )


async def _set_status(
    run_id: str,
    status: str,
    *,
    progress: int | None = None,
    **kwargs: Any,
) -> None:
    await runs_repo.set_run_status(run_id=run_id, status=status, progress=progress, **kwargs)
    await events.publish(
        run_id,
        {"type": "run_status", "status": status, "progress": progress},
    )


async def run_import(run_id: str) -> None:
    """Top-level pipeline entry. Called by the arq worker."""

    log.info("orchestrator.start", run_id=run_id)
    record = await runs_repo.get_run(run_id)
    if record is None:
        log.error("orchestrator.run_missing", run_id=run_id)
        return

    project_db = str(record["project_db_name"])
    doc_storage_path = str(record["document_storage_path"])
    doc_ext = str(record["document_ext"])
    instructions = record["instructions"]

    doc_path = (workspace_root() / doc_storage_path).resolve()
    workdir = run_dir(run_id) / "attempt-1"

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------
    await _set_status(run_id, "profiling", progress=10)
    started = _now()
    try:
        profile = profile_document(doc_path, doc_ext)
    except Exception as exc:  # noqa: BLE001
        await _emit_step(
            run_id,
            step_key="profile",
            status="error",
            title="Profile document",
            errors=[str(exc)],
            started_at=started,
            duration_ms=int((_now() - started).total_seconds() * 1000),
        )
        await _set_status(
            run_id, "failed", progress=10, error_message=f"Profile failed: {exc}", finished_at=_now()
        )
        await events.publish(run_id, {"type": "failed"})
        return

    await _emit_step(
        run_id,
        step_key="profile",
        status="success",
        title="Profile document",
        summary=f"{profile.total_rows} rows · {len(profile.columns)} columns",
        started_at=started,
        duration_ms=int((_now() - started).total_seconds() * 1000),
    )

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------
    await _set_status(run_id, "generating", progress=30)
    started = _now()
    try:
        gen = await generate_import(
            profile=profile,
            existing_tables=[],  # Phase 1: skip schema introspection of project DB.
            instructions=instructions,
        )
    except Exception as exc:  # noqa: BLE001
        await _emit_step(
            run_id,
            step_key="generate",
            status="error",
            title="Generate import script",
            errors=[str(exc)],
            started_at=started,
            duration_ms=int((_now() - started).total_seconds() * 1000),
        )
        await _set_status(
            run_id, "failed", progress=30, error_message=f"Generate failed: {exc}", finished_at=_now()
        )
        await events.publish(run_id, {"type": "failed"})
        return

    await _emit_step(
        run_id,
        step_key="generate",
        status="success",
        title="Generate import script",
        summary=gen.rationale,
        code=gen.import_script,
        language="python",
        started_at=started,
        duration_ms=int((_now() - started).total_seconds() * 1000),
    )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------
    await _set_status(run_id, "executing", progress=60)
    started = _now()
    settings = get_settings()
    project_pg_url = with_database(settings.pg_url, project_db)
    exe = await execute_script(
        script=gen.import_script,
        doc_path=doc_path,
        pg_url=project_pg_url,
        workdir=workdir,
    )
    (workdir / "stdout.log").write_text(exe.stdout)
    (workdir / "stderr.log").write_text(exe.stderr)

    if exe.exit_code != 0 or exe.timed_out:
        err_tail = "\n".join(exe.stderr.splitlines()[-30:])
        await _emit_step(
            run_id,
            step_key="execute",
            status="error",
            title="Execute import script",
            summary=("Timed out" if exe.timed_out else f"Exit code {exe.exit_code}"),
            errors=[err_tail] if err_tail else None,
            started_at=started,
            duration_ms=exe.duration_ms,
        )
        await _set_status(
            run_id,
            "failed",
            progress=60,
            error_message=f"Execute failed (exit={exe.exit_code}, timed_out={exe.timed_out}).",
            finished_at=_now(),
        )
        await events.publish(run_id, {"type": "failed"})
        return

    await _emit_step(
        run_id,
        step_key="execute",
        status="success",
        title="Execute import script",
        summary=f"{exe.rows_imported or 0} rows · {', '.join(exe.tables_reported)}",
        started_at=started,
        duration_ms=exe.duration_ms,
    )

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------
    await _set_status(run_id, "validating", progress=85)
    started = _now()
    val = await validate_project(
        db_name=project_db,
        reported_tables=exe.tables_reported,
        reported_rows=exe.rows_imported,
    )
    summary_lines: list[str] = []
    for t in val.tables:
        summary_lines.append(f"- `{t.table}`: {t.row_count} rows")
    if val.warnings:
        summary_lines.append("")
        summary_lines.append("Warnings:")
        summary_lines.extend(f"- {w}" for w in val.warnings)
    step_status = "success" if val.ok else "error"
    await _emit_step(
        run_id,
        step_key="validate",
        status=step_status,
        title="Validate import",
        summary="\n".join(summary_lines) if summary_lines else None,
        errors=val.errors or None,
        started_at=started,
        duration_ms=int((_now() - started).total_seconds() * 1000),
    )

    if not val.ok:
        await _set_status(
            run_id,
            "failed",
            progress=95,
            error_message="; ".join(val.errors),
            rows_imported=val.total_rows,
            created_tables=exe.tables_reported,
            finished_at=_now(),
        )
        await events.publish(run_id, {"type": "failed"})
        return

    await _set_status(
        run_id,
        "completed",
        progress=100,
        rows_imported=val.total_rows,
        total_rows=val.total_rows,
        created_tables=exe.tables_reported,
        finished_at=_now(),
    )
    await events.publish(run_id, {"type": "completed"})
    log.info("orchestrator.complete", run_id=run_id, rows=val.total_rows)
