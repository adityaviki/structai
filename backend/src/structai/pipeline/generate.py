"""Stage 2: ask the LLM for a schema DDL + runnable import.py."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..agent.client import call_tool
from ..agent.prompts import PROPOSE_IMPORT_TOOL, SYSTEM_GENERATE, render_generate_user_message

if TYPE_CHECKING:
    from .profile import FileProfile


@dataclass(slots=True)
class GenerateResult:
    schema_ddl: str
    import_script: str
    rationale: str
    tables: list[str]


async def generate_import(
    *,
    profile: FileProfile,
    existing_tables: list[str],
    instructions: str | None,
    model: str | None = None,
) -> GenerateResult:
    profile_json = json.dumps(profile.to_dict(), indent=2)
    user_text = render_generate_user_message(
        profile_json=profile_json,
        existing_tables=existing_tables,
        instructions=instructions,
    )

    result = await call_tool(
        system=SYSTEM_GENERATE,
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
