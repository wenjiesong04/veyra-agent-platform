"""User-requested surface is a preference. Product shape is decided later."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from veyra_agent_platform.local.builder.task_planner import user_requested_surface

CreateKind = Literal["agent", "workflow"]

_FORCE_AGENT = re.compile(
    r"不要\s*workflow|就做一个简单\s*agent|只要(一个)?\s*agent",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BuilderTargetClassification:
    create_kind: CreateKind
    confidence: Literal["high", "medium"]
    reason: str
    recommendation: str
    message_zh: str
    message_en: str
    user_requested_surface: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "create_kind": self.create_kind,
            "confidence": self.confidence,
            "reason": self.reason,
            "recommendation": self.recommendation,
            "message_zh": self.message_zh,
            "message_en": self.message_en,
            "user_requested_surface": self.user_requested_surface,
        }


def classify_builder_target(text: str) -> BuilderTargetClassification:
    """Record how the user named the product. Never lock Agent vs Workflow."""

    raw = " ".join(text.split()).strip()
    surface = user_requested_surface(raw)
    if _FORCE_AGENT.search(raw):
        surface = "agent"
    if surface == "workflow":
        return BuilderTargetClassification(
            create_kind="workflow",
            confidence="medium",
            reason="The user named a process; shape is still decided by TaskStructure.",
            recommendation="workflow",
            message_zh="我会先理解任务结构，再决定是 Agent、Workflow 还是组合。",
            message_en=(
                "I'll understand the task structure before choosing "
                "Agent, Workflow, or both."
            ),
            user_requested_surface="workflow",
        )
    return BuilderTargetClassification(
        create_kind="agent",
        confidence="medium",
        reason="The user named an Agent or did not name a process. Preference only.",
        recommendation="agent",
        message_zh="我会先理解任务结构，再决定产品形态。",
        message_en=(
            "I'll understand the task structure before choosing a product shape."
        ),
        user_requested_surface=surface or "agent",
    )
