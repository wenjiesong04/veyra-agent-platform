"""Preserve user requirement provenance independently of bounded chat history."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from veyra_agent_platform.contracts.common import ContractValidationError

MAX_REQUIREMENT_CHARACTERS = 100_000


def user_requirement_context(
    messages: Iterable[Mapping[str, Any]],
    current_content: str,
    *,
    before: str | None = None,
) -> str:
    """Capture user turns only; never promote model summaries or failures to goals.

    A retry adds no user message. Legacy operations can reconstruct their exact
    prefix from the originating turn's timestamp, excluding later amendments.
    Consecutive duplicate turns carry no additional instruction, but A→B→A
    corrections retain their order. No requirement is silently truncated.
    """
    turns: list[str] = []
    for row in messages:
        if row.get("role") != "user" or row.get("kind") != "user":
            continue
        if before is not None and str(row.get("created_at") or "") > before:
            continue
        content = str(row.get("content") or "").strip()
        if content and (not turns or turns[-1] != content):
            turns.append(content)
    current = current_content.strip()
    if current and (not turns or turns[-1] != current):
        turns.append(current)
    if len(turns) == 1:
        context = turns[0]
    else:
        context = (
            "User requirements in chronological order. Interpret the current "
            "request using these original user statements. Later explicit "
            "corrections supersede conflicting earlier statements; completed "
            "unrelated tasks are context, not new obligations. Never infer a "
            "missing requirement from an assistant summary or Project description.\n\n"
            + "\n\n".join(
                f"User turn {index}:\n{content}"
                for index, content in enumerate(turns, start=1)
            )
        )
    if len(context) > MAX_REQUIREMENT_CHARACTERS:
        raise ContractValidationError(
            "Builder requirement context exceeds the size limit; "
            "start a new conversation with the complete current requirements."
        )
    return context
