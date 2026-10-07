from __future__ import annotations

import builtins
import json
import math
import sqlite3
import subprocess
from dataclasses import replace
from decimal import localcontext
from pathlib import Path
from typing import Any

import httpx
import pytest

from veyra_agent_platform.contracts.agent import AgentSource, ComponentType
from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.agent_loop import _tool_input_error
from veyra_agent_platform.local.runtime.arithmetic import ArithmeticError, calculate
from veyra_agent_platform.local.runtime.tools import ToolRuntime, ToolRuntimeError


def _source(resource: dict[str, Any]) -> AgentSource:
    return AgentSource.from_dict(
        {
            "schema_version": "1.0",
            "agentspec_version": "26.1",
            "component_type": "Flow",
            "agent_id": "01a03795-a5b0-7f61-a971-4c55cead5f27",
            "slug": "arithmetic",
            "name": "Arithmetic fixture",
            "description": "Controlled numeric calculation.",
            "inputs": {"expression": "string"},
            "outputs": {"value": "number"},
            "nodes": [
                {"id": "start", "component_type": "Start"},
                {
                    "id": "calculate",
                    "component_type": "Tool",
                    "uses": resource["reference"],
                },
                {"id": "output", "component_type": "Output", "output_name": "value"},
            ],
            "transitions": [
                {"from": "start", "port": "next", "to": "calculate"},
                {"from": "calculate", "port": "next", "to": "output"},
            ],
            "extensions": {
                "veyra": {
                    "runtime_profile": "veyra-runtime-profile/1",
                    "secret_refs": [],
                    "permissions": {
                        "network_hosts": [],
                        "tools": [resource["resource_id"]],
                    },
                    "verification": {"required": False, "checks": []},
                }
            },
            "ui": {
                "positions": {
                    "start": {"x": 0, "y": 0},
                    "calculate": {"x": 200, "y": 0},
                    "output": {"x": 400, "y": 0},
                }
            },
            "lock": {resource["reference"]: resource["content_hash"]},
        }
    )


@pytest.fixture
def tool():
    catalog = ResourceCatalog()
    descriptor = catalog.detail("veyra.tool.math.calculate", "1.0.0")
    source = _source(descriptor)
    node = next(
        item for item in source.nodes if item.component_type is ComponentType.TOOL
    )
    return ToolRuntime(catalog), descriptor, source, node


def _execute(tool: tuple, expression: object, tmp_path: Path):
    runtime, _descriptor, source, node = tool
    values = {} if expression is None else {"expression": expression}
    authorization = runtime.authorize(source=source, node=node, values=values)
    assert authorization.decision == "allowed"
    assert authorization.approval_required is False
    return runtime.execute(
        project_root=tmp_path,
        source=source,
        node=node,
        values=values,
        authorization=authorization,
        approved=False,
        project_id="project-1",
    )


@pytest.mark.parametrize(
    "expression,value,exact,approximate",
    [
        ("0.1 + 0.2", 0.3, "0.3", False),
        ("(12.5 - 2.5) * 3 / 4", 7.5, "7.5", False),
        ("-(-2) + +3", 5, "5", False),
        ("1/3", 1 / 3, "1/3", True),
        ("(1/3)*3", 1, "1", False),
        ("-1/6", -1 / 6, "-1/6", True),
        ("2.50/0.5", 5, "5", False),
        ("1e2 + .25", 100.25, "100.25", False),
        ("0 - 0", 0, "0", False),
    ],
)
def test_real_adapter_calculates_exact_values_and_receipts(
    tool: tuple,
    tmp_path: Path,
    expression: str,
    value: int | float,
    exact: str,
    approximate: bool,
) -> None:
    execution = _execute(tool, expression, tmp_path)
    assert execution.output == {
        "expression": expression,
        "value": value,
        "exact": exact,
        "approximate": approximate,
    }
    assert math.isfinite(execution.output["value"])
    assert execution.receipt["adapter"] == "veyra.runtime.math.calculate"
    assert execution.receipt["authorization"] == "allowed"
    assert execution.receipt["output_digest"] == sha256_digest(execution.output)
    assert json.loads(json.dumps(execution.output, allow_nan=False)) == execution.output


def test_literal_decimal_precision_is_not_lost_to_ast_float() -> None:
    result = calculate(
        "0.123456789012345678901234567890 + 0.000000000000000000000000000001"
    )
    assert result["exact"] == "0.123456789012345678901234567891"
    assert result["approximate"] is True
    assert result["value"] == float(result["exact"])


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo unsafe')",
        "open('file')",
        "a+1",
        "1e+e",
        "(1).real",
        "(1).__class__",
        "1[0]",
        "[1,2]",
        "{'a': 1}",
        "1,2",
        "True",
        "None",
        "1j",
        "2**8",
        "4//2",
        "5%2",
        "1 << 2",
        "lambda: 1",
        "1 if 1 else 2",
        "sum([1,2])",
        "1 # comment",
        "0x10",
        "1_000",
        "1/0",
        "1/(2-2)",
        "1e999999",
        "1e-999999",
        "9" * 33,
        "1e32*10",
        "1e-32/10",
        "+".join(["1"] * 23),
        "(" * 201 + "1" + ")" * 201,
        "",
        None,
        3,
    ],
)
def test_real_adapter_rejects_malicious_or_unbounded_expressions(
    tool: tuple,
    tmp_path: Path,
    expression: object,
) -> None:
    with pytest.raises(ToolRuntimeError) as error:
        _execute(tool, expression, tmp_path)
    assert error.value.code == "tool_input_invalid"


def test_fraction_growth_is_bounded() -> None:
    expression = (
        "1/99999999999999999999999999999991 + "
        "1/99999999999999999999999999999989 + "
        "1/99999999999999999999999999999987"
    )
    with pytest.raises(ArithmeticError, match="numeric limits"):
        calculate(expression)


def test_calculation_does_not_inherit_or_modify_decimal_context() -> None:
    with localcontext() as context:
        context.prec = 3
        context.Emin = -2
        context.Emax = 2
        assert calculate("10000 + 0.5")["exact"] == "10000.5"
        assert (context.prec, context.Emin, context.Emax) == (3, -2, 2)


def test_tool_requires_expression_and_retains_permission_and_hash_boundary(
    tool: tuple,
) -> None:
    runtime, descriptor, source, node = tool
    assert descriptor["capabilities"] == ["arithmetic"]
    assert descriptor["spec"]["input_schema"]["expression"]["required"] is True
    assert descriptor["spec"]["output_schema"] == {
        "expression": "string",
        "value": "number",
        "exact": "string",
        "approximate": "boolean",
    }
    assert _tool_input_error(descriptor, {}) is not None
    assert _tool_input_error(descriptor, {"expression": "1+2"}) is None
    assert _tool_input_error(descriptor, {"expression": 3}) is not None
    unauthorized = replace(source, permissions=replace(source.permissions, tools=()))
    denied = runtime.authorize(
        source=unauthorized, node=node, values={"expression": "1+2"}
    )
    assert denied.code == "tool_permission_denied"
    stale = replace(source, lock={descriptor["reference"]: "0" * 64})
    assert (
        runtime.authorize(source=stale, node=node, values={"expression": "1+2"}).code
        == "tool_lock_invalid"
    )


def test_arithmetic_execution_has_no_external_or_host_effects(
    tool: tuple,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def forbidden(*args: Any, **kwargs: Any):
        del args, kwargs
        calls.append("effect")
        raise AssertionError("Arithmetic must not perform external or host effects")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(builtins, "eval", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(httpx.Client, "request", forbidden)
    assert _execute(tool, "(3.2 + 1.8) / 2", tmp_path).output["exact"] == "2.5"
    assert calls == []
