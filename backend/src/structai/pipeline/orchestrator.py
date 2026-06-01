"""Orchestrates the import pipeline as an arq job (Phase 2).

Pipeline:

    profile → generate → (snapshot) → execute → [fix → execute] × ≤MAX_FIX → validate
                                                ^                          ^
                                                |                          |
                                                +- bounded retry loop -----+

Per D15: a per-run Postgres template-DB snapshot is created before the
first execute attempt and serves as the rollback point. On any non-success
terminus (failure, cancel, max-fixes-exceeded, validate fails) the
snapshot is either dropped (live DB is byte-identical to pre-run) or used
to restore (validate failed *after* a successful execute committed).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable  # noqa: TC003 -- used at runtime
from datetime import UTC, datetime
from typing import Any

from ..agent import events
from ..agent.decide import auto_decide
from ..db import clarifications_repo, runs_repo, schema_proposals_repo
from ..db.ids import new_id
from ..db.pool import with_database
from ..db.schema_intro import format_for_llm, introspect_project
from ..db.snapshots import create_snapshot, drop_snapshot, restore_from_snapshot
from ..logging import log
from ..settings import get_settings
from ..workspace.storage import run_dir, workspace_root
from .execute import ExecuteResult, execute_script
from .fix import fix_import
from .generate import generate_import
from .profile import DocumentProfile, profile_document
from .propose_schema import (
    SchemaProposal,
    propose_schema_step,
    revise_schema_step,
)
from .validate import validate_project

MAX_FIX_ATTEMPTS = 5

# How long the orchestrator will wait for a human response (clarification
# answer or schema-proposal decision) before giving up on the run. Set
# lower than the arq job_timeout (see worker.main.WorkerSettings) so the
# orchestrator owns the failure, not arq — that way we can mark the run
# failed with a clean error message instead of leaving it pinned.
HUMAN_WAIT_TIMEOUT_S = 4 * 3600


class _HumanWaitTimeoutError(Exception):
    """Raised by the polling loops when the user takes too long."""


def _now() -> datetime:
    return datetime.now(UTC)


def _profile_summary(profile: DocumentProfile) -> str:
    if not profile.regions:
        return "No regions detected."
    if len(profile.regions) == 1:
        r = profile.regions[0]
        return f"{r.row_count} rows · {len(r.columns)} columns"
    parts = [f"{len(profile.regions)} regions"]
    for r in profile.regions:
        parts.append(f"  - `{r.name}`: {r.row_count} rows · {len(r.columns)} columns")
    return "\n".join(parts)


def _snapshot_name(project_db: str, run_id: str) -> str:
    """Build a PG-identifier-legal snapshot DB name unique to this run.

    Postgres caps identifiers at 63 chars. python-ulid generates
    monotonic ULIDs: same-millisecond IDs share the first 10 (timestamp)
    AND most of the next 16 (random) characters, differing only in the
    LAST few chars where the monotonic counter increments. So we keep
    the TAIL of the ULID, not the head — that's where the entropy
    actually lives within a millisecond.

    We reserve at least 16 chars for the ULID tail (`min_suffix`), which
    in monotonic mode keeps the full random block plus part of the
    timestamp — uniqueness is effectively guaranteed for any realistic
    enqueue rate.
    """

    infix = "_snap_"
    min_suffix = 16
    max_project_len = 63 - len(infix) - min_suffix
    project_part = (
        project_db if len(project_db) <= max_project_len else project_db[:max_project_len]
    )
    available = 63 - len(project_part) - len(infix)
    return f"{project_part}{infix}{run_id.lower()[-available:]}"


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
    attempts: int = 1,
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
        attempts=attempts,
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
            "attempts": attempts,
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
    await events.publish(run_id, {"type": "run_status", "status": status, "progress": progress})


class _CancelledError(Exception):
    """Raised by _check_cancel to unwind the pipeline cleanly."""


async def _check_cancel(run_id: str) -> None:
    if await runs_repo.cancel_requested(run_id):
        raise _CancelledError


def _format_answer(question: str, options: list[dict[str, Any]], record: dict[str, Any]) -> str:
    """Turn a clarification record into a string we feed back as tool_result."""

    picked = record.get("answer_choice_id")
    custom = record.get("answer_custom")
    auto = record.get("auto_decision", False)
    reasoning = record.get("auto_reasoning")

    chosen_label: str | None = None
    if picked:
        for o in options:
            if o.get("id") == picked:
                chosen_label = o.get("label") or picked
                break

    parts = []
    parts.append(f"User's answer to: {question!r}")
    if picked:
        parts.append(f"- choice: {picked} ({chosen_label})")
    if custom:
        parts.append(f"- custom instruction: {custom}")
    if auto:
        parts.append(f"(auto-decided on user's behalf; reasoning: {reasoning})")
    return "\n".join(parts)


def _make_clarification_handler(
    *,
    run_id: str,
    auto_mode: bool,
    resume_status: str,
    resume_progress: int,
) -> Callable[[str, str | None, list[dict[str, Any]]], Awaitable[str]]:
    async def handler(
        question: str,
        context: str | None,
        options: list[dict[str, Any]],
    ) -> str:
        await _check_cancel(run_id)
        clar_id = new_id()
        await clarifications_repo.create_clarification(
            clar_id=clar_id,
            run_id=run_id,
            question=question,
            context=context,
            options=options,
        )
        await events.publish(
            run_id,
            {"type": "clarification", "clarification_id": clar_id, "question": question},
        )

        if auto_mode:
            try:
                choice_id, reasoning = await auto_decide(
                    question=question, context=context, options=options
                )
            except Exception as exc:  # noqa: BLE001
                # If auto-decide fails, fall back to "first option" with a note.
                choice_id = options[0]["id"] if options else "_unknown"
                reasoning = f"Auto-decide failed ({exc!s}); defaulted to first option."
            await clarifications_repo.record_auto_decision(
                clar_id=clar_id, choice_id=choice_id, reasoning=reasoning
            )
            record = {
                "answer_choice_id": choice_id,
                "auto_decision": True,
                "auto_reasoning": reasoning,
            }
            await events.publish(
                run_id,
                {
                    "type": "clarification_answered",
                    "clarification_id": clar_id,
                    "auto": True,
                },
            )
            return _format_answer(question, options, record)

        # Manual mode: suspend, poll DB until answered or cancelled.
        await _set_status(run_id, "needs_clarification")
        wait_started = _now()
        while True:
            await _check_cancel(run_id)
            if await clarifications_repo.is_answered(clar_id):
                break
            if (_now() - wait_started).total_seconds() > HUMAN_WAIT_TIMEOUT_S:
                raise _HumanWaitTimeoutError(
                    f"No answer received within {HUMAN_WAIT_TIMEOUT_S // 3600}h "
                    f"of asking the clarification."
                )
            await asyncio.sleep(1)

        rec = await clarifications_repo.get_clarification(clar_id)
        assert rec is not None
        await _set_status(run_id, resume_status, progress=resume_progress)
        await events.publish(
            run_id,
            {"type": "clarification_answered", "clarification_id": clar_id, "auto": False},
        )
        return _format_answer(
            question,
            options,
            {
                "answer_choice_id": rec["answer_choice_id"],
                "answer_custom": rec["answer_custom"],
                "auto_decision": rec["auto_decision"],
                "auto_reasoning": rec["auto_reasoning"],
            },
        )

    return handler


def _proposal_summary(proposal: SchemaProposal) -> str:
    table_list = ", ".join(f"`{t}`" for t in proposal.tables) or "(no tables)"
    return f"{table_list}\n\n{proposal.rationale.strip()}"


async def _run_schema_approval_loop(
    *,
    run_id: str,
    profile: DocumentProfile,
    existing_schema: str,
    instructions: str | None,
    auto_mode: bool,
    model_override: str | None,
) -> tuple[str, list[str]]:
    """Drive the propose/accept/revise loop until a proposal is accepted.

    Returns the accepted ``(schema_ddl, tables)``. Suspends the run with
    ``awaiting_schema_approval`` status between iterations when not in
    auto mode. In auto mode, accepts the first proposal immediately.
    """

    iteration = 1
    previous_iterations: list[dict[str, str]] = []
    iteration_started: datetime = _now()

    while True:
        await _check_cancel(run_id)
        if iteration == 1:
            await _set_status(run_id, "generating", progress=15)
            await _emit_step(
                run_id,
                step_key="propose_schema",
                status="running",
                title="Propose schema",
                started_at=iteration_started,
                attempts=iteration,
            )
            schema_clarify = _make_clarification_handler(
                run_id=run_id,
                auto_mode=auto_mode,
                resume_status="generating",
                resume_progress=15,
            )
            proposal = await propose_schema_step(
                profile=profile,
                existing_schema=existing_schema,
                instructions=instructions,
                on_clarification=schema_clarify,
                model=model_override,
            )
        else:
            await _set_status(run_id, "generating", progress=20)
            await _emit_step(
                run_id,
                step_key="propose_schema",
                status="running",
                title=f"Revise schema (iteration {iteration})",
                started_at=iteration_started,
                attempts=iteration,
            )
            schema_clarify = _make_clarification_handler(
                run_id=run_id,
                auto_mode=auto_mode,
                resume_status="generating",
                resume_progress=20,
            )
            proposal = await revise_schema_step(
                profile=profile,
                existing_schema=existing_schema,
                instructions=instructions,
                previous_iterations=previous_iterations,
                feedback=previous_iterations[-1]["feedback"],
                on_clarification=schema_clarify,
                model=model_override,
            )

        proposal_id = new_id()
        await schema_proposals_repo.create_proposal(
            proposal_id=proposal_id,
            run_id=run_id,
            iteration=iteration,
            schema_ddl=proposal.schema_ddl,
            tables=proposal.tables,
            rationale=proposal.rationale,
        )
        await _emit_step(
            run_id,
            step_key="propose_schema",
            status="success" if auto_mode else "warning",
            title=(
                "Propose schema"
                if iteration == 1
                else f"Revise schema (iteration {iteration})"
            ),
            summary=_proposal_summary(proposal),
            code=proposal.schema_ddl,
            language="sql",
            started_at=iteration_started,
            duration_ms=int((_now() - iteration_started).total_seconds() * 1000),
            attempts=iteration,
        )
        await events.publish(
            run_id,
            {
                "type": "schema_proposal",
                "proposal_id": proposal_id,
                "iteration": iteration,
            },
        )

        if auto_mode:
            await schema_proposals_repo.accept(proposal_id=proposal_id, auto=True)
            await events.publish(
                run_id,
                {"type": "schema_proposal_decided", "proposal_id": proposal_id, "auto": True},
            )
            return proposal.schema_ddl, proposal.tables

        # Manual mode: suspend until user accepts or asks to revise.
        await _set_status(run_id, "awaiting_schema_approval")
        wait_started = _now()
        while True:
            await _check_cancel(run_id)
            if await schema_proposals_repo.is_decided(proposal_id):
                break
            if (_now() - wait_started).total_seconds() > HUMAN_WAIT_TIMEOUT_S:
                raise _HumanWaitTimeoutError(
                    f"No decision on the proposed schema within "
                    f"{HUMAN_WAIT_TIMEOUT_S // 3600}h."
                )
            await asyncio.sleep(1)

        rec = await schema_proposals_repo.get_proposal(proposal_id)
        assert rec is not None
        if rec["status"] == "accepted":
            await events.publish(
                run_id,
                {"type": "schema_proposal_decided", "proposal_id": proposal_id, "auto": False},
            )
            return proposal.schema_ddl, proposal.tables

        # Superseded → push this iteration onto the history and loop.
        previous_iterations.append(
            {
                "schema_ddl": proposal.schema_ddl,
                "rationale": proposal.rationale,
                "feedback": rec["feedback"] or "",
            }
        )
        iteration += 1
        iteration_started = _now()


async def _cancel_watchdog(run_id: str, cancel_event: asyncio.Event) -> None:
    """Background task: polls the DB and sets the event if cancel is requested.

    Phase 2 simple polling. The Redis pubsub-driven wake-up is the icing
    we add when it matters; at one-import-per-worker scale a 1s poll is
    invisible.
    """

    try:
        while not cancel_event.is_set():
            if await runs_repo.cancel_requested(run_id):
                cancel_event.set()
                return
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        return


async def run_import(run_id: str) -> None:
    log.info("orchestrator.start", run_id=run_id)
    record = await runs_repo.get_run(run_id)
    if record is None:
        log.error("orchestrator.run_missing", run_id=run_id)
        return

    project_db = str(record["project_db_name"])
    doc_storage_path = str(record["document_storage_path"])
    doc_ext = str(record["document_ext"])
    instructions: str | None = record["instructions"]
    model_override: str | None = record["project_model_override"]
    settings = get_settings()
    project_pg_url = with_database(settings.pg_url, project_db)

    doc_path = (workspace_root() / doc_storage_path).resolve()
    workdir_root = run_dir(run_id)

    snapshot_db = _snapshot_name(project_db, run_id)
    snapshot_taken = False

    cancel_event = asyncio.Event()
    watchdog = asyncio.create_task(_cancel_watchdog(run_id, cancel_event))

    try:
        # --- profile ---
        await _check_cancel(run_id)
        await _set_status(run_id, "profiling", progress=10)
        started = _now()
        profile = profile_document(doc_path, doc_ext)
        await _emit_step(
            run_id,
            step_key="profile",
            status="success",
            title="Profile document",
            summary=_profile_summary(profile),
            started_at=started,
            duration_ms=int((_now() - started).total_seconds() * 1000),
        )

        # --- propose schema ---
        await _check_cancel(run_id)
        auto_mode = bool(record["auto_mode"])
        existing = await introspect_project(project_db)
        existing_schema = format_for_llm(existing)

        approved_schema_ddl, approved_tables = await _run_schema_approval_loop(
            run_id=run_id,
            profile=profile,
            existing_schema=existing_schema,
            instructions=instructions,
            auto_mode=auto_mode,
            model_override=model_override,
        )

        # --- generate (attempt 1) ---
        await _check_cancel(run_id)
        await _set_status(run_id, "generating", progress=25)
        started = _now()
        gen_clarify = _make_clarification_handler(
            run_id=run_id,
            auto_mode=auto_mode,
            resume_status="generating",
            resume_progress=25,
        )

        gen = await generate_import(
            profile=profile,
            approved_schema_ddl=approved_schema_ddl,
            approved_tables=approved_tables,
            instructions=instructions,
            on_clarification=gen_clarify,
            model=model_override,
        )
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

        # --- snapshot ---
        await _check_cancel(run_id)
        await create_snapshot(settings=settings, project_db=project_db, snapshot_db=snapshot_db)
        snapshot_taken = True
        await _set_status(run_id, "generating", progress=35, snapshot_db=snapshot_db)

        # --- execute / fix loop ---
        attempt = 1
        current = gen
        execute_res: ExecuteResult | None = None
        while True:
            await _check_cancel(run_id)
            await _set_status(run_id, "executing", progress=40 + (attempt - 1) * 10)
            started = _now()
            workdir = workdir_root / f"attempt-{attempt}"
            execute_res = await execute_script(
                script=current.import_script,
                doc_path=doc_path,
                pg_url=project_pg_url,
                workdir=workdir,
                cancel_event=cancel_event,
            )
            (workdir / "stdout.log").write_text(execute_res.stdout)
            (workdir / "stderr.log").write_text(execute_res.stderr)

            if execute_res.cancelled:
                raise _CancelledError

            if execute_res.exit_code == 0 and not execute_res.timed_out:
                await _emit_step(
                    run_id,
                    step_key="execute",
                    status="success",
                    title="Execute import script",
                    summary=f"{execute_res.rows_imported or 0} rows · {', '.join(execute_res.tables_reported) or '(no tables reported)'}",
                    started_at=started,
                    duration_ms=execute_res.duration_ms,
                    attempts=attempt,
                )
                break

            # Failure path.
            err_tail = "\n".join(execute_res.stderr.splitlines()[-40:])
            await _emit_step(
                run_id,
                step_key="execute",
                status="error",
                title="Execute import script",
                summary="Timed out" if execute_res.timed_out else f"Exit code {execute_res.exit_code}",
                code=current.import_script,
                language="python",
                errors=[err_tail] if err_tail else None,
                started_at=started,
                duration_ms=execute_res.duration_ms,
                attempts=attempt,
            )

            if attempt >= MAX_FIX_ATTEMPTS:
                if snapshot_taken:
                    await drop_snapshot(settings=settings, snapshot_db=snapshot_db)
                    snapshot_taken = False
                await _set_status(
                    run_id,
                    "failed",
                    progress=80,
                    error_message=f"Gave up after {MAX_FIX_ATTEMPTS} attempts.",
                    finished_at=_now(),
                    clear_snapshot=True,
                )
                await events.publish(run_id, {"type": "failed"})
                return

            # --- fix (next attempt) ---
            await _check_cancel(run_id)
            attempt += 1
            await _set_status(run_id, "fixing", progress=40 + (attempt - 1) * 10)
            started = _now()
            fix_clarify = _make_clarification_handler(
                run_id=run_id,
                auto_mode=auto_mode,
                resume_status="fixing",
                resume_progress=40 + (attempt - 1) * 10,
            )
            current = await fix_import(
                profile=profile,
                approved_schema_ddl=approved_schema_ddl,
                previous_script=current.import_script,
                stderr_tail=err_tail,
                attempt_number=attempt,
                instructions=instructions,
                on_clarification=fix_clarify,
                model=model_override,
            )
            await _emit_step(
                run_id,
                step_key="fix",
                status="success",
                title=f"Diagnose & rewrite (attempt {attempt})",
                summary=current.rationale,
                code=current.import_script,
                language="python",
                started_at=started,
                duration_ms=int((_now() - started).total_seconds() * 1000),
                attempts=attempt,
            )
            # Loop back to execute.

        # --- validate ---
        await _check_cancel(run_id)
        await _set_status(run_id, "validating", progress=90)
        started = _now()
        assert execute_res is not None
        val = await validate_project(
            db_name=project_db,
            reported_tables=execute_res.tables_reported,
            reported_rows=execute_res.rows_imported,
        )
        summary_lines = [f"- `{t.table}`: {t.row_count} rows" for t in val.tables]
        if val.warnings:
            summary_lines += ["", "Warnings:", *(f"- {w}" for w in val.warnings)]
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
            if snapshot_taken:
                await restore_from_snapshot(
                    settings=settings, project_db=project_db, snapshot_db=snapshot_db
                )
                snapshot_taken = False
            await _set_status(
                run_id,
                "failed",
                progress=95,
                error_message="; ".join(val.errors) or "Validation failed.",
                rows_imported=val.total_rows,
                created_tables=execute_res.tables_reported,
                finished_at=_now(),
                clear_snapshot=True,
            )
            await events.publish(run_id, {"type": "failed"})
            return

        await _set_status(
            run_id,
            "completed",
            progress=100,
            rows_imported=val.total_rows,
            total_rows=val.total_rows,
            created_tables=execute_res.tables_reported,
            finished_at=_now(),
        )
        await events.publish(run_id, {"type": "completed"})
        log.info("orchestrator.complete", run_id=run_id, rows=val.total_rows, attempts=attempt)

    except _CancelledError:
        if snapshot_taken:
            await drop_snapshot(settings=settings, snapshot_db=snapshot_db)
        await _set_status(
            run_id,
            "cancelled",
            progress=None,
            error_message="Cancelled by user.",
            finished_at=_now(),
            clear_snapshot=True,
        )
        await events.publish(run_id, {"type": "cancelled"})
        log.info("orchestrator.cancelled", run_id=run_id)

    except _HumanWaitTimeoutError as exc:
        if snapshot_taken:
            with contextlib.suppress(Exception):
                await drop_snapshot(settings=settings, snapshot_db=snapshot_db)
        await _set_status(
            run_id,
            "failed",
            error_message=str(exc),
            finished_at=_now(),
            clear_snapshot=True,
        )
        await events.publish(run_id, {"type": "failed"})
        log.info("orchestrator.human_wait_timeout", run_id=run_id)

    except Exception as exc:  # noqa: BLE001
        if snapshot_taken:
            try:
                await drop_snapshot(settings=settings, snapshot_db=snapshot_db)
            except Exception:  # noqa: BLE001
                log.exception("orchestrator.snapshot_cleanup_failed", run_id=run_id)
        await _set_status(
            run_id,
            "failed",
            error_message=f"Unhandled error: {exc!s}",
            finished_at=_now(),
            clear_snapshot=True,
        )
        await events.publish(run_id, {"type": "failed"})
        log.exception("orchestrator.failed", run_id=run_id)

    finally:
        watchdog.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await watchdog


__all__ = ["MAX_FIX_ATTEMPTS", "run_import"]
