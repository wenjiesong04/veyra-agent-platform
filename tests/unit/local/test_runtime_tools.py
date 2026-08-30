from __future__ import annotations

from pathlib import Path

import pytest

from veyra_agent_platform.contracts.agent import AgentSource, ComponentType
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.tools import ToolRuntime, ToolRuntimeError


def test_write_adapter_stays_inside_project(tmp_path: Path) -> None:
    catalog = ResourceCatalog()
    resource = catalog.detail("veyra.tool.filesystem.write", "1.0.0")
    source = AgentSource.from_dict(
        {
            "schema_version": "1.0",
            "agentspec_version": "26.1",
            "component_type": "Flow",
            "agent_id": "01a03795-a5b0-7f61-a971-4c55cead5f27",
            "slug": "writer",
            "name": "Writer",
            "description": "Writes a Project file.",
            "inputs": {"path": "string", "content": "string"},
            "outputs": {"written": "boolean"},
            "nodes": [
                {"id": "start", "component_type": "Start"},
                {
                    "id": "write",
                    "component_type": "Tool",
                    "uses": resource["reference"],
                },
                {"id": "output", "component_type": "Output", "output_name": "written"},
            ],
            "transitions": [
                {"from": "start", "port": "next", "to": "write"},
                {"from": "write", "port": "next", "to": "output"},
            ],
            "extensions": {
                "veyra": {
                    "runtime_profile": "veyra-runtime-profile/1",
                    "secret_refs": [],
                    "permissions": {
                        "network_hosts": [],
                        "tools": ["veyra.tool.filesystem.write"],
                        "filesystem_read_roots": [],
                        "filesystem_write_roots": ["project"],
                        "shell_workspace_only": False,
                    },
                    "verification": {"required": False, "checks": []},
                }
            },
            "ui": {
                "positions": {
                    "start": {"x": 0, "y": 0},
                    "write": {"x": 1, "y": 0},
                    "output": {"x": 2, "y": 0},
                }
            },
            "lock": {
                "veyra.runtime.profile@1.0.0": "0" * 64,
                resource["reference"]: resource["content_hash"],
            },
        }
    )
    runtime = ToolRuntime(catalog)
    node = next(
        item for item in source.nodes if item.component_type is ComponentType.TOOL
    )
    values = {"path": "notes/hello.txt", "content": "hi"}
    authorization = runtime.authorize(source=source, node=node, values=values)
    assert authorization.decision == "allowed"
    assert authorization.approval_required is True
    execution = runtime.execute(
        project_root=tmp_path,
        source=source,
        node=node,
        values=values,
        authorization=authorization,
        approved=True,
    )
    assert execution.output == {"written": True}
    assert (tmp_path / "notes" / "hello.txt").read_text(encoding="utf-8") == "hi"
    with pytest.raises(ToolRuntimeError) as denied:
        runtime.execute(
            project_root=tmp_path,
            source=source,
            node=node,
            values=values,
            authorization=authorization,
            approved=False,
        )
    assert denied.value.code == "approval_required"
    with pytest.raises(ToolRuntimeError) as escaped:
        runtime.execute(
            project_root=tmp_path,
            source=source,
            node=node,
            values={"path": "../secret.txt", "content": "no"},
            authorization=authorization,
            approved=True,
        )
    assert escaped.value.code == "tool_path_denied"
