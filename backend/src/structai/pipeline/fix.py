"""Stage: ask the LLM to fix a failed import script."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ..agent.client import call_tool
from ..agent.prompts import PROPOSE_IMPORT_TOOL, SYSTEM_FIX, render_fix_user_message
from .generate import GenerateResult

if TYPE_CHECKING:
    from .profile import FileProfile


async def fix_import(
    *,
    profile: FileProfile,
    previous_script: str,
    stderr_tail: str,
    attempt_number: int,
    instructions: str | None,
    model: str | None = None,
) -> GenerateResult:
    profile_json = json.dumps(profile.to_dict(), indent=2)
    user_text = render_fix_user_message(
        profile_json=profile_json,
        previous_script=previous_script,
        stderr_tail=stderr_tail,
        attempt_number=attempt_number,
        instructions=instructions,
    )

    result = await call_tool(
        system=SYSTEM_FIX,
        user_blocks=[{"type": "text", "text": user_text}],
        tool=PROPOSE_IMPORT_TOOL,
        model=model,
    )

    return GenerateResult(
        schema_ddl=str(result["schema_ddl"]),
        import_script=str(result["import_script"]),
        rationale=str(result["rationale"]),
        tables=list(result["tables"]),
    )
