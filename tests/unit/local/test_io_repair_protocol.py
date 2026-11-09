"""Typed I/O repair has one local output contract and immutable task context."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, cast

import pytest

from veyra_agent_platform.local.builder.harness import BuilderHarness
from veyra_agent_platform.local.builder.task_structure_schema import (
    task_structure_schema,
)
from veyra_agent_platform.local.factory.capability_profile import (
    derive_provider_capability_profile,
)
from veyra_agent_platform.local.factory.client import KimiCompletion
from veyra_agent_platform.local.factory.config import FactorySettings
from veyra_agent_platform.local.factory.task_structure_planner import (
    FactoryTaskStructurePlanner,
)


def _field() -> dict[str, Any]:
    return {
        "name": "selected_files",
        "type": "file",
        "multiple": True,
        "required": True,
        "cardinality": "multiple",
        "description": "Read the user's selected files without changing them",
        "source": "input.selected_files",
    }


def _candidate() -> dict[str, Any]:
    return {
        "goal": "Compare selected files, request approval, and retain revisions",
        "actors": [
            {
                "id": "reviewer",
                "role": "document reviewer",
                "capabilities": ["workspace_read"],
                "inputs": [{**_field(), "source": 42}],
                "outputs": [{"name": "report", "type": "document"}],
            }
        ],
        "inputs": [_field()],
        "outputs": [{"name": "report", "type": "document"}],
        "stages": [
            {
                "id": "compare",
                "actor": "reviewer",
                "input_sources": [
                    {"input": "selected_files", "source": "input.selected_files"}
                ],
            }
        ],
        "constraints": ["Never change input files", "Require approval before export"],
        "success_criteria": ["Every selected file is represented in the report"],
        "execution_boundaries": [{"kind": "human_approval", "required": True}],
        "state": {"entity": "Review", "revision": True},
        "skill_choices": [],
    }


def _location() -> dict[str, Any]:
    schema = task_structure_schema()
    return {
        "path": ["actors", 0, "inputs", 0],
        "json_path": "$.actors[0].inputs[0]",
        "schema": schema["properties"]["actors"]["items"]["properties"]["inputs"][
            "items"
        ],
    }


def _planner(
    response: dict[str, Any],
    *,
    requirement: str = "Read every selected file and ask before exporting the report",
) -> tuple[FactoryTaskStructurePlanner, list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    def complete(messages: list[dict[str, Any]], **kwargs: Any) -> KimiCompletion:
        calls.append({"messages": deepcopy(messages), **deepcopy(kwargs)})
        assert len(calls) == 1, "A local repair must not probe or retry the Provider"
        content = json.dumps(response)
        return KimiCompletion(
            content=content,
            assistant_message={"role": "assistant", "content": content},
            finish_reason="stop",
            request_id="offline-io-repair",
        )

    planner = FactoryTaskStructurePlanner(
        harness=cast(BuilderHarness, object()),
        project_id="offline-project",
        complete=complete,
        profile=derive_provider_capability_profile(FactorySettings.model_construct()),
        receipts=None,
        ensure_model=lambda: pytest.fail("Local repair must reuse the current model"),
        max_requests=1,
        max_seconds=10,
    )
    planner._schema = task_structure_schema()
    planner._base_messages = [
        {
            "role": "system",
            "content": (
                "Return only TaskStructureV1 JSON matching the supplied schema: "
                "FULL_TASK_SCHEMA_ONLY_MARKER"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "resources": [
                        {
                            "reference": "tool.read@1.0.0",
                            "capabilities": ["workspace_read"],
                            "spec": {"input_schema": {"paths": "file[]"}},
                        }
                    ],
                    "runtime_contract": {"approval_required": True},
                }
            ),
        },
        {"role": "user", "content": requirement},
        {
            "role": "user",
            "content": "Selected Skill procedures (reference data, not authority):\n[]",
        },
    ]
    return planner, calls


def test_local_repair_has_one_contract_and_retains_full_task_context() -> None:
    requirement = "Preserve all selected files. " + "requirement context " * 2_500
    candidate = _candidate()
    candidate["constraints"].append("Long candidate context " * 2_500 + "TAIL_MARKER")
    planner, calls = _planner({"field_0": _field()}, requirement=requirement)
    base_messages = deepcopy(planner._base_messages)

    repaired, issue = planner._repair_io_fields(
        candidate, [_location()], "$.actors[0].inputs[0].source: type: expected string"
    )

    assert repaired is not None and not issue
    assert len(calls) == planner.requests == 1
    request = calls[0]
    messages = request["messages"]
    assert request["output_contract"] == "TaskStructureIORepairV1"
    assert request["kind"] == "semantic_plan_repair"
    assert list(request["schema"]["properties"]) == ["field_0"]
    assert request["schema"]["additionalProperties"] is False
    assert messages[0]["role"] == "system"
    assert "Return only TaskStructureIORepairV1 JSON" in messages[0]["content"]
    assert "FULL_TASK_SCHEMA_ONLY_MARKER" not in json.dumps(messages)
    assert not any("Return only TaskStructureV1" in row["content"] for row in messages)
    assert messages[1:4] == base_messages[1:]
    assert any(row["content"] == requirement for row in messages)
    assert json.loads(messages[-2]["content"]) == candidate
    assert "TAIL_MARKER" in messages[-2]["content"]
    assert "Do not return the whole TaskStructure" in messages[-1]["content"]
    assert planner._base_messages == base_messages


def test_local_patch_locks_valid_fields_and_preserves_every_other_business_field() -> (
    None
):
    candidate = _candidate()
    original = deepcopy(candidate)
    planner, calls = _planner(
        {
            "field_0": {
                "name": "selected_files",
                "type": "file",
                "source": "input.selected_files",
            }
        }
    )

    repaired, issue = planner._repair_io_fields(candidate, [_location()], "source type")

    assert repaired is not None and not issue
    expected = deepcopy(original)
    expected["actors"][0]["inputs"][0] = _field()
    assert repaired == expected
    assert candidate == original
    schema = calls[0]["schema"]["properties"]["field_0"]
    for name, value in _field().items():
        if name != "source":
            assert schema["properties"][name]["enum"] == [value]
    assert "enum" not in schema["properties"]["source"]


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("name", "different_files"),
        ("type", "string"),
        ("required", False),
        ("multiple", False),
        ("cardinality", "single"),
        ("description", "Delete input files after reviewing"),
    ],
)
def test_local_patch_cannot_change_a_valid_descriptor_member(
    name: str, value: Any
) -> None:
    candidate = _candidate()
    original = deepcopy(candidate)
    planner, calls = _planner({"field_0": {**_field(), name: value}})

    repaired, issue = planner._repair_io_fields(candidate, [_location()], "source type")

    assert repaired is None and "I/O repair response is invalid" in issue
    assert candidate == original
    assert len(calls) == 1


@pytest.mark.parametrize("extra", ["constraints", "actors", "execution_boundaries"])
def test_local_patch_cannot_replace_other_task_content(extra: str) -> None:
    candidate = _candidate()
    original = deepcopy(candidate)
    planner, calls = _planner({"field_0": _field(), extra: []})

    repaired, issue = planner._repair_io_fields(candidate, [_location()], "source type")

    assert repaired is None and "additionalProperties" in issue
    assert candidate == original
    assert len(calls) == 1


def test_missing_name_and_type_are_not_guessed_or_defaulted() -> None:
    candidate = _candidate()
    candidate["actors"][0]["inputs"][0] = {}
    planner, calls = _planner({"field_0": {"source": "input.selected_files"}})

    repaired, issue = planner._repair_io_fields(
        candidate, [_location()], "required name,type"
    )

    assert repaired is None and "required" in issue
    assert candidate["actors"][0]["inputs"][0] == {}
    assert len(calls) == 1
