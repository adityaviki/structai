"""Stage 2a: ask the LLM for a schema (DDL only).

Runs an agentic loop with the ``propose_schema`` tool. May iterate when
the user requests revisions — each call to ``propose_schema_step``
produces one proposal; the orchestrator decides whether to accept it or
to call ``revise_schema_step`` with the user's feedback.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ..agent.client import agentic_loop
from ..agent.prompts import (
    ASK_CLARIFICATION_TOOL,
    PROPOSE_SCHEMA_TOOL,
    SYSTEM_PROPOSE_SCHEMA,
    SYSTEM_REVISE_SCHEMA,
    render_propose_schema_user_message,
    render_revise_schema_user_message,
)
from .profile import DocumentProfile  # noqa: TC001 -- used at runtime in signature

ClarificationHandler = Callable[[str, str | None, list[dict[str, Any]]], Awaitable[str]]


@dataclass(slots=True)
class SchemaProposal:
    schema_ddl: str
    tables: list[str]
    rationale: str


def _make_handle_tool_call(
    on_clarification: ClarificationHandler | None,
) -> Callable[[str, dict[str, Any]], Awaitable[str]]:
    async def _handle(name: str, inputs: dict[str, Any]) -> str:
        if name == "ask_clarification":
            if on_clarification is None:
                return (
                    "Clarification mechanism not available in this run; "
                    "pick the most reasonable option yourself and proceed."
                )
            return await on_clarification(
                str(inputs["question"]),
                inputs.get("context"),
                list(inputs.get("options", [])),
            )
        return f"Unexpected tool: {name}"

    return _handle


async def propose_schema_step(
    *,
    profile: DocumentProfile,
    existing_schema: str,
    instructions: str | None,
    on_clarification: ClarificationHandler | None = None,
    model: str | None = None,
) -> SchemaProposal:
    profile_json = json.dumps(profile.to_dict(), indent=2)
    user_text = render_propose_schema_user_message(
        profile_json=profile_json,
        existing_schema=existing_schema,
        instructions=instructions,
    )

    tools = [PROPOSE_SCHEMA_TOOL]
    if on_clarification is not None:
        tools = [PROPOSE_SCHEMA_TOOL, ASK_CLARIFICATION_TOOL]

    result = await agentic_loop(
        system=SYSTEM_PROPOSE_SCHEMA,
        initial_user_blocks=[{"type": "text", "text": user_text}],
        tools=tools,
        terminal_tool_name="propose_schema",
        handle_tool_call=_make_handle_tool_call(on_clarification),
        model=model,
    )

    return SchemaProposal(
        schema_ddl=str(result["schema_ddl"]),
        tables=list(result["tables"]),
        rationale=str(result["rationale"]),
    )


async def revise_schema_step(
    *,
    profile: DocumentProfile,
    existing_schema: str,
    instructions: str | None,
    previous_iterations: list[dict[str, str]],
    feedback: str,
    on_clarification: ClarificationHandler | None = None,
    model: str | None = None,
) -> SchemaProposal:
    profile_json = json.dumps(profile.to_dict(), indent=2)
    user_text = render_revise_schema_user_message(
        profile_json=profile_json,
        existing_schema=existing_schema,
        instructions=instructions,
        previous_iterations=previous_iterations,
        feedback=feedback,
    )

    tools = [PROPOSE_SCHEMA_TOOL]
    if on_clarification is not None:
        tools = [PROPOSE_SCHEMA_TOOL, ASK_CLARIFICATION_TOOL]

    result = await agentic_loop(
        system=SYSTEM_REVISE_SCHEMA,
        initial_user_blocks=[{"type": "text", "text": user_text}],
        tools=tools,
        terminal_tool_name="propose_schema",
        handle_tool_call=_make_handle_tool_call(on_clarification),
        model=model,
    )

    return SchemaProposal(
        schema_ddl=str(result["schema_ddl"]),
        tables=list(result["tables"]),
        rationale=str(result["rationale"]),
    )
