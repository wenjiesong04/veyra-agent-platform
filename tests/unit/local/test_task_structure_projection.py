"""Server-owned TaskStructure repairs use the same closed shape as initial plans."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator

from veyra_agent_platform.contracts.task_structure import TaskStructure
from veyra_agent_platform.local.builder.task_structure_schema import (
    complete_task_io_metadata,
    task_structure_json_intake_schema,
    task_structure_payload,
    task_structure_projection,
    task_structure_schema,
)


def test_intake_defaults_preserve_explicit_io_values() -> None:
    payload = {
        "inputs": [
            {
                "name": "files",
                "type": "file",
                "multiple": True,
                "required": False,
                "source": "input.files",
            }
        ],
        "outputs": [],
        "actors": [],
    }
    completed = complete_task_io_metadata(payload)
    assert completed["inputs"][0] == {
        "name": "files",
        "type": "file",
        "multiple": True,
        "required": False,
        "cardinality": "multiple",
        "description": "",
        "source": "input.files",
    }
    assert payload["inputs"][0].get("cardinality") is None


def test_json_intake_does_not_default_names_types_or_invalid_metadata() -> None:
    from jsonschema import Draft202012Validator

    schema = task_structure_json_intake_schema(task_structure_schema())
    io_schema = schema["properties"]["inputs"]["items"]
    validator = Draft202012Validator(io_schema)
    assert validator.is_valid({"name": "file", "type": "file"})
    for invalid in [
        {"type": "file"},
        {"name": "file"},
        {"name": "file", "type": "file", "required": "false"},
        {"name": "file", "type": "file", "multiple": 1},
        {"name": "file", "type": "file", "$ref": "invented"},
        {"name": "file", "type": "file", "cardinality": "unbounded"},
    ]:
        assert not validator.is_valid(invalid)


def test_typed_condition_intake_compiles_without_changing_legacy_task_contract() -> (
    None
):
    from veyra_agent_platform.contracts.condition import parse_condition_expression

    payload = {
        "execution_boundaries": [
            {
                "kind": "condition",
                "expression": {
                    "path": "confirm.approved",
                    "operator": "==",
                    "literal": True,
                },
            }
        ]
    }
    original = deepcopy(payload)
    converted = task_structure_payload(payload)
    expression = converted["execution_boundaries"][0]["expression"]
    assert expression == "confirm.approved == true"
    assert parse_condition_expression(expression).evaluate(
        {"confirm": {"approved": True}}
    )
    assert payload == original
    legacy = {
        "execution_boundaries": [
            {"kind": "condition", "expression": "approved == true"}
        ]
    }
    assert task_structure_payload(legacy) == legacy


def test_condition_intake_rejects_length_before_legacy_clipping_changes_meaning() -> (
    None
):
    from veyra_agent_platform.contracts.condition import ConditionValidationError

    with pytest.raises(ConditionValidationError, match="expression_too_long"):
        task_structure_payload(
            {
                "execution_boundaries": [
                    {
                        "kind": "condition",
                        "expression": {
                            "path": "request",
                            "operator": "==",
                            "literal": "x" * 240,
                        },
                    }
                ]
            }
        )


def test_condition_duty_identity_uses_semantics_instead_of_legacy_quote_style() -> None:
    from veyra_agent_platform.contracts.task_structure import ExecutionBoundary
    from veyra_agent_platform.local.builder.task_planner import required_task_duties

    condition = ExecutionBoundary(
        kind="condition",
        stage="route",
        reason="Route on the declared decision",
        required=True,
        expression="choose.selection == 'continue'",
        branches=("continue", "stop"),
        source="Use the recorded choice",
    )
    legacy = replace(_task(), execution_boundaries=(condition,))
    canonical = replace(
        legacy,
        execution_boundaries=(
            replace(condition, expression='choose.selection == "continue"'),
        ),
    )
    assert required_task_duties(legacy) == required_task_duties(canonical)
    changed = replace(
        legacy,
        execution_boundaries=(
            replace(condition, expression='choose.selection == "stop"'),
        ),
    )
    assert required_task_duties(legacy) != required_task_duties(changed)


def test_mfjs_projection_preserves_typed_condition_and_existing_string_contract() -> (
    None
):
    from veyra_agent_platform.local.factory.structured_schema import (
        project_moonshot_json_schema,
    )

    schema = project_moonshot_json_schema(task_structure_schema())
    condition_schema = schema["properties"]["execution_boundaries"]["items"][
        "properties"
    ]["expression"]
    validator = Draft202012Validator(condition_schema)
    for expression in [
        "",
        'decision == "continue"',
        {"path": "confirmation.approved", "operator": "==", "literal": True},
        {"path": "check.result.score", "operator": ">=", "literal": 0.00001},
        {"path": "check.result.tags", "operator": "contains", "literal": "review"},
    ]:
        validator.validate(expression)
    assert not validator.is_valid(None)
    assert not validator.is_valid(
        {"path": "decision", "operator": "matches", "literal": "continue"}
    )
    dumped = json.dumps(condition_schema)
    assert '"oneOf"' not in dumped and '"$ref"' not in dumped
    assert condition_schema["anyOf"][1]["properties"]["operator"]["type"] == "string"


def _task() -> TaskStructure:
    return TaskStructure.from_dict(
        {
            "schema_version": "1.0",
            "goal": "按提供的文件复核待办，确认后仅在 reports 中保存结果。",
            "summary": "Retain source evidence, update tasks, and ask before saving",
            "actors": [
                {
                    "id": "reviewer",
                    "role": "reviewer",
                    "capabilities": ["text_generation", "document_analysis"],
                    "inputs": [
                        {
                            "name": "materials",
                            "type": "file",
                            "multiple": True,
                            "required": True,
                            "cardinality": "multiple",
                            "description": "用户提供的待办资料",
                            "source": "input.materials",
                        },
                        {"name": "note", "type": "string", "required": False},
                    ],
                    "outputs": [{"name": "report", "type": "object"}],
                }
            ],
            "stages": [
                {
                    "id": "review",
                    "summary": "Review source evidence",
                    "actor": "reviewer",
                    "input_sources": {"materials": "input.materials"},
                },
                {"id": "confirm", "summary": "Confirm before saving"},
            ],
            "entities": ["task"],
            "inputs": [{"name": "materials", "type": "file", "multiple": True}],
            "outputs": [{"name": "report", "type": "object"}],
            "execution_boundaries": [
                {
                    "kind": "human_input",
                    "stage": "confirm",
                    "reason": "The user approves the proposed task updates",
                    "required": True,
                    "question": "确认这些修改并保存报告吗？",
                    "scope": "run",
                    "source": "user confirmation",
                    "expected_schema": {"approved": "boolean", "note": "string"},
                },
                {
                    "kind": "human_approval",
                    "stage": "confirm",
                    "reason": "Approve the report file write",
                    "required": True,
                    "approval_class": "tool",
                },
            ],
            "lifecycle": {
                "persistent": True,
                "interaction": "persistent_task",
                "entity": "task",
            },
            "state": {
                "entity": "task",
                "identity": "task_key",
                "scope": "project",
                "fields": {
                    "task_key": "string",
                    "owner": "string",
                    "status": "string",
                    "evidence": "artifact",
                },
                "statuses": ["open", "done"],
                "revision": True,
            },
            "orchestration_complexity": "single",
            "constraints": ["Original inputs are read-only"],
            "success_criteria": ["Retain stable task IDs and source evidence"],
            "skill_choices": [
                {
                    "actor": "reviewer",
                    "capability": "document_analysis",
                    "reference": "veyra.skill.document-analyzer@1.0.0",
                    "reason": "Use the exact selected document method",
                }
            ],
            "filesystem_write_roots": ["project/reports"],
        }
    )


def test_closed_projection_preserves_actor_io_gates_state_method_and_scope() -> None:
    structure = _task()
    canonical_before = structure.to_dict()
    projected = task_structure_projection(structure)
    Draft202012Validator(task_structure_schema()).validate(projected)
    restored = TaskStructure.from_dict(
        task_structure_payload(json.loads(json.dumps(projected)))
    )
    assert restored.to_dict() == canonical_before
    assert structure.to_dict() == canonical_before
    actor = projected["actors"][0]
    assert actor["inputs"][0]["type"] == "file"
    assert actor["inputs"][0]["multiple"] is True
    assert actor["inputs"][0]["source"] == "input.materials"
    assert actor["inputs"][1]["required"] is False
    assert actor["inputs"][1]["description"] == ""
    assert actor["inputs"][1]["source"] == ""
    assert projected["stages"][0]["input_sources"] == [
        {"input": "materials", "source": "input.materials"}
    ]
    assert projected["execution_boundaries"][0]["expected_schema"] == [
        {"name": "approved", "type": "boolean"},
        {"name": "note", "type": "string"},
    ]
    assert projected["execution_boundaries"][1]["approval_class"] == "tool"
    assert projected["state"]["identity"] == "task_key"
    assert projected["state"]["revision"] is True
    assert restored.skill_choices == structure.skill_choices
    assert restored.filesystem_write_roots == ("project/reports",)


def test_projection_emits_empty_wire_members_without_inventing_new_semantics() -> None:
    structure = TaskStructure.from_dict(
        {
            "schema_version": "1.0",
            "goal": "Translate",
            "summary": "Translate supplied text",
            "actors": [{"id": "translator", "role": "translator"}],
            "inputs": [{"name": "text", "type": "string"}],
            "outputs": [{"name": "translation", "type": "string"}],
            "lifecycle": {"persistent": False, "interaction": "single_run"},
        }
    )
    projected = task_structure_projection(structure)
    Draft202012Validator(task_structure_schema()).validate(projected)
    assert projected["actors"][0]["inputs"] == []
    assert projected["actors"][0]["outputs"] == []
    assert projected["actors"][0]["reason"] == ""
    assert projected["lifecycle"]["entity"] == ""
    assert projected["state"] is None
    assert projected["skill_choices"] == []
    assert projected["filesystem_write_roots"] == []
    assert (
        TaskStructure.from_dict(task_structure_payload(projected)).to_dict()
        == structure.to_dict()
    )


def test_projection_does_not_truncate_identity_to_make_provider_validation_pass() -> (
    None
):
    structure = _task()
    identity = "reviewer_" + "a" * 65
    structure = replace(
        structure,
        actors=(replace(structure.actors[0], id=identity),),
        skill_choices=(replace(structure.skill_choices[0], actor=identity),),
        stages=tuple(
            replace(stage, actor=identity) if stage.actor == "reviewer" else stage
            for stage in structure.stages
        ),
    )
    projected = task_structure_projection(structure)
    assert projected["actors"][0]["id"] == identity
    errors = list(Draft202012Validator(task_structure_schema()).iter_errors(projected))
    assert any(
        error.json_path == "$.actors[0].id" and error.validator == "maxLength"
        for error in errors
    )


def test_projection_rejects_a_raw_provider_placeholder() -> None:
    invalid = deepcopy(task_structure_projection(_task()))
    invalid["actors"][0]["inputs"][0] = {"$ref": "#/inputs/0"}
    with pytest.raises(TypeError, match="server-owned TaskStructure"):
        task_structure_projection(invalid)
    errors = list(Draft202012Validator(task_structure_schema()).iter_errors(invalid))
    assert any(
        error.json_path == "$.actors[0].inputs[0]" and error.validator == "required"
        for error in errors
    )
