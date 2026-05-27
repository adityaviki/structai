"""Stage 2: ask the LLM for a schema DDL + runnable import.py.

Uses an agentic loop so the model can call `ask_clarification` mid-stream
when it needs a judgment call from the user.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ..agent.client import agentic_loop
from ..agent.prompts import (
    ASK_CLARIFICATION_TOOL,
    PROPOSE_IMPORT_TOOL,
    SYSTEM_GENERATE,
    render_generate_user_message,
)
from .profile import DocumentProfile  # noqa: TC001 -- used at runtime in signature

ClarificationHandler = Callable[[str, str | None, list[dict[str, Any]]], Awaitable[str]]


@dataclass(slots=True)
class GenerateResult:
    schema_ddl: str
    import_script: str
    rationale: str
    tables: list[str]


async def generate_import(
    *,
    profile: DocumentProfile,
    existing_tables: list[str],
    instructions: str | None,
    on_clarification: ClarificationHandler | None = None,
    model: str | None = None,
) -> GenerateResult:
    profile_json = json.dumps(profile.to_dict(), indent=2)
    user_text = render_generate_user_message(
        profile_json=profile_json,
        existing_tables=existing_tables,
        instructions=instructions,
    )

    async def _handle_tool_call(name: str, inputs: dict[str, Any]) -> str:
        if name == "ask_clarification":
            if on_clarification is None:
                # No suspend mechanism wired up — refuse so the model proceeds.
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

    tools = [PROPOSE_IMPORT_TOOL]
    if on_clarification is not None:
        tools = [PROPOSE_IMPORT_TOOL, ASK_CLARIFICATION_TOOL]

    result = await agentic_loop(
        system=SYSTEM_GENERATE,
        initial_user_blocks=[{"type": "text", "text": user_text}],
        tools=tools,
        terminal_tool_name="propose_import",
        handle_tool_call=_handle_tool_call,
        model=model,
    )

    return GenerateResult(
        schema_ddl=str(result["schema_ddl"]),
        import_script=str(result["import_script"]),
        rationale=str(result["rationale"]),
        tables=list(result["tables"]),
    )
