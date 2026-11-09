"""Model-turn accounting and host admission policy, not Tool authorization."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

DEFAULT_TOTAL_MODEL_TURNS = 512
DEFAULT_ADDITIONAL_MODEL_TURNS = 64


@dataclass
class ModelTurnBudget:
    original_limit: int
    used: int
    limit: int
    total_limit: int = DEFAULT_TOTAL_MODEL_TURNS
    extension_limit: int = DEFAULT_ADDITIONAL_MODEL_TURNS

    @classmethod
    def restore(
        cls, initial: int, state: Mapping[str, Any], settings: Any = None
    ) -> ModelTurnBudget:
        total = getattr(settings, "max_total_model_turns", DEFAULT_TOTAL_MODEL_TURNS)
        extension = getattr(
            settings, "max_additional_model_turns", DEFAULT_ADDITIONAL_MODEL_TURNS
        )
        stored = state.get("budget")
        if isinstance(stored, Mapping):
            used, limit = stored.get("used"), stored.get("limit")
            if stored.get("original_limit") != initial:
                raise ValueError("The saved budget belongs to a different Source")
        else:
            used = int(state.get("turn") or 0)
            if state.get("pending_tool"):
                used += 1
            limit = initial
        if (
            type(used) is not int
            or type(limit) is not int
            or not 0 <= used <= limit
            or not initial <= limit <= total
        ):
            raise ValueError("The saved budget is outside the current host policy")
        return cls(initial, used, limit, total, extension)

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    def consume(self) -> None:
        if not self.remaining:
            raise ValueError("No authorized model turn remains")
        self.used += 1

    def extend(self, additional: int) -> None:
        if (
            type(additional) is not int
            or not 1 <= additional <= self.extension_limit
            or self.limit + additional > self.total_limit
        ):
            raise ValueError("Additional turns exceed the current host policy")
        self.limit += additional

    def snapshot(self) -> dict[str, Any]:
        return {
            "scope": "run_model_turns",
            "limit": self.limit,
            "used": self.used,
            "remaining": self.remaining,
        }

    def state(self) -> dict[str, int]:
        return {
            "original_limit": self.original_limit,
            "used": self.used,
            "limit": self.limit,
        }

    def waiting_context(self, required: int, phase: str) -> dict[str, Any]:
        available = min(self.extension_limit, self.total_limit - self.limit)
        return {
            "budget": self.snapshot(),
            "phase": phase,
            "required_remaining": required,
            "max_additional_turns": available,
            "minimum_additional_turns": max(1, required - self.remaining),
            "suggested_additional_turns": min(
                available, max(self.original_limit, required - self.remaining)
            ),
            "total_model_turn_limit": self.total_limit,
        }
