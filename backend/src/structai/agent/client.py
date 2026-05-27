"""Thin Anthropic SDK wrapper.

Wraps the parts of the SDK we actually call so the rest of the codebase
doesn't import `anthropic` directly. This is the single point we'd swap if
we ever add a second provider (deferred per D5a).
"""

from __future__ import annotations

import json
from typing import Any

from anthropic import AsyncAnthropic
from anthropic.types import (
    MessageParam,
    TextBlockParam,
    ToolChoiceToolParam,
    ToolParam,
    ToolUseBlock,
)

from ..settings import get_settings


def _client() -> AsyncAnthropic:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "Anthropic API key missing. Set STRUCTAI_ANTHROPIC_API_KEY in your env or .env."
        )
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


async def call_tool(
    *,
    system: str,
    user_blocks: list[TextBlockParam],
    tool: ToolParam,
    model: str | None = None,
    max_tokens: int = 8000,
) -> dict[str, Any]:
    """Call the model with a forced tool choice and return its tool input dict.

    System prompt + tool schemas are cache-able (cache_control breakpoints
    placed on the system block and on the tool definition).
    """

    client = _client()
    settings = get_settings()
    chosen_model = model or settings.default_model

    messages: list[MessageParam] = [{"role": "user", "content": user_blocks}]

    tool_choice: ToolChoiceToolParam = {"type": "tool", "name": tool["name"]}

    resp = await client.messages.create(
        model=chosen_model,
        max_tokens=max_tokens,
        system=[
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[tool],
        tool_choice=tool_choice,
        messages=messages,
    )

    for block in resp.content:
        if isinstance(block, ToolUseBlock) and block.name == tool["name"]:
            input_val = block.input
            if isinstance(input_val, str):
                # Some models occasionally return a string instead of a dict for
                # tool input; parse defensively.
                return json.loads(input_val)
            assert isinstance(input_val, dict)
            return input_val

    raise RuntimeError(
        f"Model did not call the expected tool {tool['name']!r}. "
        f"Stop reason: {resp.stop_reason}"
    )
