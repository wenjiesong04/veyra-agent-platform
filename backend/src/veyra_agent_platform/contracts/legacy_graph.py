"""Classify historical graph Agents without migrating them."""

from __future__ import annotations

from typing import Literal

from .agent import AgentSource, ComponentType

LegacyGraphClass = Literal[
    "loop_agent",
    "simple_graph_loop_candidate",
    "multi_model_graph_candidate",
    "orchestration_workflow_candidate",
    "legacy_graph",
]

_ORCHESTRATION = frozenset(
    {
        ComponentType.CONDITION,
        ComponentType.HUMAN_APPROVAL,
        ComponentType.TRANSFORM,
        ComponentType.VERIFIER,
        ComponentType.AGENT_CALL,
    }
)
_MODEL_LIKE = frozenset({ComponentType.AGENT, ComponentType.MODEL})
_SIMPLE = frozenset(
    {
        ComponentType.START,
        ComponentType.OUTPUT,
        ComponentType.AGENT,
        ComponentType.MODEL,
        ComponentType.TOOL,
        ComponentType.CUSTOM_COMPONENT,
    }
)


def classify_legacy_graph_agent(source: AgentSource) -> LegacyGraphClass:
    """Deterministic product-class for an existing Agent source.

    This never rewrites source. Loop Agents stay loop Agents. Historical Flow
    graphs stay openable as graph Agents until an explicit migration runs.
    """

    if source.execution_kind == "loop":
        return "loop_agent"
    types = {node.component_type for node in source.nodes}
    if types & _ORCHESTRATION:
        return "orchestration_workflow_candidate"
    if not types <= _SIMPLE:
        return "legacy_graph"
    model_count = sum(1 for node in source.nodes if node.component_type in _MODEL_LIKE)
    if model_count == 1:
        return "simple_graph_loop_candidate"
    if model_count > 1:
        return "multi_model_graph_candidate"
    return "legacy_graph"


def legacy_graph_migration_plan(source: AgentSource) -> dict[str, str]:
    classification = classify_legacy_graph_agent(source)
    if classification == "loop_agent":
        action = "keep"
        reason = "Already a loop Agent."
    elif classification == "simple_graph_loop_candidate":
        action = "convert_to_loop_agent"
        reason = (
            "Start → Model → Output can become an Agent loop without changing behavior."
        )
    elif classification == "orchestration_workflow_candidate":
        action = "convert_to_workflow"
        reason = "Condition, approval, or multi-stage control flow belongs to Workflow."
    elif classification == "multi_model_graph_candidate":
        action = "convert_to_workflow"
        reason = "Multiple Model stages are explicit orchestration."
    else:
        action = "keep_as_legacy_graph"
        reason = "Keep the historical graph Agent readable; do not silent-migrate."
    return {
        "agent_id": source.agent_id,
        "slug": source.slug,
        "classification": classification,
        "action": action,
        "reason": reason,
        "silent_migrate": "false",
    }
