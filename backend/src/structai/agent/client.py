"""Thin Anthropic SDK wrapper.

Wraps the parts of the SDK we actually call so the rest of the codebase
doesn't import `anthropic` directly. This is the single point we'd swap if
we ever add a second provider (deferred per D5a).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable  # noqa: TC003 -- used at runtime in signatures
from typing import Any

from anthropic import AsyncAnthropic
from anthropic.types import (
    MessageParam,
    TextBlockParam,
    ToolChoiceAnyParam,
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


def _block_input(block: ToolUseBlock) -> dict[str, Any]:
    input_val = block.input
    if isinstance(input_val, str):
        return json.loads(input_val)
    assert isinstance(input_val, dict)
    return input_val


async def call_tool(
    *,
    system: str,
    user_blocks: list[TextBlockParam],
    tool: ToolParam,
    model: str | None = None,
    max_tokens: int = 8000,
) -> dict[str, Any]:
    """Call the model with a forced tool choice and return its tool input dict."""

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
            return _block_input(block)

    raise RuntimeError(
        f"Model did not call the expected tool {tool['name']!r}. "
        f"Stop reason: {resp.stop_reason}"
    )


async def agentic_loop(
    *,
    system: str,
    initial_user_blocks: list[TextBlockParam],
    tools: list[ToolParam],
    terminal_tool_name: str,
    handle_tool_call: Callable[[str, dict[str, Any]], Awaitable[str]],
    model: str | None = None,
    max_tokens: int = 8000,
    max_iterations: int = 10,
) -> dict[str, Any]:
    """Run an agent loop.

    The model is forced to call *some* tool on each turn (``tool_choice =
    any``). When it calls ``terminal_tool_name``, we return its input dict.
    For any other tool call, ``handle_tool_call(name, input_dict)`` is
    awaited and its return string is fed back to the model as a
    ``tool_result``.

    Bounded by ``max_iterations`` to keep cost predictable.
    """

    client = _client()
    settings = get_settings()
    chosen_model = model or settings.default_model

    messages: list[MessageParam] = [{"role": "user", "content": initial_user_blocks}]
    tool_choice: ToolChoiceAnyParam = {"type": "any"}

    for _ in range(max_iterations):
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
            tools=tools,
            tool_choice=tool_choice,
            messages=messages,
        )

        tool_use_blocks = [b for b in resp.content if isinstance(b, ToolUseBlock)]
        if not tool_use_blocks:
            raise RuntimeError(
                f"Agent loop: model returned no tool calls. Stop reason: {resp.stop_reason}"
            )

        # If the model called the terminal tool, return its input.
        for block in tool_use_blocks:
            if block.name == terminal_tool_name:
                return _block_input(block)

        # Otherwise the model called a non-terminal tool. Append the assistant
        # turn verbatim, then a user turn with one tool_result per tool_use.
        messages.append({"role": "assistant", "content": resp.content})
        tool_results: list[dict[str, Any]] = []
        for block in tool_use_blocks:
            try:
                content = await handle_tool_call(block.name, _block_input(block))
            except Exception as exc:  # noqa: BLE001
                content = f"Tool error: {exc!s}"
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                }
            )
        messages.append({"role": "user", "content": tool_results})  # type: ignore[typeddict-item]

    raise RuntimeError(
        f"Agent loop exceeded max_iterations={max_iterations} without calling {terminal_tool_name!r}."
    )
