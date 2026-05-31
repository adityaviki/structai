"""Stage: ask the LLM to fix a failed import script.

Same agentic-loop shape as generate, so the model can ask the user a
clarification in the middle of diagnosing the failure (rare but useful).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from ..agent.client import agentic_loop
from ..agent.prompts import (
    ASK_CLARIFICATION_TOOL,
    PROPOSE_IMPORT_TOOL,
    SYSTEM_FIX,
    render_fix_user_message,
)
from .generate import GenerateResult

if TYPE_CHECKING:
    from .profile import DocumentProfile

ClarificationHandler = Callable[[str, str | None, list[dict[str, Any]]], Awaitable[str]]


async def fix_import(
    *,
    profile: DocumentProfile,
    approved_schema_ddl: str,
    previous_script: str,
    stderr_tail: str,
    attempt_number: int,
    instructions: str | None,
    on_clarification: ClarificationHandler | None = None,
    model: str | None = None,
) -> GenerateResult:
    profile_json = json.dumps(profile.to_dict(), indent=2)
    user_text = render_fix_user_message(
        profile_json=profile_json,
        approved_schema_ddl=approved_schema_ddl,
        previous_script=previous_script,
        stderr_tail=stderr_tail,
        attempt_number=attempt_number,
        instructions=instructions,
    )

    async def _handle_tool_call(name: str, inputs: dict[str, Any]) -> str:
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

    tools = [PROPOSE_IMPORT_TOOL]
    if on_clarification is not None:
        tools = [PROPOSE_IMPORT_TOOL, ASK_CLARIFICATION_TOOL]

    result = await agentic_loop(
        system=SYSTEM_FIX,
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
