"""Bounded, metadata-only Project context shared by Builder adapters."""

from __future__ import annotations

import json
from typing import Any, Literal

from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.local.projects.service import ProjectService
from veyra_agent_platform.local.resources import ResourceCatalog

from .prompt import BUILDER_SYSTEM_PROMPT

MAX_CONTEXT_BYTES = 400_000
BuilderMode = Literal["interview", "create_agent", "edit_source", "resolve_intent"]


class BuilderHarness:
    def __init__(self, projects: ProjectService, catalog: ResourceCatalog) -> None:
        self.projects = projects
        self.catalog = catalog

    def messages(
        self,
        project_id: str,
        mode: BuilderMode,
        *,
        target: dict[str, Any] | None = None,
        schema: dict[str, Any] | None = None,
        conversation: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        project = self.projects.project_summary(project_id)
        inventory = {
            kind: [
                {key: value for key, value in item.items() if key != "source_path"}
                for item in project.get(kind, [])
            ]
            for kind in ("agents", "workflows", "knowledge")
        }
        for kind in ("agent", "workflow"):
            reader = getattr(
                self.projects.repository,
                "draft" if kind == "agent" else "workflow_draft",
            )
            versions = getattr(self.projects.repository, f"{kind}_versions")
            for item in inventory[f"{kind}s"]:
                identity = item[f"{kind}_id"]
                draft = reader(identity)
                if draft is not None:
                    item["draft"] = {
                        key: draft[key]
                        for key in ("revision", "etag", "source_file_hash")
                    }
                    source = json.loads(draft["source_json"])
                    item["nodes"] = [
                        {
                            key: node[key]
                            for key in (
                                "id",
                                "component_type",
                                "agent_id",
                                "version_id",
                            )
                            if key in node
                        }
                        for node in source["nodes"]
                    ]
                    item["transitions"] = source["transitions"]
                    item["lock"] = source["lock"]
                item["versions"] = [
                    {
                        key: row[key]
                        for key in ("version_id", "source_hash", "behavior_hash")
                    }
                    for row in versions(identity)
                ]
        resources = self.catalog.factory_snapshot()
        for resource in resources:
            descriptor = self.catalog.by_reference(resource["reference"])
            resource.update(
                content_hash=descriptor["content_hash"],
                origin=descriptor["origin"],
                factory_selectable=descriptor["factory_selectable"],
            )
        context = {
            "scope": "project" if target is None else target["kind"],
            "operation": mode,
            "project": {
                key: project[key]
                for key in ("project_id", "name", "description", "manifest_hash")
            },
            "inventory": inventory,
            "project_bindings": [
                binding.to_dict()
                for binding in self.projects.project_resource_bindings(project_id)
            ],
            "files": self.projects.list_files(project_id)["files"],
            "resources": resources,
            "unselectable_resources": [
                {
                    key: item[key]
                    for key in ("reference", "kind", "availability", "runtime_status")
                }
                for item in self.catalog.resources()["resources"]
                if not item["factory_selectable"]
            ],
            "target": target,
            "conversation": conversation,
            "authority": {
                "writes": "explicit_confirmation_only",
                "file_contents": "not_loaded",
                "resource_creation": "not_supported_by_this_adapter",
                "multi_object_mutation": False,
                "runtime_host_configuration": "not_checked",
                "runtime_execution": "not_performed",
            },
        }
        encoded = json.dumps(context, ensure_ascii=False)
        if len(encoded.encode()) > MAX_CONTEXT_BYTES:
            raise ContractValidationError("Builder context exceeds the size limit")
        contract = {
            "interview": (
                "Ask one concise follow-up about goal, inputs, outputs, risks or "
                "success criteria. Do not ask users to learn internal node types."
            ),
            "create_agent": (
                "Return only an AgentSemanticPlanV1 JSON matching the supplied "
                "response schema. Describe the Agent's goal, inputs, outputs, "
                "steps and capability/knowledge intents. Do not emit resource "
                "hashes, Knowledge UUIDs, node IDs, canvas positions, "
                "source.lock, permission sets, or filesystem roots. The server "
                "compiles a canonical AgentBlueprint and reviews it before "
                "creation."
            ),
            "edit_source": (
                "Return only the complete candidate Source JSON. Change only the "
                "selected target to satisfy the request. The server derives the "
                "Proposal, Diff and Impact. Source schema: " + json.dumps(schema)
            ),
            "resolve_intent": (
                "Resolve the latest natural-language request using this Project and "
                "conversation. Return only JSON matching this schema: "
                + json.dumps(schema)
                + ". Distinguish create, edit, discuss and clarify. Questions and "
                "discussion are not edit commands. Do not invent a target or infer "
                "creation because a named target is absent. List ALL affected "
                "objects; cross-Agent handoffs are Workflow-level or multi-object "
                "work, never a silent single-Agent edit. A target mention must quote "
                "its name, slug or ID from user messages. Use basis=context only "
                "for an unambiguous reference to the current conversational/page "
                "target. If multiple objects could match, return clarify with a "
                "short question in the user's language; never choose the first or "
                "default Agent. A clarified reply must retain the original change "
                "in instruction. For create, set create_kind. Recognize Workflow "
                "and Resource creation even when the adapter cannot apply it. "
                "message explains your interpretation, not completed work. "
                "plan describes the candidate change, not authorization to write."
            ),
        }[mode]
        return [
            {"role": "system", "content": BUILDER_SYSTEM_PROMPT + "\n" + contract},
            {"role": "user", "content": encoded},
        ]
