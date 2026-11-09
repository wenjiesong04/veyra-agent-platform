from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace
from decimal import localcontext
from pathlib import Path

import httpx
import pytest

from tests.unit.local.test_arithmetic_tool import _source
from tests.unit.local.test_semantic_composition import Planner, field
from veyra_agent_platform.contracts.agent import ComponentType
from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.task_structure import TaskStructure
from veyra_agent_platform.local.builder.generate_product import generate_builder_product
from veyra_agent_platform.local.builder.model_requirements import (
    derive_model_requirements,
)
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.agent_loop import _tool_input_error
from veyra_agent_platform.local.runtime.tabular import (
    TABULAR_DEFAULT_RESULT_BYTES,
    TABULAR_MAX_FILE_BYTES,
    TABULAR_MAX_RESULT_BYTES,
    TabularError,
    compare_csv,
)
from veyra_agent_platform.local.runtime.tools import ToolRuntime, ToolRuntimeError


def compare(left: bytes, right: bytes = b"id,value\n", **options):
    return compare_csv(
        left,
        right,
        **{
            "left_path": "assets/left.csv",
            "right_path": "assets/right.csv",
            "left_key": "code",
            "right_key": "id",
            "left_amount": "quantity",
            "right_amount": "value",
            "include_all_groups": True,
            **options,
        },
    )


def test_comparison_has_exact_full_outer_facts_and_original_quoted_physical_lines() -> (
    None
):
    left = (
        '\ufeffcode,quantity,note\r\n"a,b",0.1,"first line\r\n'
        'second line"\r\n"a,b",0.2,tail\r\nz,-2.50,n\r\n,4,blank\r\n'
    ).encode()
    right = b'id,value\n"a,b",0.3\nz,-2\nr,7\n ,5\n'
    result = compare(left, right)
    assert result["left"]["record_count"] == 4 and result["left"]["group_count"] == 2
    assert result["right"]["record_count"] == 4 and result["right"]["group_count"] == 3
    assert result["counts"] == {
        "matched_groups": 2,
        "equal_groups": 1,
        "different_groups": 1,
        "left_only_groups": 0,
        "right_only_groups": 1,
        "left_matched_records": 3,
        "right_matched_records": 2,
        "left_only_records": 0,
        "right_only_records": 1,
        "left_blank_key_records": 1,
        "right_blank_key_records": 1,
        "left_unmatched_records": 1,
        "right_unmatched_records": 2,
        "multi_record_groups": 1,
    }
    groups = {group["key"]: group for group in result["groups"]}
    assert groups["a,b"]["status"] == "equal" and groups["a,b"]["left_count"] == 2
    assert groups["a,b"]["left_rows"] == [
        {"line_start": 2, "line_end": 3, "amount": "0.1"},
        {"line_start": 4, "line_end": 4, "amount": "0.2"},
    ]
    assert groups["z"]["difference"] == "0.5"
    assert groups["r"]["left_total"] is None and groups["r"]["difference"] is None
    assert result["blank_keys"]["left"][0]["line_start"] == 6
    assert (
        result["totals"]["left_all"] == "1.8"
        and result["totals"]["right_all"] == "10.3"
    )
    assert result["totals"]["right_unmatched"] == "12"
    assert result["left"]["sha256"] == hashlib.sha256(left).hexdigest()
    assert result["summary_complete"] is True and result["truncated"] is False
    assert "first line" not in json.dumps(result)


def test_zero_amount_groups_still_require_matching_nonblank_keys() -> None:
    result = compare(b"code,quantity\na,0\n,0\n", b"id,value\nb,0\n,0\n")
    assert result["counts"]["equal_groups"] == 0
    assert (
        result["counts"]["left_only_groups"] == 1
        and result["counts"]["right_only_groups"] == 1
    )
    assert result["counts"]["left_unmatched_records"] == 2
    assert result["counts"]["right_unmatched_records"] == 2
    assert all(group["difference"] is None for group in result["groups"])


def test_key_matching_is_exact_and_does_not_coerce_numeric_or_trimmed_keys() -> None:
    result = compare(b"code,quantity\n001,1\n x,2\n", b"id,value\n1,1\nx,2\n")
    assert result["counts"]["matched_groups"] == 0
    assert (
        result["counts"]["left_only_groups"]
        == result["counts"]["right_only_groups"]
        == 2
    )


def test_decimal_sums_do_not_depend_on_ambient_decimal_precision() -> None:
    with localcontext() as context:
        context.prec = 2
        result = compare(
            b"code,quantity\na,123456789.123456789\na,0.000000001\na,-123456789\n",
            b"id,value\na,0.12345679\n",
        )
    assert result["counts"]["equal_groups"] == 1
    assert result["totals"]["left_all"] == "0.12345679"
    assert result["groups"][0]["difference"] == "0"


def test_empty_tables_have_complete_zero_counts_and_exact_totals() -> None:
    result = compare(b"code,quantity\n")
    assert result["left"]["record_count"] == result["right"]["record_count"] == 0
    assert result["groups"] == [] and result["truncated"] is False
    assert all(value == "0" for value in result["totals"].values())


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"code,quantity,code\n",
        b",quantity\n",
        b"code,quantity\na\n",
        b"code,quantity\na,1,extra\n",
        b'code,quantity\n"unterminated,1\n',
        b'code,quantity\ninvalid"quote,1\n',
        b'code,quantity\n"closed"tail,1\n',
        b"code,quantity\na,\xff\n",
        b"code,quantity\na,1\x00\n",
    ],
)
def test_malformed_or_duplicate_header_csv_fails_safely(content: bytes) -> None:
    with pytest.raises(TabularError) as error:
        compare(content)
    assert error.value.code == "tabular_csv_invalid"
    assert 'invalid"quote' not in str(error.value)


@pytest.mark.parametrize(
    "amount",
    [
        "",
        "NaN",
        "Infinity",
        "1/2",
        "1,234.56",
        "$123",
        "秘密-token",
        "1e100000000",
        "1.2345678901234567890123456789012345",
    ],
)
def test_invalid_or_unbounded_decimal_fails_without_cell_contents(amount: str) -> None:
    content = f'code,quantity\na,"{amount}"\n'.encode()
    with pytest.raises(TabularError) as error:
        compare(content)
    assert error.value.code == "tabular_amount_invalid"
    assert "physical line 2" in str(error.value)
    assert "秘密-token" not in str(error.value)


def test_missing_selected_columns_are_rejected_before_comparing() -> None:
    with pytest.raises(TabularError) as error:
        compare(b"code,quantity\na,1\n", left_key="not_present")
    assert error.value.code == "tabular_input_invalid"


def test_file_record_column_cell_and_header_boundaries_are_enforced() -> None:
    with pytest.raises(TabularError, match="1 MB"):
        compare(b"x" * (TABULAR_MAX_FILE_BYTES + 1))
    with pytest.raises(TabularError, match="2000"):
        compare(b"code,quantity\n" + b"a,1\n" * 2001)
    with pytest.raises(TabularError, match="50"):
        compare((",".join(f"c{index}" for index in range(51)) + "\n").encode())
    with pytest.raises(TabularError, match="4096"):
        compare(b"code,quantity\n" + b"a" * 4097 + b",1\n")
    with pytest.raises(TabularError, match="256"):
        compare(("code,quantity," + "h" * 257 + "\n").encode())


def test_details_are_bounded_while_all_summary_facts_remain_complete() -> None:
    left = b"code,quantity\n" + b"same,0.01\n" * 2000
    result = compare(left, b"id,value\nsame,20\n")
    assert result["counts"]["equal_groups"] == 1
    assert (
        result["left"]["record_count"] == 2000 and result["totals"]["left_all"] == "20"
    )
    assert result["groups"][0]["left_count"] == 2000
    assert len(result["groups"][0]["left_rows"]) == 200
    assert result["groups"][0]["left_rows_truncated"] is True
    assert result["summary_complete"] is True and result["truncated"] is True
    rows = "".join(f"k{index},1\n" for index in range(300))
    groups = compare(
        ("code,quantity\n" + rows).encode(), ("id,value\n" + rows).encode()
    )
    assert groups["counts"]["equal_groups"] == 300 and len(groups["groups"]) == 200
    assert groups["truncated"] is True


def test_serialized_output_byte_limit_handles_multibyte_keys() -> None:
    rows = "".join(f"{'汉' * 1000}{index},1\n" for index in range(180))
    result = compare(
        ("code,quantity\n" + rows).encode(), ("id,value\n" + rows).encode()
    )
    assert result["counts"]["equal_groups"] == 180
    assert result["truncated"] is True and result["summary_complete"] is True
    assert (
        len(json.dumps(result, ensure_ascii=False).encode()) <= TABULAR_MAX_RESULT_BYTES
    )


def test_default_summary_precedes_bounded_mismatch_details() -> None:
    left = "code,quantity\n" + "".join(f"k{index},1\n" for index in range(300))
    right = "id,value\n" + "".join(f"k{index},2\n" for index in range(300))
    result = compare(left.encode(), right.encode(), include_all_groups=False)
    assert list(result)[:5] == ["schema_version", "left", "right", "counts", "totals"]
    assert result["counts"]["different_groups"] == 300
    assert (
        result["totals"]["left_all"] == "300" and result["totals"]["right_all"] == "600"
    )
    assert result["summary_complete"] is True
    assert (
        result["mismatch_groups_truncated"] is True
        and result["groups_requested"] is False
    )
    assert (
        len(json.dumps(result, ensure_ascii=False).encode())
        <= TABULAR_DEFAULT_RESULT_BYTES
    )


def runtime_case(tmp_path: Path):
    catalog = ResourceCatalog()
    resource = catalog.detail("veyra.tool.tabular.compare", "1.0.0")
    source = _source(resource)
    source = replace(
        source,
        permissions=replace(source.permissions, filesystem_read_roots=("project",)),
    )
    node = next(
        item for item in source.nodes if item.component_type is ComponentType.TOOL
    )
    (tmp_path / "left.csv").write_bytes(b"code,quantity\na,0.1\na,0.2\n")
    (tmp_path / "right.csv").write_bytes(b"id,value\na,0.3\n")
    values = {
        "left_path": "left.csv",
        "right_path": "right.csv",
        "left_key": "code",
        "right_key": "id",
        "left_amount": "quantity",
        "right_amount": "value",
    }
    return catalog, resource, source, node, values


def test_runtime_is_permission_checked_read_only_and_records_exact_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    catalog, resource, source, node, values = runtime_case(tmp_path)
    assert resource["capabilities"] == ["tabular_compare"]
    assert _tool_input_error(resource, values) is None
    runtime = ToolRuntime(catalog)

    def forbidden(*args, **kwargs):
        raise AssertionError("external effect attempted")

    monkeypatch.setattr(httpx.Client, "request", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in tmp_path.iterdir()
    }
    authorization = runtime.authorize(source=source, node=node, values=values)
    assert (
        authorization.decision == "allowed" and authorization.approval_required is False
    )
    execution = runtime.execute(
        project_root=tmp_path,
        source=source,
        node=node,
        values=values,
        authorization=authorization,
        approved=False,
    )
    assert execution.output["counts"]["equal_groups"] == 1
    assert execution.receipt["authorization"] == "allowed"
    assert execution.receipt["output_digest"] == sha256_digest(execution.output)
    assert execution.output["left"]["sha256"] == hashes["left.csv"]
    assert hashes == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in tmp_path.iterdir()
    }
    for permissions in (
        replace(source.permissions, tools=()),
        replace(source.permissions, filesystem_read_roots=()),
    ):
        assert (
            runtime.authorize(
                source=replace(source, permissions=permissions),
                node=node,
                values=values,
            ).decision
            == "denied"
        )


@pytest.mark.parametrize(
    "path",
    [
        "../outside.csv",
        "/outside.csv",
        "..\\outside.csv",
        "..／outside.csv",
        ".env",
        "private.key",
        "left.csv\x00",
    ],
)
def test_runtime_denies_traversal_absolute_and_secret_paths(
    tmp_path: Path, path: str
) -> None:
    catalog, _, source, node, values = runtime_case(tmp_path)
    runtime = ToolRuntime(catalog)
    values["left_path"] = path
    authorization = runtime.authorize(source=source, node=node, values=values)
    with pytest.raises(ToolRuntimeError) as error:
        runtime.execute(
            project_root=tmp_path,
            source=source,
            node=node,
            values=values,
            authorization=authorization,
            approved=False,
        )
    assert error.value.code == "tool_path_denied"
    assert str(tmp_path) not in str(error.value)


def test_runtime_denies_symlinks_and_bounds_reads(tmp_path: Path) -> None:
    catalog, _, source, node, values = runtime_case(tmp_path)
    runtime = ToolRuntime(catalog)
    target = tmp_path / "link.csv"
    target.symlink_to(tmp_path / "left.csv")
    values["left_path"] = "link.csv"
    authorization = runtime.authorize(source=source, node=node, values=values)
    with pytest.raises(ToolRuntimeError, match="symlinks"):
        runtime.execute(
            project_root=tmp_path,
            source=source,
            node=node,
            values=values,
            authorization=authorization,
            approved=False,
        )
    target.unlink()
    target.write_bytes(b"x" * (TABULAR_MAX_FILE_BYTES + 1))
    with pytest.raises(ToolRuntimeError, match="1 MB"):
        runtime.execute(
            project_root=tmp_path,
            source=source,
            node=node,
            values=values,
            authorization=authorization,
            approved=False,
        )


def test_generator_pins_table_tool_without_model_capability_inflation() -> None:
    requirement = (
        "Compare two CSV files by exact text key and sum the chosen numeric columns."
    )
    payload = {
        "schema_version": "1.0",
        "goal": requirement,
        "summary": requirement,
        "actors": [
            {
                "id": "analyst",
                "role": "table analysis",
                "capabilities": ["tabular_compare"],
            }
        ],
        "stages": [{"id": "compare", "actor": "analyst", "summary": requirement}],
        "inputs": [field("request", "string")],
        "outputs": [field("result", "object")],
        "execution_boundaries": [],
        "lifecycle": {"persistent": False, "interaction": "single_run"},
        "uncertainty": [],
    }
    catalog = ResourceCatalog()
    product = generate_builder_product(
        requirement, catalog, planner_provider=Planner(payload)
    )
    assert product.status == "review", product.diagnostics
    assert "veyra.tool.tabular.compare" in product.source.permissions.tools
    assert product.source.permissions.filesystem_read_roots == ("project",)
    resource = catalog.detail("veyra.tool.tabular.compare", "1.2.0")
    assert product.source.lock[resource["reference"]] == resource["content_hash"]
    needs = derive_model_requirements(TaskStructure.from_dict(payload), product.plan)
    assert all(need.required == ("text_generation",) for need in needs)
