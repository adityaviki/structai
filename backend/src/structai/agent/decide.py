"""Auto-mode arbiter: have the LLM pick a clarification answer on its own."""

from __future__ import annotations

import json
from typing import Any

from .client import call_tool
from .prompts import AUTO_DECIDE_TOOL, SYSTEM_AUTO_DECIDE


async def auto_decide(
    *,
    question: str,
    context: str | None,
    options: list[dict[str, Any]],
    model: str | None = None,
) -> tuple[str, str]:
    """Return ``(choice_id, reasoning)``."""

    payload = {
        "question": question,
        "context": context,
        "options": options,
    }
    user_text = (
        "The import agent asked the user this clarification question, but the user enabled "
        "auto mode. Pick one option id on their behalf and explain why in one sentence.\n\n"
        "```json\n"
        + json.dumps(payload, indent=2)
        + "\n```"
    )
    result = await call_tool(
        system=SYSTEM_AUTO_DECIDE,
        user_blocks=[{"type": "text", "text": user_text}],
        tool=AUTO_DECIDE_TOOL,
        model=model,
    )
    return str(result["choice_id"]), str(result["reasoning"])
