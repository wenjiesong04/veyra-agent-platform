from __future__ import annotations

from pathlib import Path

from veyra_agent_platform.contracts.agent import AgentSource, ComponentType
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.tools import (
    ToolAuthorization,
    ToolExecution,
    ToolRuntime,
)


def test_injected_tool_adapter_can_extend_runtime(tmp_path: Path) -> None:
    catalog = ResourceCatalog()
    resource = catalog.detail("veyra.tool.filesystem.read", "1.0.0")
    source = AgentSource.from_dict(
        {
            "schema_version": "1.0",
            "agentspec_version": "26.1",
            "component_type": "Flow",
            "agent_id": "01a03795-a5b0-7f61-a971-4c55cead5f27",
            "slug": "adapter",
            "name": "Adapter",
            "description": "Injected adapter test.",
            "inputs": {"path": "string"},
            "outputs": {"content": "string"},
            "nodes": [
                {"id": "start", "component_type": "Start"},
                {"id": "read", "component_type": "Tool", "uses": resource["reference"]},
                {"id": "output", "component_type": "Output", "output_name": "content"},
            ],
            "transitions": [
                {"from": "start", "port": "next", "to": "read"},
                {"from": "read", "port": "next", "to": "output"},
            ],
            "extensions": {
                "veyra": {
                    "runtime_profile": "veyra-runtime-profile/1",
                    "secret_refs": [],
                    "permissions": {
                        "network_hosts": [],
                        "tools": [resource["resource_id"]],
                        "filesystem_read_roots": ["project"],
                        "filesystem_write_roots": [],
                        "shell_workspace_only": False,
                    },
                    "verification": {"required": False, "checks": []},
                }
            },
            "ui": {
                "positions": {
                    "start": {"x": 0, "y": 0},
                    "read": {"x": 1, "y": 0},
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

    def plugin(
        *,
        project_root: Path,
        source: AgentSource,
        node: object,
        values: dict[str, object],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution:
        del project_root, source, node, values, approved
        return ToolExecution(
            output={"content": "from injected plugin"},
            receipt={"plugin": "test", "authorization": authorization.decision},
        )

    runtime = ToolRuntime(catalog, adapters={"veyra.runtime.filesystem.read": plugin})
    authorization = runtime.authorize(
        source=source, node=node, values={"path": "x.txt"}
    )
    execution = runtime.execute(
        project_root=tmp_path,
        source=source,
        node=node,
        values={"path": "x.txt"},
        authorization=authorization,
        approved=False,
    )

    assert execution.output == {"content": "from injected plugin"}
    assert execution.receipt["plugin"] == "test"
