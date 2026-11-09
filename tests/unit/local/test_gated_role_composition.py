"""Readonly production and scoped writing remain separated by real workflow gates."""

from dataclasses import replace
from typing import Any

import pytest

from veyra_agent_platform.contracts.task_structure import TaskStructure
from veyra_agent_platform.local.builder.generate_product import generate_builder_product
from veyra_agent_platform.local.builder.task_planner import required_task_duties
from veyra_agent_platform.local.builder.task_structure_schema import (
    task_structure_projection,
)
from veyra_agent_platform.local.resources import ResourceCatalog


def _task() -> TaskStructure:
    return TaskStructure.from_dict(
        {
            "schema_version": "1.0",
            "goal": "Execute the declared review and gated output method.",
            "summary": "Produce a readonly report, verify, then approve scoped writing",
            "actors": [
                {
                    "id": "reader",
                    "role": "reviewer",
                    "capabilities": ["text_generation", "workspace_read"],
                    "reason": "Inspect selected material without modifying it",
                    "inputs": [{"name": "material_path", "type": "string"}],
                    "outputs": [
                        {"name": "report_text", "type": "string"},
                        {"name": "report_path", "type": "string"},
                        {"name": "outcome", "type": "object"},
                    ],
                },
                {
                    "id": "writer",
                    "role": "writer",
                    "capabilities": ["text_generation", "workspace_write"],
                    "reason": "Write only the supplied approved report",
                    "inputs": [
                        {"name": "report_text", "type": "string"},
                        {"name": "report_path", "type": "string"},
                    ],
                    "outputs": [{"name": "saved_report", "type": "object"}],
                },
            ],
            "stages": [
                {
                    "id": "review",
                    "summary": "Read, inspect, and draft within one autonomous call",
                    "actor": "reader",
                    "input_sources": {"material_path": "input.material_path"},
                },
                {"id": "check", "summary": "Independently check the report is present"},
                {
                    "id": "approve",
                    "summary": "The user decides whether to save the report",
                },
                {
                    "id": "write",
                    "summary": "Save the approved report",
                    "actor": "writer",
                    "input_sources": {
                        "report_text": "review.report_text",
                        "report_path": "review.report_path",
                    },
                },
            ],
            "inputs": [{"name": "material_path", "type": "string"}],
            "outputs": [
                {
                    "name": "report_text",
                    "type": "string",
                    "source": "review.report_text",
                },
                {
                    "name": "saved_report",
                    "type": "object",
                    "source": "write.saved_report",
                },
            ],
            "execution_boundaries": [
                {
                    "kind": "tool",
                    "stage": "review",
                    "reason": "Read selected material",
                    "required": True,
                    "capability": "workspace_read",
                },
                {
                    "kind": "verification",
                    "stage": "check",
                    "reason": "Require actual report data before approval",
                    "required": True,
                    "checks": ["required_fields:report-text"],
                },
                {
                    "kind": "human_approval",
                    "stage": "approve",
                    "reason": "Ask before saving the proposed report",
                    "required": True,
                    "approval_class": "business",
                },
                {
                    "kind": "tool",
                    "stage": "write",
                    "reason": "Save only after approval",
                    "required": True,
                    "capability": "workspace_write",
                },
                {
                    "kind": "human_approval",
                    "stage": "write",
                    "reason": "Runtime must also authorize the exact file write",
                    "required": True,
                    "approval_class": "tool",
                },
            ],
            "lifecycle": {"persistent": False, "interaction": "multi_turn"},
            "orchestration_complexity": "multi_actor",
            "constraints": [
                "Do not modify original material",
                "Write only inside reports",
            ],
            "success_criteria": [
                "An independent check and user approval precede writing"
            ],
            "filesystem_write_roots": ["project/reports"],
        }
    )


class _Planner:
    def __init__(self, structure: TaskStructure) -> None:
        self.structure = structure

    def complete_json(self, prompt: str, schema: Any) -> dict[str, Any]:
        del prompt, schema
        return task_structure_projection(self.structure)


def _generate(structure: TaskStructure):
    return generate_builder_product(
        structure.goal, ResourceCatalog(), planner_provider=_Planner(structure)
    )


def _reachable(edges: list[dict[str, str]], start: str, target: str) -> bool:
    remaining = [start]
    seen = set()
    while remaining:
        current = remaining.pop()
        if current == target:
            return True
        if current in seen:
            continue
        seen.add(current)
        remaining.extend(edge["to"] for edge in edges if edge["from"] == current)
    return False


def test_gated_report_composes_real_ports_and_least_privilege_roles() -> None:
    product = _generate(_task())
    assert product.status == "review", product.diagnostics
    assert product.source is None and product.orchestration is not None
    assert (
        product.plan is not None
        and product.plan.product_shape == "MULTI_AGENT_WORKFLOW"
    )
    reader, writer = product.orchestration.companions
    assert reader.permissions.tools == ("veyra.tool.filesystem.read",)
    assert reader.permissions.filesystem_write_roots == ()
    assert "veyra.tool.filesystem.write@1.0.0" not in reader.lock
    assert writer.permissions.tools == ("veyra.tool.filesystem.write",)
    assert writer.permissions.filesystem_write_roots == ("project/reports",)
    assert writer.permissions.filesystem_read_roots == ()
    assert "veyra.tool.filesystem.read@1.0.0" not in writer.lock
    workflow = product.orchestration.workflow
    calls = {
        node["id"]: node
        for node in workflow["nodes"]
        if node["component_type"] == "AgentCall"
    }
    assert set(calls) == {"review", "write"}
    assert calls["review"]["agent_ref"].startswith(reader.agent_id + "@")
    assert calls["write"]["agent_ref"].startswith(writer.agent_id + "@")
    for port in ("report-text", "report-path"):
        produced = calls["review"]["output_mapping"][port]
        assert calls["write"]["input_mapping"][port] == produced
        assert port in reader.outputs and port in writer.inputs
    checks = [
        node for node in workflow["nodes"] if node["component_type"] == "Verifier"
    ]
    approvals = [
        node for node in workflow["nodes"] if node["component_type"] == "HumanApproval"
    ]
    assert len(checks) == 1 and checks[0]["checks"] == ["required_fields:report-text"]
    assert len(approvals) == 1 and approvals[0]["review"] == "approval"
    assert workflow["extensions"]["veyra"]["verification"]["required"] is True
    assert product.plan.shape.downgraded is False


def test_writer_is_only_reachable_after_passed_verification_and_approved_gate() -> None:
    product = _generate(_task())
    assert product.orchestration is not None, product.diagnostics
    workflow = product.orchestration.workflow
    edges = list(workflow["transitions"])
    check = next(
        node["id"] for node in workflow["nodes"] if node["component_type"] == "Verifier"
    )
    gate = next(
        node["id"]
        for node in workflow["nodes"]
        if node["component_type"] == "HumanApproval"
    )
    assert _reachable(edges, "start", "write")
    for boundary, port in ((check, "passed"), (gate, "approved")):
        without_grant = [
            edge
            for edge in edges
            if not (edge["from"] == boundary and edge["port"] == port)
        ]
        assert not _reachable(without_grant, "start", "write")
    for boundary, denied in ((check, "failed"), (gate, "rejected")):
        branch = next(
            edge["to"]
            for edge in edges
            if edge["from"] == boundary and edge["port"] == denied
        )
        assert not _reachable(edges, branch, "write")


def test_forcing_a_loop_cannot_publish_away_required_independent_gates() -> None:
    product = _generate(replace(_task(), user_shape_override="PURE_AGENT"))
    assert product.status == "review", product.diagnostics
    assert product.plan is not None and product.plan.shape.warnings
    assert product.plan.shape.downgraded is False
    assert product.source is None and product.orchestration is not None
    kinds = {node["component_type"] for node in product.orchestration.workflow["nodes"]}
    assert {"Verifier", "HumanApproval"} <= kinds


def test_binding_correction_preserves_the_same_user_check_duty() -> None:
    original = _task()
    boundaries = tuple(
        replace(boundary, checks=("required_fields:review.report_text",))
        if boundary.kind == "verification"
        else boundary
        for boundary in original.execution_boundaries
    )
    corrected = replace(original, execution_boundaries=boundaries)
    assert not required_task_duties(original) - required_task_duties(corrected)
    product = _generate(corrected)
    assert product.status == "review", product.diagnostics
    assert product.orchestration is not None
    verifier = next(
        node
        for node in product.orchestration.workflow["nodes"]
        if node["component_type"] == "Verifier"
    )
    assert verifier["input_mapping"]["report-text"] == "review_report_text"


@pytest.mark.parametrize(
    "reference,diagnostic",
    [
        ("review.unannounced", "undeclared output"),
        ("write.saved_report", "unavailable stage"),
    ],
)
def test_bad_stage_ports_are_rejected_before_a_candidate_is_composed(
    reference: str, diagnostic: str
) -> None:
    task = _task()
    stages = list(task.stages)
    target = 3 if reference.startswith("review.") else 0
    name = "report_text" if target == 3 else "material_path"
    stages[target] = replace(
        stages[target],
        input_sources={**(stages[target].input_sources or {}), name: reference},
    )
    product = _generate(replace(task, stages=tuple(stages)))
    assert product.status == "blocked"
    assert product.source is None and product.orchestration is None
    assert any(diagnostic in issue for issue in product.diagnostics), (
        product.diagnostics
    )
