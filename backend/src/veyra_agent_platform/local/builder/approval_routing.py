"""Recognize approval control predicates without inventing data outputs."""

from __future__ import annotations

from dataclasses import dataclass

from veyra_agent_platform.contracts.condition import parse_condition_expression
from veyra_agent_platform.contracts.task_structure import (
    ExecutionBoundary,
    TaskStructure,
)

from .product_shape import stage_key


@dataclass(frozen=True)
class ApprovalOutcome:
    true_means_approved: bool


def approval_outcome(
    structure: TaskStructure, boundary: ExecutionBoundary
) -> ApprovalOutcome | None:
    if boundary.kind != "condition":
        return None
    stage = next(
        (
            item
            for item in structure.stages
            if stage_key(item.id) == stage_key(boundary.stage)
        ),
        None,
    )
    if stage is None or stage.actor:
        return None
    matching = [
        item
        for item in structure.execution_boundaries
        if stage_key(item.stage) == stage_key(stage.id)
    ]
    approvals = [
        item
        for item in matching
        if item.kind == "human_approval" and item.approval_class != "tool"
    ]
    if len(approvals) != 1 or any(item.kind == "human_input" for item in matching):
        return None
    predicate = parse_condition_expression(boundary.expression)
    path = predicate.path
    if (
        len(path) != 2
        or stage_key(path[0]) != stage_key(stage.id)
        or path[1] not in {"approved", "rejected"}
        or predicate.operator not in {"==", "!="}
        or type(predicate.literal) is not bool
    ):
        return None
    when_approved = path[1] == "approved"
    truth = when_approved == predicate.literal
    if predicate.operator == "!=":
        truth = not truth
    return ApprovalOutcome(true_means_approved=truth)
