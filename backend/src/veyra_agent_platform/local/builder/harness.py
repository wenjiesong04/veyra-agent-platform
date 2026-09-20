"""Bounded, metadata-only Project context shared by Builder adapters."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, NamedTuple

from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.local.projects.service import ProjectService
from veyra_agent_platform.local.resources import ResourceCatalog

from .prompt import BUILDER_SYSTEM_PROMPT

MAX_CONTEXT_BYTES = 400_000
BuilderMode = Literal["interview", "create_agent", "edit_source", "resolve_intent"]
ContextCategory = Literal[
    "conversation_recent_messages",
    "project_agents_metadata",
    "workflows_metadata",
    "knowledge_metadata",
    "project_resource_bindings",
    "catalog_capabilities",
    "project_files_metadata",
    "project_config",
]
ExcludedCategory = Literal[
    "knowledge_contents",
    "project_file_contents",
    "credentials",
    "secrets",
    "raw_runtime_events",
    "hidden_reasoning",
    "raw_prompts",
    "provider_response_bodies",
]

INCLUDED_CONTEXT_CATEGORIES: tuple[ContextCategory, ...] = (
    "conversation_recent_messages",
    "project_agents_metadata",
    "workflows_metadata",
    "knowledge_metadata",
    "project_resource_bindings",
    "catalog_capabilities",
    "project_files_metadata",
    "project_config",
)
EXCLUDED_CONTEXT_CATEGORIES: tuple[ExcludedCategory, ...] = (
    "knowledge_contents",
    "project_file_contents",
    "credentials",
    "secrets",
    "raw_runtime_events",
    "hidden_reasoning",
    "raw_prompts",
    "provider_response_bodies",
)


class SnapshotFacts(NamedTuple):
    project_hash: str
    catalog_hash: str
    context_size_bytes: int


class BuilderHarness:
    def __init__(self, projects: ProjectService, catalog: ResourceCatalog) -> None:
        self.projects = projects
        self.catalog = catalog

    def context_document(
        self,
        project_id: str,
        mode: BuilderMode,
        *,
        target: dict[str, Any] | None = None,
        conversation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
        return context

    def messages(
        self,
        project_id: str,
        mode: BuilderMode,
        *,
        target: dict[str, Any] | None = None,
        schema: dict[str, Any] | None = None,
        conversation: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        context = self.context_document(
            project_id, mode, target=target, conversation=conversation
        )
        encoded = json.dumps(context, ensure_ascii=False)
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

    def snapshot_facts(self, project_id: str, mode: BuilderMode) -> SnapshotFacts:
        context = self.context_document(project_id, mode)
        encoded = json.dumps(context, ensure_ascii=False)
        return SnapshotFacts(
            project_hash=canonical_json_hash(project_snapshot_projection(context)),
            catalog_hash=canonical_json_hash(
                catalog_snapshot_projection(context["resources"])
            ),
            context_size_bytes=len(encoded.encode("utf-8")),
        )


def canonical_json_hash(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def project_snapshot_projection(context: dict[str, Any]) -> dict[str, Any]:
    inventory = context.get("inventory") or {}
    return {
        "project": _pick(
            context.get("project") or {},
            ("project_id", "name", "description", "manifest_hash"),
        ),
        "agents": [_agent_projection(item) for item in inventory.get("agents") or []],
        "workflows": [
            _pick(
                item,
                (
                    "workflow_id",
                    "slug",
                    "name",
                    "description",
                    "version",
                    "source_file_hash",
                ),
            )
            | _graph_projection(item)
            for item in inventory.get("workflows") or []
        ],
        "knowledge": [
            _knowledge_projection(item) for item in inventory.get("knowledge") or []
        ],
        "project_bindings": list(context.get("project_bindings") or []),
        "files": [
            _pick(item, ("path", "kind", "byte_length", "agent_id"))
            for item in context.get("files") or []
        ],
    }


def catalog_snapshot_projection(
    resources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        _pick(
            item,
            (
                "reference",
                "kind",
                "name",
                "description",
                "availability",
                "runtime_status",
                "required_permissions",
                "factory_selectable",
                "content_hash",
                "origin",
                "component_class",
            ),
        )
        for item in resources
    ]


def _agent_projection(item: dict[str, Any]) -> dict[str, Any]:
    payload = _pick(
        item,
        ("agent_id", "slug", "name", "description", "version", "source_file_hash"),
    )
    origin = item.get("community_origin")
    if isinstance(origin, dict):
        payload["community_origin"] = _pick(
            origin, ("owner_handle", "slug", "version", "source_hash")
        )
    payload.update(_graph_projection(item))
    return payload


def _graph_projection(item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    draft = item.get("draft")
    if isinstance(draft, dict):
        payload["draft"] = _pick(draft, ("revision", "etag", "source_file_hash"))
    if "nodes" in item:
        payload["nodes"] = item["nodes"]
    if "transitions" in item:
        payload["transitions"] = item["transitions"]
    if "lock" in item:
        payload["lock"] = item["lock"]
    if "versions" in item:
        payload["versions"] = item["versions"]
    return payload


def _knowledge_projection(item: dict[str, Any]) -> dict[str, Any]:
    payload = _pick(
        item,
        (
            "knowledge_id",
            "slug",
            "name",
            "description",
            "version",
            "source_file_hash",
        ),
    )
    processing = item.get("processing")
    if isinstance(processing, dict):
        payload["index_status"] = processing.get("index_status")
        payload["chunk_count"] = processing.get("chunk_count")
    return payload


def _pick(item: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: item[key] for key in keys if key in item and item[key] is not None}
