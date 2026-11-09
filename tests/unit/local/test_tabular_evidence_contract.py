"""Public CSV evidence contracts match native facts and preserve existing pins."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from tests.unit.local.test_arithmetic_tool import _source
from tests.unit.local.test_semantic_composition import Planner, field
from veyra_agent_platform.contracts.agent import ComponentType
from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.local.builder.generate_product import generate_builder_product
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.agent_loop import _tool_descriptor
from veyra_agent_platform.local.runtime.tool_output_contract import (
    ToolOutputContractError,
    prepare_tool_output_contract,
    verify_tool_output_contract,
)
from veyra_agent_platform.local.runtime.tools import (
    ToolExecution,
    ToolRuntime,
    ToolRuntimeError,
)


def _case(tmp_path: Path):
    catalog = ResourceCatalog()
    resource = catalog.detail("veyra.tool.tabular.compare", "1.2.0")
    source = _source(resource)
    source = replace(
        source,
        permissions=replace(source.permissions, filesystem_read_roots=("project",)),
    )
    node = next(
        item for item in source.nodes if item.component_type is ComponentType.TOOL
    )
    (tmp_path / "left.csv").write_bytes(
        b'key,amount,note\na,0.1,"line one\nline two"\na,0.2,x\n,2,y\n'
    )
    (tmp_path / "right.csv").write_bytes(b"key,amount\na,0.3\nb,5\n")
    arguments = {
        "left_source": {"path": "left.csv"},
        "right_source": {"path": "right.csv"},
        "left_key": "key",
        "right_key": "key",
        "left_amount": "amount",
        "right_amount": "amount",
        "include_all_groups": True,
    }
    return catalog, resource, source, node, arguments


def _execute(runtime, source, node, arguments, tmp_path):
    authorization = runtime.authorize(source=source, node=node, values=arguments)
    assert authorization.decision == "allowed"
    return runtime.execute(
        project_root=tmp_path,
        source=source,
        node=node,
        values=arguments,
        authorization=authorization,
        approved=False,
    )


def test_native_result_and_public_contract_include_real_source_and_row_evidence(
    tmp_path: Path,
) -> None:
    catalog, resource, source, node, arguments = _case(tmp_path)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    execution = _execute(ToolRuntime(catalog), source, node, arguments, tmp_path)
    result = execution.output
    group = next(item for item in result["groups"] if item["key"] == "a")
    assert group["left_rows"] == [
        {"line_start": 2, "line_end": 3, "amount": "0.1"},
        {"line_start": 4, "line_end": 4, "amount": "0.2"},
    ]
    assert group["difference"] == "0"
    assert result["totals"]["left_all"] == "2.3"
    assert result["totals"]["right_all"] == "5.3"
    assert result["blank_keys"]["left"] == [
        {"line_start": 5, "line_end": 5, "amount": "2"}
    ]
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before
    contract = prepare_tool_output_contract(resource["spec"])
    assert execution.receipt["output_verification"] == {
        "method": "json_schema",
        "schema_hash": sha256_digest(contract),
        "status": "passed",
    }
    public = _tool_descriptor(resource)
    assert public["output_validation"] is True
    rows = public["output_schema"]["properties"]["groups"]["items"]["properties"][
        "left_rows"
    ]
    assert set(rows["items"]["required"]) == {"line_start", "line_end", "amount"}


@pytest.mark.parametrize(
    "defect",
    ["row", "amount", "source_hash", "count", "complete", "truncation", "total"],
)
def test_result_contract_rejects_missing_or_incompatible_evidence(
    tmp_path: Path, defect: str
) -> None:
    catalog, resource, source, node, arguments = _case(tmp_path)
    result = deepcopy(
        _execute(ToolRuntime(catalog), source, node, arguments, tmp_path).output
    )
    group = next(item for item in result["groups"] if item["key"] == "a")
    if defect == "row":
        del group["left_rows"][0]["line_start"]
    elif defect == "amount":
        group["left_rows"][0]["amount"] = 0.1
    elif defect == "source_hash":
        result["left"]["sha256"] = "private-invalid-evidence"
    elif defect == "count":
        result["counts"]["matched_groups"] = -1
    elif defect == "complete":
        result["summary_complete"] = False
    elif defect == "truncation":
        result["groups_truncated"] = "false"
    elif defect == "total":
        del result["totals"]["left_all"]
    with pytest.raises(ToolOutputContractError) as caught:
        verify_tool_output_contract(
            prepare_tool_output_contract(resource["spec"]), result
        )
    assert caught.value.code == "tool_output_invalid"
    assert caught.value.verification["status"] == "failed"
    assert "private-invalid-evidence" not in str(caught.value)


def test_invalid_adapter_result_keeps_failed_contract_receipt_and_is_not_retried(
    tmp_path: Path,
) -> None:
    catalog, resource, source, node, arguments = _case(tmp_path)
    actual = _execute(ToolRuntime(catalog), source, node, arguments, tmp_path)
    wrong = deepcopy(actual.output)
    wrong["left"]["sha256"] = "private-invalid-evidence"
    calls = []

    def adapter(**kwargs):
        calls.append(kwargs)
        return ToolExecution(
            output=wrong,
            receipt={**actual.receipt, "output_digest": sha256_digest(wrong)},
        )

    runtime = ToolRuntime(catalog, adapters={resource["spec"]["adapter"]: adapter})
    with pytest.raises(ToolRuntimeError) as caught:
        _execute(runtime, source, node, arguments, tmp_path)
    assert len(calls) == 1 and caught.value.recovery is None
    assert caught.value.receipt["output_verification"]["status"] == "failed"
    assert caught.value.receipt["output_digest"] == sha256_digest(wrong)
    assert "private-invalid-evidence" not in str(caught.value)


def test_unsupported_result_schema_fails_before_adapter_execution(
    tmp_path: Path,
) -> None:
    catalog, _resource, source, node, arguments = _case(tmp_path)
    calls = []

    def adapter(**kwargs):
        calls.append(kwargs)
        raise AssertionError("invalid contract must never dispatch")

    runtime = ToolRuntime(catalog, adapters={"veyra.runtime.tabular.compare": adapter})
    authorization = runtime.authorize(source=source, node=node, values=arguments)
    resource = deepcopy(authorization.resource)
    resource["spec"]["output_json_schema"] = {"$ref": "https://example.invalid/schema"}
    authorization = replace(authorization, resource=resource)
    with pytest.raises(ToolRuntimeError) as caught:
        runtime.execute(
            project_root=tmp_path,
            source=source,
            node=node,
            values=arguments,
            authorization=authorization,
            approved=False,
        )
    assert caught.value.code == "tool_output_schema_invalid"
    assert calls == []


def test_existing_versions_keep_their_hashes_and_bound_version_is_not_upgraded() -> (
    None
):
    catalog = ResourceCatalog()
    hashes = {
        "1.0.0": "a625be4b78c99913c6c7592924aded140b93d8c2b14e356dceebaed65d194b5c",
        "1.1.0": "40585c7b122bd6990c62a4b5113ce75b823bc2a0859defc81aad97771e56d6fc",
    }
    for version, digest in hashes.items():
        resource = catalog.detail("veyra.tool.tabular.compare", version)
        assert resource["content_hash"] == digest
        assert prepare_tool_output_contract(resource["spec"]) is None
    bound = catalog.detail("veyra.tool.tabular.compare", "1.1.0")
    payload = {
        "schema_version": "1.0",
        "goal": "Compare selected CSV files",
        "summary": "Compare with source evidence",
        "actors": [
            {"id": "analyst", "role": "analysis", "capabilities": ["tabular_compare"]}
        ],
        "stages": [
            {"id": "compare", "actor": "analyst", "summary": "Compare the files"}
        ],
        "inputs": [field("request", "string")],
        "outputs": [field("result", "object")],
        "execution_boundaries": [],
        "lifecycle": {"persistent": False, "interaction": "single_run"},
        "uncertainty": [],
    }
    product = generate_builder_product(
        payload["goal"],
        catalog,
        planner_provider=Planner(payload),
        project_resources=[
            {
                **bound,
                "scope": "project",
                "bound_content_hash": bound["content_hash"],
                "binding_status": "current",
            }
        ],
    )
    assert product.status == "review", product.diagnostics
    assert product.source.lock[bound["reference"]] == bound["content_hash"]
    assert "veyra.tool.tabular.compare@1.2.0" not in product.source.lock
