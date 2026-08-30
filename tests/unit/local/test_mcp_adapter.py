from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

from veyra_agent_platform.contracts.agent import AgentSource, ComponentType
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.tools import ToolRuntime


class _FakeMcp:
    def call(
        self, server_id: str, tool_name: str, arguments: dict[str, object]
    ) -> dict[str, object]:
        assert server_id == "server-1"
        assert tool_name == "echo"
        return {"content": [{"type": "text", "text": arguments["text"]}]}


def _source(resource: dict[str, object]) -> AgentSource:
    return AgentSource.from_dict(
        {
            "schema_version": "1.0",
            "agentspec_version": "26.1",
            "component_type": "Flow",
            "agent_id": "01a03795-a5b0-7f61-a971-4c55cead5f27",
            "slug": "mcp-agent",
            "name": "MCP Agent",
            "description": "Calls a discovered MCP tool.",
            "inputs": {"text": "string"},
            "outputs": {"result": "object"},
            "nodes": [
                {"id": "start", "component_type": "Start"},
                {
                    "id": "call",
                    "component_type": "Tool",
                    "uses": resource["reference"],
                },
                {"id": "output", "component_type": "Output", "output_name": "result"},
            ],
            "transitions": [
                {"from": "start", "port": "next", "to": "call"},
                {"from": "call", "port": "next", "to": "output"},
            ],
            "extensions": {
                "veyra": {
                    "runtime_profile": "veyra-runtime-profile/1",
                    "secret_refs": [],
                    "permissions": {
                        "network_hosts": [],
                        "tools": [resource["resource_id"]],
                        "filesystem_read_roots": [],
                        "filesystem_write_roots": [],
                        "shell_workspace_only": False,
                    },
                    "verification": {"required": False, "checks": []},
                }
            },
            "ui": {
                "positions": {
                    "start": {"x": 0, "y": 0},
                    "call": {"x": 1, "y": 0},
                    "output": {"x": 2, "y": 0},
                }
            },
            "lock": {
                "veyra.runtime.profile@1.0.0": "0" * 64,
                resource["reference"]: resource["content_hash"],
            },
        }
    )


def test_unconfigured_builtin_mcp_call_is_not_executable() -> None:
    catalog = ResourceCatalog()
    resource = catalog.detail("veyra.mcp.call", "1.0.0")
    runtime = ToolRuntime(catalog)
    source = AgentSource.from_dict(
        {
            "schema_version": "1.0",
            "agentspec_version": "26.1",
            "component_type": "Flow",
            "agent_id": "01a03795-a5b0-7f61-a971-4c55cead5f27",
            "slug": "mcp-generic",
            "name": "MCP Generic",
            "description": "Generic MCP call stays unconfigured.",
            "inputs": {"text": "string"},
            "outputs": {"result": "string"},
            "nodes": [
                {"id": "start", "component_type": "Start"},
                {
                    "id": "call",
                    "component_type": "Tool",
                    "uses": resource["reference"],
                },
                {"id": "output", "component_type": "Output", "output_name": "result"},
            ],
            "transitions": [
                {"from": "start", "port": "next", "to": "call"},
                {"from": "call", "port": "next", "to": "output"},
            ],
            "extensions": {
                "veyra": {
                    "runtime_profile": "veyra-runtime-profile/1",
                    "secret_refs": [],
                    "permissions": {
                        "network_hosts": [],
                        "tools": ["veyra.mcp.call"],
                        "filesystem_read_roots": [],
                        "filesystem_write_roots": [],
                        "shell_workspace_only": False,
                    },
                    "verification": {"required": False, "checks": []},
                }
            },
            "ui": {
                "positions": {
                    "start": {"x": 0, "y": 0},
                    "call": {"x": 1, "y": 0},
                    "output": {"x": 2, "y": 0},
                }
            },
            "lock": {
                "veyra.runtime.profile@1.0.0": "0" * 64,
                resource["reference"]: resource["content_hash"],
            },
        }
    )
    node = next(
        item for item in source.nodes if item.component_type is ComponentType.TOOL
    )
    authorization = runtime.authorize(source=source, node=node, values={"text": "hi"})
    assert authorization.decision == "denied"
    assert authorization.code == "tool_unavailable"


def test_discovered_mcp_tool_executes_through_runtime_adapter(tmp_path: Path) -> None:
    overlay = tmp_path / "overlays"
    package = overlay / "discovered" / "echo" / "node.yaml"
    package.parent.mkdir(parents=True)
    package.write_text(
        yaml.safe_dump(
            {
                "resource_id": "veyra.mcp.demo.echo",
                "kind": "tool",
                "name": "echo",
                "description": "Echo text through MCP",
                "availability": "ready",
                "factory_selectable": True,
                "runtime_status": "supported",
                "required_permissions": {
                    "network_hosts": [],
                    "tools": ["veyra.mcp.demo.echo"],
                    "filesystem_read_roots": [],
                    "filesystem_write_roots": [],
                    "shell_workspace_only": False,
                },
                "tags": ["mcp", "discovered"],
                "spec": {
                    "adapter": "veyra.runtime.mcp.call",
                    "approval_required": False,
                    "mcp_server_id": "server-1",
                    "mcp_tool_name": "echo",
                    "input_schema": {"text": "string"},
                    "tool_name": "mcp.echo",
                    "ui": {"category": "mcp", "icon": "plug", "title": "echo"},
                },
                "version": "1.0.0",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    catalog = ResourceCatalog(overlay_root=overlay)
    resource = catalog.detail("veyra.mcp.demo.echo", "1.0.0")
    runtime = ToolRuntime(catalog, mcp=_FakeMcp())
    source = _source(resource)
    node = next(
        item for item in source.nodes if item.component_type is ComponentType.TOOL
    )
    values = {"text": "hello"}
    authorization = runtime.authorize(source=source, node=node, values=values)
    assert authorization.decision == "allowed"
    assert authorization.adapter == "veyra.runtime.mcp.call"
    execution = runtime.execute(
        project_root=tmp_path,
        source=source,
        node=node,
        values=values,
        authorization=authorization,
        approved=False,
    )
    assert execution.output["result"]["content"][0]["text"] == "hello"
    assert execution.receipt["authorization"] == "allowed"
