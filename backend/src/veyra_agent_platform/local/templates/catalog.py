"""Safe built-in Agent templates available to local Projects."""

from __future__ import annotations

from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.common import new_uuid7

STARTER_TEMPLATE_ID = "veyra.starter-agent@1.0.0"
_RUNTIME_LOCK_DIGEST = "0" * 64

_STARTER_SOURCE: dict[str, Any] = {
    "schema_version": "1.0",
    "agentspec_version": "26.1",
    "component_type": "Flow",
    "agent_id": "01a03795-a5b0-7f61-a971-4c55cead5f27",
    "slug": "starter-agent",
    "name": "Starter Agent",
    "description": "A safe local-first starting point for a new Agent.",
    "inputs": {"request": "string"},
    "outputs": {"result": "string"},
    "nodes": [
        {"id": "start", "component_type": "Start"},
        {
            "id": "agent",
            "component_type": "Agent",
            "model_ref": "model.primary",
            "system_prompt": "Complete the request and return a concise result.",
        },
        {
            "id": "output",
            "component_type": "Output",
            "output_name": "result",
        },
    ],
    "transitions": [
        {"from": "start", "port": "next", "to": "agent"},
        {"from": "agent", "port": "next", "to": "output"},
    ],
    "extensions": {
        "veyra": {
            "runtime_profile": "veyra-runtime-profile/1",
            "secret_refs": [],
            "permissions": {
                "network_hosts": [],
                "tools": [],
                "filesystem_read_roots": [],
                "filesystem_write_roots": [],
                "shell_workspace_only": False,
            },
            "verification": {"required": False, "checks": []},
        }
    },
    "ui": {
        "positions": {
            "start": {"x": 0, "y": 80},
            "agent": {"x": 240, "y": 80},
            "output": {"x": 480, "y": 80},
        }
    },
    "lock": {"veyra.runtime.profile@1.0.0": _RUNTIME_LOCK_DIGEST},
}


class AgentTemplateError(ValueError):
    """A template selection is unknown or violates the safe catalog contract."""


class AgentTemplateCatalog:
    """Return validated copies of platform-owned, versioned Agent templates."""

    def __init__(self) -> None:
        starter = AgentSource.from_dict(_STARTER_SOURCE)
        permissions = starter.permissions
        if (
            permissions.network_hosts
            or permissions.tools
            or permissions.filesystem_read_roots
            or permissions.filesystem_write_roots
            or permissions.shell_workspace_only
        ):
            raise RuntimeError("starter Agent template must have no external authority")
        self._sources = {STARTER_TEMPLATE_ID: starter}

    def metadata(self) -> list[dict[str, str]]:
        starter = self._sources[STARTER_TEMPLATE_ID]
        return [
            {
                "template_id": STARTER_TEMPLATE_ID,
                "name": starter.name,
                "description": starter.description,
                "default_slug": starter.slug,
            }
        ]

    def instantiate(
        self, *, template_id: str, slug: str, name: str, description: str
    ) -> AgentSource:
        template = self._sources.get(template_id)
        if template is None:
            raise AgentTemplateError("unknown Agent template")
        source = template.to_dict()
        source.update(
            {
                "agent_id": new_uuid7(),
                "slug": slug,
                "name": name,
                "description": description,
            }
        )
        return AgentSource.from_dict(source)
