"""Immutable, server-owned descriptors for local Factory and Studio resources."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Final, Literal

from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.common import SCHEMA_VERSION

ResourceKind = Literal["component", "tool", "mcp_tool", "skill", "policy", "template"]
Availability = Literal[
    "ready",
    "requires_configuration",
    "design_only",
    "quarantined",
    "disabled",
    "unavailable",
]
RuntimeStatus = Literal["supported", "runtime_not_configured", "runtime_not_supported"]

RESOURCE_KINDS: Final[tuple[ResourceKind, ...]] = (
    "component",
    "tool",
    "mcp_tool",
    "skill",
    "policy",
    "template",
)

_EMPTY_PERMISSIONS: Final[dict[str, Any]] = {
    "network_hosts": [],
    "tools": [],
    "filesystem_read_roots": [],
    "filesystem_write_roots": [],
    "shell_workspace_only": False,
}

_COMPONENTS: Final[tuple[tuple[str, list[str], list[str], RuntimeStatus], ...]] = (
    ("Start", [], ["next"], "supported"),
    ("Agent", ["model_ref", "system_prompt"], ["next"], "runtime_not_configured"),
    ("Tool", ["uses"], ["next"], "supported"),
    ("Condition", ["expression"], ["true", "false"], "supported"),
    ("Transform", ["mapping"], ["next"], "supported"),
    ("HumanApproval", ["prompt"], ["approved", "rejected"], "supported"),
    ("Verifier", ["checks"], ["passed", "failed"], "supported"),
    ("Output", ["output_name"], [], "supported"),
)


class ResourceCatalogError(ValueError):
    """Raised when a requested catalog filter or immutable reference is invalid."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ResourceCatalog:
    """Expose copies of a closed in-code catalog; callers cannot mutate its state."""

    def __init__(self) -> None:
        resources = self._load_node_file()
        if resources is None:
            resources = [self._component(*definition) for definition in _COMPONENTS]
            resources.extend(self._tool_resources())
            resources.extend(self._mcp_resources())
            resources.extend(self._skill_resources())
            resources.extend(self._policy_resources())
            resources.extend(self._template_resources())
        self._resources = tuple(self._descriptor(resource) for resource in resources)
        self._by_reference = {
            (resource["resource_id"], resource["version"]): resource
            for resource in self._resources
        }
        if len(self._by_reference) != len(self._resources):
            raise RuntimeError("resource catalog references must be unique")

    @staticmethod
    def _load_node_file() -> list[dict[str, Any]] | None:
        """Load the committed node definitions before using the code fallback."""
        path = (
            Path(__file__).resolve().parents[5]
            / "resources"
            / "nodes"
            / "catalog.v1.json"
        )
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Resource node catalog could not be read") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != SCHEMA_VERSION
            or payload.get("catalog_version") != "1"
        ):
            raise RuntimeError("Resource node catalog has an unsupported schema")
        nodes = payload.get("nodes")
        if (
            not isinstance(nodes, list)
            or not nodes
            or not all(isinstance(node, dict) for node in nodes)
        ):
            raise RuntimeError("Resource node catalog must contain node descriptors")
        required = {
            "resource_id",
            "kind",
            "name",
            "description",
            "availability",
            "factory_selectable",
            "runtime_status",
            "required_permissions",
            "tags",
            "spec",
        }
        if any(set(node) != required for node in nodes):
            raise RuntimeError("Resource node catalog contains an invalid descriptor")
        return [deepcopy(node) for node in nodes]

    def resources(
        self, *, kind: str | None = None, availability: str | None = None
    ) -> dict[str, Any]:
        self._validate_kind(kind)
        self._validate_availability(availability)
        selected = [
            resource
            for resource in self._resources
            if (kind is None or resource["kind"] == kind)
            and (availability is None or resource["availability"] == availability)
        ]
        return {
            "schema_version": SCHEMA_VERSION,
            "resources": deepcopy(selected),
            "kinds": [
                {
                    "kind": resource_kind,
                    "count": sum(
                        resource["kind"] == resource_kind for resource in selected
                    ),
                }
                for resource_kind in RESOURCE_KINDS
            ],
        }

    def detail(self, resource_id: str, version: str) -> dict[str, Any]:
        resource = self._by_reference.get((resource_id, version))
        if resource is None:
            raise ResourceCatalogError(
                "resource_not_found",
                "resource version is not registered in this catalog",
            )
        return deepcopy(resource)

    def by_reference(self, reference: str) -> dict[str, Any]:
        if not isinstance(reference, str) or "@" not in reference:
            raise ResourceCatalogError(
                "resource_not_found",
                "resource version is not registered in this catalog",
            )
        resource_id, version = reference.rsplit("@", 1)
        return self.detail(resource_id, version)

    def factory_snapshot(self) -> list[dict[str, Any]]:
        """Return the bounded descriptors Factory may send to a model."""
        return [
            {
                "reference": resource["reference"],
                "kind": resource["kind"],
                "name": resource["name"],
                "description": resource["description"],
                "availability": resource["availability"],
                "runtime_status": resource["runtime_status"],
                "required_permissions": deepcopy(resource["required_permissions"]),
                "spec": deepcopy(resource["spec"]),
            }
            for resource in self._resources
            if resource["factory_selectable"]
        ]

    def components(self) -> list[dict[str, Any]]:
        """Project component Resources into the legacy Studio endpoint shape."""
        return [
            {
                "type": resource["name"],
                "fields": deepcopy(resource["spec"]["fields"]),
                "output_ports": deepcopy(resource["spec"]["output_ports"]),
                "runtime_status": resource["runtime_status"],
            }
            for resource in self._resources
            if resource["kind"] == "component"
        ]

    @staticmethod
    def _descriptor(resource: dict[str, Any]) -> dict[str, Any]:
        material = deepcopy(resource)
        material["schema_version"] = SCHEMA_VERSION
        material["version"] = "1.0.0"
        material["reference"] = f"{material['resource_id']}@{material['version']}"
        material["origin"] = "builtin"
        material["content_hash"] = sha256_digest(material)
        return material

    @staticmethod
    def _component(
        name: str,
        fields: list[str],
        output_ports: list[str],
        runtime_status: RuntimeStatus,
    ) -> dict[str, Any]:
        availability: Availability = (
            "requires_configuration"
            if name == "Agent"
            else "design_only"
            if runtime_status == "runtime_not_supported"
            else "ready"
        )
        return {
            "resource_id": f"veyra.component.{name.lower()}",
            "kind": "component",
            "name": name,
            "description": f"Platform-owned {name} graph component.",
            "availability": availability,
            "factory_selectable": True,
            "runtime_status": runtime_status,
            "required_permissions": deepcopy(_EMPTY_PERMISSIONS),
            "tags": ["graph", "builtin"],
            "spec": {"fields": fields, "output_ports": output_ports},
        }

    @staticmethod
    def _permissions(
        *,
        tools: list[str] | None = None,
        network_hosts: list[str] | None = None,
        filesystem_read_roots: list[str] | None = None,
        filesystem_write_roots: list[str] | None = None,
        shell_workspace_only: bool = False,
    ) -> dict[str, Any]:
        permission_tools = [
            (
                value
                if value.startswith("veyra.")
                else f"veyra.mcp.{value.removeprefix('mcp.')}"
                if value.startswith("mcp.")
                else f"veyra.tool.{value}"
            )
            for value in (tools or [])
        ]
        return {
            "network_hosts": list(network_hosts or []),
            "tools": permission_tools,
            "filesystem_read_roots": list(filesystem_read_roots or []),
            "filesystem_write_roots": list(filesystem_write_roots or []),
            "shell_workspace_only": shell_workspace_only,
        }

    @classmethod
    def _tool_resources(cls) -> list[dict[str, Any]]:
        selectable = (
            (
                "filesystem.read",
                "Filesystem Read",
                "Read a bounded Project path and return file contents.",
                cls._permissions(
                    tools=["filesystem.read"], filesystem_read_roots=["project"]
                ),
                {
                    "tool_name": "filesystem.read",
                    "approval_required": False,
                    "input_schema": {"path": "string"},
                    "output_schema": {"content": "string"},
                    "adapter": "veyra.runtime.filesystem.read",
                },
                "ready",
                True,
                "supported",
                ["filesystem", "local"],
            ),
            (
                "filesystem.write",
                "Filesystem Write",
                "Write inside a Project workspace. Approval is required by default.",
                cls._permissions(
                    tools=["filesystem.write"], filesystem_write_roots=["project"]
                ),
                {
                    "tool_name": "filesystem.write",
                    "approval_required": True,
                    "input_schema": {"path": "string", "content": "string"},
                    "output_schema": {"written": "boolean"},
                    "adapter": "veyra.runtime.filesystem.write",
                },
                "ready",
                True,
                "supported",
                ["filesystem", "approval"],
            ),
            (
                "shell.exec",
                "Workspace Shell",
                "Run a workspace-scoped command after approval.",
                cls._permissions(tools=["shell.exec"], shell_workspace_only=True),
                {
                    "tool_name": "shell.exec",
                    "approval_required": True,
                    "input_schema": {"command": "string"},
                    "output_schema": {"stdout": "string"},
                },
                "design_only",
                True,
                "runtime_not_supported",
                ["shell", "approval"],
            ),
            (
                "http.request",
                "HTTP Request",
                "Call an allowlisted HTTP host. Hosts are derived, never invented.",
                cls._permissions(tools=["http.request"]),
                {
                    "tool_name": "http.request",
                    "approval_required": False,
                    "input_schema": {"method": "string", "url": "string"},
                    "output_schema": {"status": "integer", "body": "string"},
                },
                "design_only",
                True,
                "runtime_not_supported",
                ["network"],
            ),
        )
        unavailable = (
            (
                "github.read",
                "GitHub Read",
                "Read GitHub issues or repositories after a GitHub adapter exists.",
                cls._permissions(
                    tools=["github.read"], network_hosts=["api.github.com"]
                ),
                {"tool_name": "github.read", "adapter": "missing"},
                "unavailable",
                False,
                "runtime_not_supported",
                ["github", "network"],
            ),
            (
                "github.write",
                "GitHub Write",
                "Write GitHub comments or issues after a GitHub adapter exists.",
                cls._permissions(
                    tools=["github.write"], network_hosts=["api.github.com"]
                ),
                {
                    "tool_name": "github.write",
                    "approval_required": True,
                    "adapter": "missing",
                },
                "unavailable",
                False,
                "runtime_not_supported",
                ["github", "approval"],
            ),
            (
                "browser.navigate",
                "Browser Navigate",
                "Navigate and read pages after the browser Runtime is stable.",
                cls._permissions(tools=["browser.navigate"]),
                {"tool_name": "browser.navigate", "adapter": "deferred"},
                "unavailable",
                False,
                "runtime_not_supported",
                ["browser"],
            ),
        )
        return [
            {
                "resource_id": f"veyra.tool.{slug}",
                "kind": "tool",
                "name": name,
                "description": description,
                "availability": availability,
                "factory_selectable": selectable_flag,
                "runtime_status": runtime_status,
                "required_permissions": permissions,
                "tags": tags,
                "spec": spec,
            }
            for (
                slug,
                name,
                description,
                permissions,
                spec,
                availability,
                selectable_flag,
                runtime_status,
                tags,
            ) in (*selectable, *unavailable)
        ]

    @classmethod
    def _mcp_resources(cls) -> list[dict[str, Any]]:
        return [
            {
                "resource_id": "veyra.mcp.call",
                "kind": "mcp_tool",
                "name": "MCP Call",
                "description": (
                    "Call a discovered MCP tool after a server is configured and "
                    "normalized into a Tool descriptor."
                ),
                "availability": "requires_configuration",
                "factory_selectable": False,
                "runtime_status": "runtime_not_configured",
                "required_permissions": cls._permissions(tools=["mcp.call"]),
                "spec": {
                    "tool_name": "mcp.call",
                    "discovery": "normalized_tool_required",
                    "credentials": "host_side",
                },
                "tags": ["mcp", "discovery"],
            }
        ]

    @staticmethod
    def _skill_resources() -> list[dict[str, Any]]:
        skills = (
            (
                "research-brief",
                "Research Brief",
                "Structure a bounded research brief with sources and open questions.",
                ["research", "instruction"],
                (
                    "State scope, evidence, findings, and open questions. Separate "
                    "what the provided material supports from what remains unknown. "
                    "Do not invent citations, URLs, or files."
                ),
            ),
            (
                "document-analyzer",
                "Document Analyzer",
                "Extract claims, decisions, risks, and traceable citations "
                "from documents.",
                ["document", "instruction"],
                (
                    "Separate quoted evidence from inference and uncertainty. Capture "
                    "decisions, owners, dates, numbers, and risks. If the source is "
                    "too long, keep only what the stated need requires."
                ),
            ),
            (
                "content-planner",
                "Content Planner",
                "Plan audience, outline, dependencies, review points, and "
                "success criteria.",
                ["planning", "instruction"],
                (
                    "Produce a reviewable plan before drafting or moving anything. "
                    "Include outline, dependencies, review points, and a done-when "
                    "check. Prefer a short plan the user can apply."
                ),
            ),
            (
                "need-extractor",
                "Need Extractor",
                "Distinguish the user's actual need from extra or generic information.",
                ["need", "instruction"],
                (
                    "Read the user's need before the source. Rank must-have answers, "
                    "nice-to-have context, and out-of-scope material. Prefer answering "
                    "the need over summarizing everything. Drop padding."
                ),
            ),
            (
                "evidence-ledger",
                "Evidence Ledger",
                "Keep claims tied to supplied evidence and mark gaps explicitly.",
                ["evidence", "instruction"],
                (
                    "Use only evidence present in the user message. Label each point "
                    "as quote, paraphrase, or inference. List missing facts and what "
                    "to collect next. Never fabricate sources."
                ),
            ),
            (
                "file-taxonomy",
                "File Taxonomy",
                "Propose folders, rename rules, and keep/archive candidates "
                "from a listing.",
                ["files", "instruction"],
                (
                    "Treat the listing as the only inventory. Propose a folder tree, "
                    "rename pattern, duplicate handling, and keep/archive/delete "
                    "candidates. Do not claim files were moved. Flag destructive "
                    "deletes. If the listing is incomplete, say so."
                ),
            ),
        )
        return [
            {
                "resource_id": f"veyra.skill.{slug}",
                "kind": "skill",
                "name": name,
                "description": description,
                "availability": "ready",
                "factory_selectable": True,
                "runtime_status": "runtime_not_configured",
                "required_permissions": deepcopy(_EMPTY_PERMISSIONS),
                "tags": tags,
                "spec": {"instruction": instruction},
            }
            for slug, name, description, tags, instruction in skills
        ]

    @staticmethod
    def _policy_resources() -> list[dict[str, Any]]:
        policies = (
            (
                "local-only",
                "Local Only",
                "Keep execution and data handling local.",
                {"network": "deny"},
            ),
            (
                "verification-required",
                "Verification Required",
                "Require verification before completion.",
                {"verification": "required"},
            ),
            (
                "external-write-requires-approval",
                "External Write Requires Approval",
                "Require approval for external writes.",
                {"external_write": "approval_required"},
            ),
        )
        return [
            {
                "resource_id": f"veyra.policy.{slug}",
                "kind": "policy",
                "name": name,
                "description": description,
                "availability": "ready",
                "factory_selectable": True,
                "runtime_status": "supported",
                "required_permissions": deepcopy(_EMPTY_PERMISSIONS),
                "tags": ["policy", "builtin"],
                "spec": spec,
            }
            for slug, name, description, spec in policies
        ]

    @staticmethod
    def _template_resources() -> list[dict[str, Any]]:
        graph = [
            "veyra.component.start@1.0.0",
            "veyra.component.agent@1.0.0",
            "veyra.component.output@1.0.0",
        ]
        templates = (
            (
                "starter-agent",
                "Starter Agent",
                "A safe local-first starting point for a new Agent.",
                "veyra.starter-agent@1.0.0",
                graph,
                (),
            ),
            (
                "document-distiller",
                "文档提炼",
                (
                    "把长文档或粘贴文本，提炼成你真正需要的结论、证据和待确认项。"
                    "不编造原文没有的事实。"
                ),
                "veyra.document-distiller@1.0.0",
                graph,
                (
                    "veyra.skill.document-analyzer@1.0.0",
                    "veyra.skill.need-extractor@1.0.0",
                ),
            ),
            (
                "question-researcher",
                "问题研究",
                (
                    "根据你的问题和已有材料，整理已知、未知、证据和下一步。"
                    "当前不会上网搜索，也不编造来源。"
                ),
                "veyra.question-researcher@1.0.0",
                graph,
                (
                    "veyra.skill.research-brief@1.0.0",
                    "veyra.skill.evidence-ledger@1.0.0",
                ),
            ),
            (
                "file-sort-planner",
                "文件整理",
                (
                    "根据文件清单给出分类、命名和目录方案。"
                    "当前不会真正移动、重命名或删除文件。"
                ),
                "veyra.file-sort-planner@1.0.0",
                graph,
                (
                    "veyra.skill.file-taxonomy@1.0.0",
                    "veyra.skill.content-planner@1.0.0",
                ),
            ),
        )
        return [
            {
                "resource_id": f"veyra.template.{slug}",
                "kind": "template",
                "name": name,
                "description": description,
                "availability": "ready",
                "factory_selectable": True,
                "runtime_status": "runtime_not_configured",
                "required_permissions": deepcopy(_EMPTY_PERMISSIONS),
                "tags": ["template", "forkable"],
                "spec": {
                    "template_id": template_id,
                    "component_references": list(components),
                    "skill_references": list(skills),
                },
            }
            for (
                slug,
                name,
                description,
                template_id,
                components,
                skills,
            ) in templates
        ]

    @staticmethod
    def _validate_kind(kind: str | None) -> None:
        if kind is not None and kind not in RESOURCE_KINDS:
            raise ResourceCatalogError(
                "invalid_resource_kind", "kind is not a catalog kind"
            )

    def _validate_availability(self, availability: str | None) -> None:
        if availability is not None and availability not in {
            resource["availability"] for resource in self._resources
        } | {"quarantined", "disabled", "unavailable"}:
            raise ResourceCatalogError(
                "invalid_resource_availability", "availability is not a catalog state"
            )
