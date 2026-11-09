"""Public progress signals for the Agent loop: plan, repeated calls, turn budget.

A plan is a short user-visible checklist, never hidden reasoning. It cannot
change permissions, approvals or outputs; invalid plans are ignored.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from veyra_agent_platform.contracts.canonical import sha256_digest

PLAN_STEP_STATUSES = ("pending", "in_progress", "done", "blocked")
MAX_PLAN_STEPS = 12
MAX_PLAN_TEXT = 200
# Only a timeout may legitimately succeed when repeated with identical input.
RETRYABLE_OBSERVATION_CODES = frozenset({"tool_timeout"})
MAX_REPEATED_CALLS = 2


def public_plan(raw: Any) -> dict[str, Any] | None:
    """Normalize a model-supplied plan, or return None when it is not usable."""

    if not isinstance(raw, Mapping):
        return None
    raw_steps = raw.get("steps")
    if not isinstance(raw_steps, list) or not 0 < len(raw_steps) <= MAX_PLAN_STEPS:
        return None
    steps: list[dict[str, str]] = []
    for entry in raw_steps:
        title: Any
        status: Any
        if isinstance(entry, str):
            title, status = entry, "pending"
        elif isinstance(entry, Mapping):
            title, status = entry.get("title"), entry.get("status", "pending")
        else:
            return None
        if (
            not isinstance(title, str)
            or not title.strip()
            or len(title.strip()) > MAX_PLAN_TEXT
            or status not in PLAN_STEP_STATUSES
        ):
            return None
        steps.append({"title": title.strip(), "status": str(status)})
    plan: dict[str, Any] = {"steps": steps}
    goal = raw.get("goal")
    if isinstance(goal, str) and goal.strip():
        if len(goal.strip()) > MAX_PLAN_TEXT:
            return None
        plan["goal"] = goal.strip()
    return plan


def tool_call_fingerprint(reference: str, arguments: Mapping[str, Any]) -> str:
    return sha256_digest({"tool": reference, "arguments": dict(arguments)})


def executed_call_state(
    reference: str, arguments: Mapping[str, Any], output: Any
) -> dict[str, Any]:
    """Remember the latest executed call so an identical next request is caught."""

    retryable = (
        isinstance(output, Mapping)
        and output.get("outcome") == "failed"
        and output.get("code") in RETRYABLE_OBSERVATION_CODES
    )
    return {
        "fingerprint": tool_call_fingerprint(reference, arguments),
        "retryable": retryable,
        "repeats": 0,
    }


def is_repeated_call(
    last_call: Any, reference: str, arguments: Mapping[str, Any]
) -> bool:
    return (
        isinstance(last_call, Mapping)
        and not last_call.get("retryable")
        and last_call.get("fingerprint") == tool_call_fingerprint(reference, arguments)
    )


def repeated_call_feedback(reference: str) -> str:
    return (
        f"Tool {reference} was just called with identical arguments and its "
        "observation is already above. No tool was executed again. Use that "
        "observation, change the arguments, choose another permitted tool, "
        "ask_user, or return final outputs."
    )


def final_turn_notice(max_turns: int) -> str:
    return (
        f"[Runtime budget] This is the last of {max_turns} model turns. A tool "
        "request now cannot be followed by another turn. Return final outputs "
        "from the evidence already observed, or ask_user if a required fact is "
        "missing."
    )
