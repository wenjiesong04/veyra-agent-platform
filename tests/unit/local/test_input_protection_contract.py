"""Opt-in input policies survive planning and preserve legacy source pins."""

from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator

from tests.unit.local.test_gated_role_composition import _generate, _task
from veyra_agent_platform.contracts.agent import PermissionContract
from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.task_structure import TaskStructure
from veyra_agent_platform.contracts.typed_io import parse_typed_field
from veyra_agent_platform.local.builder.task_structure_schema import (
    task_structure_json_intake_schema,
    task_structure_projection,
    task_structure_schema,
)


def test_default_permission_serialization_does_not_change_legacy_hash_payload() -> None:
    legacy = PermissionContract.from_dict({"tools": [], "network_hosts": []})
    payload = legacy.to_dict()
    assert "protect_input_files" not in payload
    assert "protected_input_fields" not in payload
    assert PermissionContract.from_dict(payload).to_dict() == payload


def test_protected_inputs_require_opt_in_and_actual_declared_file_fields() -> None:
    with pytest.raises(ContractValidationError, match="requires"):
        PermissionContract.from_dict(
            {"tools": [], "network_hosts": [], "protected_input_fields": ["path"]}
        )
    policy = PermissionContract.from_dict(
        {
            "tools": [],
            "network_hosts": [],
            "protect_input_files": True,
            "protected_input_fields": ["path"],
        }
    )
    policy.validate_input_fields({"path": parse_typed_field("string", "path")})
    policy.validate_input_fields(
        {"path": parse_typed_field({"type": "file", "multiple": True}, "path")}
    )
    for fields in [
        {},
        {"path": parse_typed_field("object", "path")},
        {"path": parse_typed_field({"type": "string", "multiple": True}, "path")},
    ]:
        with pytest.raises(ContractValidationError):
            policy.validate_input_fields(fields)


def test_task_projection_retains_opt_in_and_legacy_intake_defaults() -> None:
    task = replace(
        _task(), protect_input_files=True, protected_input_fields=("material_path",)
    )
    projection = task_structure_projection(task)
    assert Draft202012Validator(task_structure_schema()).is_valid(projection)
    assert TaskStructure.from_dict(task.to_dict()).protect_input_files
    assert projection["protected_input_fields"] == ["material_path"]
    projection.pop("protect_input_files")
    projection.pop("protected_input_fields")
    assert Draft202012Validator(
        task_structure_json_intake_schema(task_structure_schema())
    ).is_valid(projection)


def test_generated_workflow_owns_one_input_policy_and_all_roles_inherit_it() -> None:
    task = replace(
        _task(), protect_input_files=True, protected_input_fields=("material_path",)
    )
    product = _generate(task)
    assert product.orchestration is not None, product.diagnostics
    policy = product.orchestration.workflow["extensions"]["veyra"]["permissions"]
    assert policy["protect_input_files"] is True
    assert policy["protected_input_fields"] == ["materialpath"]
    assert all(
        role.permissions.protect_input_files
        for role in product.orchestration.companions
    )
    assert all(
        not role.permissions.protected_input_fields
        for role in product.orchestration.companions
    )
