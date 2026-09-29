"""Closed, deterministic executor for the initial V1 flow components."""

from __future__ import annotations

import json
import re
import threading
import time
from base64 import b64encode
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource, ComponentType, FlowNode
from veyra_agent_platform.contracts.canonical import file_hash, sha256_digest
from veyra_agent_platform.contracts.common import (
    SCHEMA_VERSION,
    ContractValidationError,
    IdempotencyKey,
    new_uuid7,
)
from veyra_agent_platform.contracts.condition import (
    TEMPLATE_TOKEN_RE,
    parse_condition_expression,
    resolve_value_path,
)
from veyra_agent_platform.contracts.custom_component import (
    CustomComponentDefinition,
    CustomComponentImplementationKind,
    CustomComponentReadiness,
)
from veyra_agent_platform.contracts.typed_io import (
    TypedField,
    artifact_id_from_value,
    looks_like_artifact_ref,
    looks_like_collection_ref,
    value_matches_field,
)
from veyra_agent_platform.contracts.workflow import WorkflowSource
from veyra_agent_platform.local.artifacts import ArtifactService
from veyra_agent_platform.local.artifacts.extract import (
    artifact_plain_text,
    extract_document,
)
from veyra_agent_platform.local.library.dependencies import (
    inspect_agent_dependencies,
)
from veyra_agent_platform.local.library.knowledge_context import read_knowledge_context
from veyra_agent_platform.local.library.service import LibraryService
from veyra_agent_platform.local.projects.custom_components import (
    CustomComponentError,
    CustomComponentService,
)
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService
from veyra_agent_platform.local.resources import ResourceCatalog, ResourceCatalogError
from veyra_agent_platform.local.resources.project import (
    ProjectResourceError,
    ProjectResourceService,
)
from veyra_agent_platform.local.resources.readiness import ResourceReadiness
from veyra_agent_platform.local.runtime.dataflow import DataflowStore
from veyra_agent_platform.local.storage.repositories import LocalRepository

from .agent_loop import AgentLoopRuntime, loop_tool_references
from .client import GeneratedImage, RuntimeModelClient, RuntimeProviderError
from .config import RuntimeSettings
from .conversations import AgentConversationService
from .credentials import (
    IMAGE_BINDING_SLOT,
    RUNTIME_BINDING_SLOT,
    ProviderCredentialStore,
    node_binding_slot,
)
from .model_capabilities import (
    RuntimeModelCapabilities,
    runtime_model_capabilities,
)
from .profiles import RuntimeApiProfile, RuntimeProfileStore
from .tools import ProducedArtifact, ToolAuthorization, ToolRuntime, ToolRuntimeError

PRIMARY_MODEL_REF = "model.primary"
IMAGE_MODEL_REF = "model.image"
MODEL_REF_SLOTS = {
    PRIMARY_MODEL_REF: RUNTIME_BINDING_SLOT,
    IMAGE_MODEL_REF: IMAGE_BINDING_SLOT,
}
_VISITS = "$visits"
_MAX_VALUE_CHARS = 24_000
_MAX_PREVIEW_CHARS = 4_000
_MAX_PROMPT_IMAGES = 8
_MAX_COMMENT_CHARS = 4_000
_MAX_IMAGES_PER_STEP = 4


class _RunAbandoned(Exception):
    """The run left the running state before the executor could finish."""


class RuntimeError(ProjectError):
    """A typed terminal runtime failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.events: list[tuple[str | None, str, dict[str, Any]]] = []
        self.tool_calls: tuple[_ToolCallRecord, ...] = ()


@dataclass(frozen=True)
class _ToolCallRecord:
    node_id: str
    tool_reference: str
    authorization: str
    decision_code: str
    decision_reason: str
    input_digest: str
    receipt: dict[str, Any] | None


@dataclass(frozen=True)
class _ExecutionPause:
    node_id: str
    prompt: str
    values: dict[str, Any]
    events: list[tuple[str | None, str, dict[str, Any]]]
    tool_calls: tuple[_ToolCallRecord, ...]
    details: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class _ExecutionOutcome:
    events: list[tuple[str | None, str, dict[str, Any]]]
    tool_calls: tuple[_ToolCallRecord, ...]
    result: dict[str, Any] | None
    verified: bool
    pause: _ExecutionPause | None


class RuntimeService(AgentLoopRuntime):
    def __init__(
        self,
        repository: LocalRepository,
        projects: ProjectService,
        library: LibraryService,
        model: RuntimeModelClient | None = None,
        tools: ToolRuntime | None = None,
        profiles: RuntimeProfileStore | None = None,
        conversations: AgentConversationService | None = None,
        project_resources: ProjectResourceService | None = None,
        resource_readiness: ResourceReadiness | None = None,
        artifacts: ArtifactService | None = None,
        custom_components: CustomComponentService | None = None,
        credentials: ProviderCredentialStore | None = None,
    ) -> None:
        self.repository, self.projects, self.library = repository, projects, library
        self.model = model or RuntimeModelClient(RuntimeSettings())
        self.tools = tools or ToolRuntime(ResourceCatalog())
        self.custom_components = custom_components or CustomComponentService(
            projects, self.tools.catalog
        )
        self.project_resources = project_resources or ProjectResourceService(
            projects, self.tools.catalog, self.custom_components
        )
        self.profiles = profiles or RuntimeProfileStore(repository)
        self.credentials = credentials
        self.resource_readiness = resource_readiness or ResourceReadiness(
            self.tools.catalog,
            self.model,
            self.tools._adapters.keys(),
            self.tools.mcp,
            model_configured=self._runtime_model_configured,
        )
        self.conversations = conversations
        self.artifacts = artifacts or ArtifactService(repository, projects.object_root)
        self.custom_components.project_resource_readiness = (
            self.resource_readiness.project
        )
        self.custom_components.model_recipe_configured = self._runtime_model_configured
        self.repository.interrupt_orphan_runs()

    def _runtime_model_configured(self) -> bool:
        if self.credentials is not None:
            return (
                any(item.readiness == "ready" for item in self.credentials.list())
                or self.model.transport is not None
            )
        return bool(self.model.configured)

    def status(self) -> dict[str, Any]:
        payload = self.model.status()
        if self.credentials is not None:
            payload["configured"] = self._runtime_model_configured()
            payload["allow_process_environment_key"] = False
            payload["user_provided_only"] = True
        payload["modalities"] = runtime_model_capabilities(
            self.model.settings
        ).to_dict()
        return payload

    def builder_runtime_preflight(self, project_id: str) -> dict[str, Any]:
        """Return the durable Builder gate without contacting a Provider."""
        if self.credentials is None:
            return {
                "status": "ready",
                "credentials": [],
                "binding_slot": "primary_model",
            }
        credentials = [
            item.to_dict()
            for item in self.credentials.list()
            if item.readiness == "ready"
        ]
        return {
            "status": "waiting_for_runtime_binding"
            if credentials
            else "waiting_for_runtime_credential",
            "credentials": credentials,
            "binding_slot": "primary_model",
            "project_id": project_id,
        }

    def validate_profile(self, profile: RuntimeApiProfile) -> dict[str, Any]:
        """Validate a supplied profile without persisting it or running a prompt."""
        settings = self.model.settings.model_copy(
            update={
                "model_base_url": profile.base_url,
                "model_id": profile.model_id,
                "model_api_key_env": profile.api_key_env,
            }
        )
        client = RuntimeModelClient(
            settings,
            transport=self.model.transport,
            secret_store=self.model.secret_store,
        )
        try:
            client.validate()
        except RuntimeProviderError as exc:
            return {
                "schema_version": SCHEMA_VERSION,
                "valid": False,
                "configured": exc.code != "runtime_not_configured",
                "model_available": False,
                "provider": profile.provider,
                "base_url": profile.base_url,
                "model_id": profile.model_id,
                "api_key_env": profile.api_key_env,
                "code": exc.code,
                "message": str(exc),
            }
        return {
            "schema_version": SCHEMA_VERSION,
            "valid": True,
            "configured": True,
            "model_available": True,
            "provider": profile.provider,
            "base_url": profile.base_url,
            "model_id": profile.model_id,
            "api_key_env": profile.api_key_env,
            "code": "validated",
            "message": (
                "Runtime model credentials and model availability were verified."
            ),
        }

    def readiness(
        self, project_id: str, agent_id: str, *, version_id: str | None = None
    ) -> dict[str, Any]:
        """Return a no-effect startup preflight for one effective Agent Runtime."""
        self.library._agent_in_project(project_id, agent_id)
        if version_id:
            version = self.repository.version(version_id)
            if (
                version is None
                or version["agent_id"] != agent_id
                or not int(version["committed"] or 0)
            ):
                raise RuntimeError(
                    "agent_version_not_found", "Committed Agent version not found"
                )
            source = AgentSource.from_dict(json.loads(version["source_json"]))
            report = self.readiness_for_source(project_id, agent_id, source)
            report["version_id"] = version_id
            return report
        agent = self.library._agent_in_project(project_id, agent_id)
        source_path = self.library._source_path(project_id, agent)
        source_text = self.projects._read_text(source_path)
        source = AgentSource.from_dict(
            self.projects._parse_yaml(source_text, agent["slug"])
        )
        return self.readiness_for_source(project_id, agent_id, source)

    def readiness_for_source(
        self, project_id: str, agent_id: str, source: AgentSource
    ) -> dict[str, Any]:
        """Preflight a current draft or an immutable Agent snapshot.

        Workflow AgentCall nodes execute pinned snapshots.  Keeping this
        source-based variant separate from ``readiness`` prevents a Workflow
        preflight from accidentally inspecting an Agent's newer mutable draft.
        It is deliberately non-mutating and never calls the model provider.
        """
        if source.agent_id != agent_id:
            raise RuntimeError(
                "source_identity_invalid",
                "source identity does not match requested Agent",
            )
        dependencies = inspect_agent_dependencies(
            self.projects, self.tools.catalog, project_id, source
        )
        model = self._model_for(project_id, agent_id)
        model_status = model.status()
        requires_model = self._source_requires_model(project_id, source)
        model_ready = not requires_model or bool(model_status["configured"])
        model_detail = (
            "No model node is present in this Agent."
            if not requires_model
            else (
                "Effective Runtime model credentials are available."
                if model_ready
                else "Effective Runtime model credentials are not configured."
            )
        )
        if self.credentials is not None:
            resolved = self.credentials.effective_credential(project_id, agent_id)
            raw_source = resolved[1].source if resolved else "default"
        else:
            _, raw_source = self.profiles.effective(project_id, agent_id)
        profile_source = _readiness_profile_source(raw_source)
        tool_checks = self._tool_readiness(project_id, source)
        for missing in self._missing_tool_secrets(source):
            tool_checks.append(missing)
        tools_ready = all(item["ready"] for item in tool_checks)
        secret_gap = any(
            item.get("code") == "needs_configuration" for item in tool_checks
        )
        tools_code = (
            "ready"
            if tools_ready
            else "needs_configuration"
            if secret_gap
            else "tool_runtime_unavailable"
        )
        tools_detail = (
            "Tool Runtime authorization preflight passed."
            if tools_ready
            else (
                "This Agent needs configuration before it can run."
                if secret_gap
                else "One or more Tools cannot pass Runtime authorization."
            )
        )
        modalities = runtime_model_capabilities(model.settings)
        modality_check = _runtime_modality_readiness(source, requires_model, modalities)
        checks = [
            {
                "id": "dependencies",
                "ready": bool(dependencies["runtime_ready"]),
                "code": "ready"
                if dependencies["runtime_ready"]
                else "dependency_attention",
                "detail": (
                    "All Agent dependencies are resolved."
                    if dependencies["runtime_ready"]
                    else "One or more Agent dependencies need attention."
                ),
            },
            {
                "id": "model",
                "ready": model_ready,
                "code": "ready" if model_ready else "runtime_not_configured",
                "detail": model_detail,
            },
            {
                "id": "modalities",
                **modality_check,
            },
            {
                "id": "tools",
                "ready": tools_ready,
                "code": tools_code,
                "detail": tools_detail,
            },
        ]
        if _uses_image_model(source):
            image_model = self._model_for(project_id, agent_id, IMAGE_BINDING_SLOT)
            image_ready = bool(image_model.status()["configured"])
            checks.append(
                {
                    "id": "image_model",
                    "ready": image_ready,
                    "code": "ready" if image_ready else "image_model_not_configured",
                    "detail": (
                        f"Image model {image_model.settings.model_id} is bound."
                        if image_ready
                        else "Bind an image generation model for the image steps."
                    ),
                }
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "project_id": project_id,
            "agent_id": agent_id,
            "ready": all(item["ready"] for item in checks),
            "profile_source": profile_source,
            "model": {
                "required": requires_model,
                "configured": bool(model_status["configured"]),
                "model_id": model_status["model_id"],
                "model_base_url": model_status["model_base_url"],
                "model_api_key_env": model_status["model_api_key_env"],
                "modalities": modalities.to_dict(),
            },
            "dependency_summary": dependencies["dependency_summary"],
            "dependencies": dependencies["dependencies"],
            "tool_checks": tool_checks,
            "checks": checks,
        }

    def _authorize_tool(
        self,
        project_id: str,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
    ) -> ToolAuthorization:
        if node.uses is None:
            return self.tools.authorize(source=source, node=node, values=values)
        try:
            resource = self.project_resources.resolve_pin(
                project_id, node.uses, source.lock.get(node.uses)
            )
        except ProjectResourceError as exc:
            return self.tools._denied(node.uses, exc.code, str(exc), values)
        return self.tools.authorize(
            source=source,
            node=node,
            values=values,
            resource=self.resource_readiness.project(resource),
        )

    def _tool_readiness(
        self, project_id: str, source: AgentSource
    ) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        for node in source.nodes:
            if node.component_type is ComponentType.TOOL:
                authorization = self._authorize_tool(project_id, source, node, {})
                ready = authorization.decision == "allowed"
                checks.append(
                    {
                        "node_id": node.id,
                        "reference": node.uses or "tool_reference_missing",
                        "ready": ready,
                        "code": authorization.code,
                        "detail": authorization.reason,
                    }
                )
                continue
            if node.component_type is not ComponentType.CUSTOM_COMPONENT:
                continue
            try:
                definition = self._resolve_custom_component(project_id, source, node)
            except RuntimeError as exc:
                checks.append(
                    {
                        "node_id": node.id,
                        "reference": node.uses or "component_reference_missing",
                        "ready": False,
                        "code": exc.code,
                        "detail": str(exc),
                    }
                )
                continue
            if (
                definition.implementation.kind
                is CustomComponentImplementationKind.COMPOSITE_GRAPH
            ):
                checks.append(
                    {
                        "node_id": node.id,
                        "reference": node.uses or definition.ref(),
                        "ready": False,
                        "code": "design_only",
                        "detail": "composite_graph Custom Components are design-only",
                    }
                )
                continue
            if (
                definition.implementation.kind
                is CustomComponentImplementationKind.TOOL_WRAPPER
            ):
                authorization = self._authorize_wrapped_tool(
                    project_id, source, node, definition, {}
                )
                checks.append(
                    {
                        "node_id": node.id,
                        "reference": node.uses or definition.ref(),
                        "ready": authorization.decision == "allowed",
                        "code": authorization.code,
                        "detail": authorization.reason,
                    }
                )
                continue
            if (
                definition.implementation.kind
                is CustomComponentImplementationKind.MODEL_RECIPE
            ):
                model = self._model_for(project_id, source.agent_id)
                configured = bool(model.status()["configured"])
                ready = (
                    definition.readiness is CustomComponentReadiness.READY
                    and configured
                )
                code = (
                    "ready"
                    if ready
                    else "runtime_not_configured"
                    if not configured
                    else definition.readiness.value
                )
                detail = (
                    "Custom Component is ready on the effective Agent Runtime."
                    if ready
                    else "Configure the effective Agent Runtime model before use."
                    if not configured
                    else f"Custom Component is {definition.readiness.value}"
                )
                checks.append(
                    {
                        "node_id": node.id,
                        "reference": node.uses or definition.ref(),
                        "ready": ready,
                        "code": code,
                        "detail": detail,
                    }
                )
                continue
            checks.append(
                {
                    "node_id": node.id,
                    "reference": node.uses or definition.ref(),
                    "ready": definition.readiness is CustomComponentReadiness.READY,
                    "code": definition.readiness.value,
                    "detail": f"Custom Component is {definition.readiness.value}",
                }
            )
        return checks

    def _require_runtime_modalities(
        self, project_id: str, agent_id: str, source: AgentSource
    ) -> None:
        model = self._model_for(project_id, agent_id)
        requires_model = self._source_requires_model(project_id, source)
        check = _runtime_modality_readiness(
            source,
            requires_model,
            runtime_model_capabilities(model.settings),
        )
        if not check["ready"]:
            raise RuntimeError(str(check["code"]), str(check["detail"]))
        if (
            _uses_image_model(source)
            and not self._model_for(project_id, agent_id, IMAGE_BINDING_SLOT).configured
        ):
            raise RuntimeError(
                "image_model_not_configured",
                "Bind an image generation model to this Agent before running it",
            )

    def components(self) -> dict[str, Any]:
        from veyra_agent_platform.local.components import component_registry

        return {"schema_version": SCHEMA_VERSION, "components": component_registry()}

    def run(
        self,
        project_id: str,
        agent_id: str,
        inputs: dict[str, Any],
        idempotency_key: str,
        conversation_id: str | None = None,
        append_user: bool = True,
        *,
        source: str = "draft",
        version_id: str | None = None,
    ) -> dict[str, Any]:
        if source == "committed" or version_id:
            return self.run_committed(
                project_id,
                agent_id,
                inputs,
                idempotency_key,
                conversation_id=conversation_id,
                version_id=version_id,
                append_user=append_user,
            )
        return self._run_draft(
            project_id,
            agent_id,
            inputs,
            idempotency_key,
            conversation_id=conversation_id,
            append_user=append_user,
        )

    def _run_draft(
        self,
        project_id: str,
        agent_id: str,
        inputs: dict[str, Any],
        idempotency_key: str,
        conversation_id: str | None = None,
        append_user: bool = True,
    ) -> dict[str, Any]:
        IdempotencyKey(SCHEMA_VERSION, idempotency_key)
        agent = self.library._agent_in_project(project_id, agent_id)
        source_path = self.library._source_path(project_id, agent)
        source_text = self.projects._read_text(source_path)
        source = AgentSource.from_dict(
            self.projects._parse_yaml(source_text, agent["slug"])
        )
        if source.agent_id != agent_id:
            raise RuntimeError(
                "source_identity_invalid",
                "source identity does not match requested Agent",
            )
        inputs = self._prepare_inputs(project_id, source, inputs)
        self._require_runtime_modalities(project_id, agent_id, source)
        fingerprint = file_hash(source_text)
        scope = f"run:{project_id}:{agent_id}"
        digest = sha256_digest(
            {
                "file_hash": fingerprint,
                "inputs": inputs,
                "conversation_id": conversation_id,
            }
        )
        with self.repository.transaction() as connection:
            replay = self.repository.idempotent_response(
                connection, scope, idempotency_key, digest
            )
            if replay is not None:
                return replay
            draft = connection.execute(
                "SELECT source_file_hash FROM agent_drafts WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
            if draft is None or draft["source_file_hash"] != fingerprint:
                raise RuntimeError(
                    "source_changed",
                    "source changed outside Studio; reload it before running",
                )
            version = self.repository.version_by_fingerprint(
                connection, agent_id, fingerprint
            )
            if version is None:
                version_id = new_uuid7()
                self.repository.insert_version(
                    connection,
                    {
                        "version_id": version_id,
                        "agent_id": agent_id,
                        "source_hash": source.source_hash,
                        "behavior_hash": source.behavior_hash,
                        "lock_hash": source.lock_hash,
                        "file_hash": fingerprint,
                        "source": source.to_dict(),
                        "source_text": source_text,
                        "created_at": _now(),
                    },
                )
                self.repository.attach_file_to_version(
                    connection,
                    version_id=version_id,
                    project_id=project_id,
                    relative_path=agent["source_path"],
                )
            else:
                version_id = version["version_id"]
            run_id = new_uuid7()
            conversation_context = ""
            resolved_conversation_id = conversation_id
            if self.conversations is not None and (conversation_id or append_user):
                resolved_conversation_id, conversation_context = (
                    self.conversations.prepare_turn(
                        connection,
                        project_id=project_id,
                        agent_id=agent_id,
                        conversation_id=conversation_id,
                        inputs=inputs,
                        run_id=run_id,
                        append_user=append_user,
                    )
                )
            elif conversation_id:
                raise RuntimeError(
                    "conversation_unavailable",
                    "Agent conversation service is unavailable",
                )
            self.repository.create_run(
                connection,
                run_id=run_id,
                project_id=project_id,
                agent_id=agent_id,
                version_id=version_id,
                created_at=_now(),
                inputs=inputs,
                conversation_id=resolved_conversation_id,
            )
            self.repository.add_run_events(
                connection,
                run_id,
                [(None, "run.created", {}), (None, "run.started", {})],
            )
            started = self._row_payload(
                connection.execute(
                    "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
            )
            self.repository.remember_response(
                connection, scope, idempotency_key, digest, started
            )
        self._schedule_execution(
            run_id,
            lambda: self._complete_execution(
                project_id,
                run_id,
                source,
                inputs,
                start_node=None,
                approved=False,
                conversation_id=resolved_conversation_id,
                conversation_context=conversation_context,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            ),
        )
        return started

    def run_committed(
        self,
        project_id: str,
        agent_id: str,
        inputs: dict[str, Any],
        idempotency_key: str,
        *,
        version_id: str | None = None,
        conversation_id: str | None = None,
        append_user: bool = True,
    ) -> dict[str, Any]:
        """Execute a committed Agent version. Never reads the current draft."""

        IdempotencyKey(SCHEMA_VERSION, idempotency_key)
        self.library._agent_in_project(project_id, agent_id)
        version = self._resolve_committed_version(
            project_id, agent_id, version_id, conversation_id
        )
        source = AgentSource.from_dict(json.loads(version["source_json"]))
        if source.agent_id != agent_id or source.source_hash != version["source_hash"]:
            raise RuntimeError(
                "agent_version_invalid", "Agent version integrity check failed"
            )
        if conversation_id and self.conversations is not None:
            stored = self.conversations.initial_inputs(
                project_id, agent_id, conversation_id
            )
            if stored:
                inputs = {**stored, **inputs}
        inputs = self._prepare_inputs(project_id, source, inputs)
        self._require_runtime_modalities(project_id, agent_id, source)
        self._require_app_preflight(project_id, agent_id, source)
        version_id = version["version_id"]
        persist_initial = bool(
            conversation_id is None
            or (
                self.conversations is not None
                and not self.conversations.initial_inputs(
                    project_id, agent_id, conversation_id
                )
            )
        )
        scope = f"run-committed:{project_id}:{agent_id}:{version_id}"
        digest = sha256_digest(
            {
                "version_id": version_id,
                "inputs": inputs,
                "conversation_id": conversation_id,
            }
        )
        with self.repository.transaction() as connection:
            replay = self.repository.idempotent_response(
                connection, scope, idempotency_key, digest
            )
            if replay is not None:
                return replay
            run_id = new_uuid7()
            conversation_context = ""
            resolved_conversation_id = conversation_id
            if self.conversations is not None and (conversation_id or append_user):
                resolved_conversation_id, conversation_context = (
                    self.conversations.prepare_turn(
                        connection,
                        project_id=project_id,
                        agent_id=agent_id,
                        conversation_id=conversation_id,
                        inputs=inputs,
                        run_id=run_id,
                        append_user=append_user,
                        agent_version_id=version_id,
                        persist_initial_inputs=persist_initial,
                    )
                )
            elif conversation_id:
                raise RuntimeError(
                    "conversation_unavailable",
                    "Agent conversation service is unavailable",
                )
            self.repository.create_run(
                connection,
                run_id=run_id,
                project_id=project_id,
                agent_id=agent_id,
                version_id=version_id,
                created_at=_now(),
                inputs=inputs,
                conversation_id=resolved_conversation_id,
            )
            self.repository.add_run_events(
                connection,
                run_id,
                [(None, "run.created", {}), (None, "run.started", {})],
            )
            started = self._row_payload(
                connection.execute(
                    "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
            )
            self.repository.remember_response(
                connection, scope, idempotency_key, digest, started
            )
        self._schedule_execution(
            run_id,
            lambda: self._complete_execution(
                project_id,
                run_id,
                source,
                inputs,
                start_node=None,
                approved=False,
                conversation_id=resolved_conversation_id,
                conversation_context=conversation_context,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            ),
        )
        return started

    def _resolve_committed_version(
        self,
        project_id: str,
        agent_id: str,
        version_id: str | None,
        conversation_id: str | None,
    ) -> Any:
        pinned: str | None = None
        if conversation_id and self.conversations is not None:
            pinned = self.conversations.conversation_version(
                project_id, agent_id, conversation_id
            )
            if pinned and version_id and pinned != version_id:
                raise RuntimeError(
                    "conversation_version_mismatch",
                    "This conversation is pinned to a different Agent version",
                )
            if pinned:
                version_id = pinned
        if not version_id:
            latest = self.repository.latest_committed_version(agent_id)
            if latest is None:
                raise RuntimeError(
                    "agent_has_no_committed_version",
                    "This Agent has no runnable version yet. "
                    "Commit a version in Studio before using it.",
                )
            version_id = str(latest["version_id"])
        version = self.repository.version(version_id)
        if (
            version is None
            or version["agent_id"] != agent_id
            or not int(version["committed"] or 0)
        ):
            raise RuntimeError(
                "agent_version_not_found", "Committed Agent version not found"
            )
        return version

    def _require_app_preflight(
        self, project_id: str, agent_id: str, source: AgentSource
    ) -> None:
        report = self.readiness_for_source(project_id, agent_id, source)
        model = report.get("model") or {}
        if model.get("required") and not model.get("configured"):
            raise RuntimeError(
                "runtime_not_configured", "Runtime model is not configured."
            )
        for dependency in report.get("dependencies") or []:
            status = str(dependency.get("status") or "")
            detail = str(dependency.get("detail") or "")
            if status == "configuration_required":
                raise RuntimeError(
                    "needs_configuration",
                    detail or "This Agent needs configuration before it can run.",
                )
            if status == "resource_unbound":
                raise RuntimeError(
                    "resource_unbound",
                    detail or "A required resource is not bound to this Project.",
                )
            if status in {"lock_mismatch", "project_binding_stale"}:
                raise RuntimeError(
                    "resource_identity_conflict",
                    detail or "Pinned resource identity does not match this Agent.",
                )
        missing = self._missing_tool_secrets(source)
        if missing:
            raise RuntimeError(
                "needs_configuration",
                str(missing[0]["detail"]),
            )

    def _missing_tool_secrets(self, source: AgentSource) -> list[dict[str, Any]]:
        from veyra_agent_platform.local.secrets import resolve_secret

        missing: list[dict[str, Any]] = []
        seen: set[str] = set()
        references: list[tuple[str, str]] = []
        for node in source.nodes:
            if node.component_type is not ComponentType.TOOL or not node.uses:
                continue
            if node.uses in seen:
                continue
            seen.add(node.uses)
            references.append((node.id, node.uses))
        for reference in loop_tool_references(source):
            if reference in seen:
                continue
            seen.add(reference)
            references.append(("capability", reference))
        for node_id, reference in references:
            try:
                resource = self.tools.catalog.by_reference(reference)
            except Exception:
                continue
            spec = resource.get("spec") if isinstance(resource, dict) else {}
            if not isinstance(spec, dict):
                continue
            secret_ref = spec.get("secret_ref")
            secret_env = spec.get("secret_env")
            if not isinstance(secret_ref, str) or not secret_ref:
                continue
            token = resolve_secret(
                self.tools._secret_store,
                secret_ref,
                secret_env if isinstance(secret_env, str) else "",
            )
            if token:
                continue
            identity = reference.split("@", 1)[0]
            detail = (
                "This Agent needs configuration before it can run. "
                "GitHub connection required."
                if "github" in identity
                else (
                    "This Agent needs configuration before it can run. "
                    "A required integration is not configured."
                )
            )
            missing.append(
                {
                    "node_id": node_id,
                    "reference": reference,
                    "ready": False,
                    "code": "needs_configuration",
                    "detail": detail,
                }
            )
        return missing

    def run_version(
        self,
        project_id: str,
        agent_id: str,
        version_id: str,
        inputs: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Execute a pinned snapshot without inspecting or changing its draft."""
        IdempotencyKey(SCHEMA_VERSION, idempotency_key)
        self.library._agent_in_project(project_id, agent_id)
        version = self.repository.version(version_id)
        if version is None or version["agent_id"] != agent_id:
            raise RuntimeError(
                "agent_version_not_found", "Committed Agent version not found"
            )
        source = AgentSource.from_dict(json.loads(version["source_json"]))
        if source.agent_id != agent_id or source.source_hash != version["source_hash"]:
            raise RuntimeError(
                "agent_version_invalid", "Agent version integrity check failed"
            )
        inputs = self._prepare_inputs(project_id, source, inputs)
        self._require_runtime_modalities(project_id, agent_id, source)
        scope = f"run-version:{project_id}:{agent_id}:{version_id}"
        digest = sha256_digest({"version_id": version_id, "inputs": inputs})
        with self.repository.transaction() as connection:
            replay = self.repository.idempotent_response(
                connection, scope, idempotency_key, digest
            )
            if replay is not None:
                return replay
            run_id = new_uuid7()
            self.repository.create_run(
                connection,
                run_id=run_id,
                project_id=project_id,
                agent_id=agent_id,
                version_id=version_id,
                created_at=_now(),
                inputs=inputs,
            )
            self.repository.add_run_events(
                connection,
                run_id,
                [(None, "run.created", {}), (None, "run.started", {})],
            )
            started = self._row_payload(
                connection.execute(
                    "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
            )
            self.repository.remember_response(
                connection, scope, idempotency_key, digest, started
            )
        self._schedule_execution(
            run_id,
            lambda: self._complete_execution(
                project_id,
                run_id,
                source,
                inputs,
                start_node=None,
                approved=False,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            ),
        )
        return started

    def command(
        self,
        project_id: str,
        agent_id: str,
        run_id: str,
        command: str,
        idempotency_key: str,
        *,
        checkpoint_id: str | None = None,
        comment: str | None = None,
    ) -> dict[str, Any]:
        IdempotencyKey(SCHEMA_VERSION, idempotency_key)
        self.library._agent_in_project(project_id, agent_id)
        row = self.repository.run(run_id)
        if (
            row is None
            or row["agent_id"] != agent_id
            or row["project_id"] != project_id
        ):
            raise ProjectError("unknown Agent run")
        if command not in {"approve", "reject", "stop", "resume", "retry"}:
            raise RuntimeError("command_invalid", "Unsupported run command")
        note = (comment or "").strip()
        if note and command not in {"approve", "reject"}:
            raise RuntimeError(
                "command_invalid", "Only Approve and Reject accept a comment"
            )
        if len(note) > _MAX_COMMENT_CHARS:
            raise RuntimeError(
                "command_invalid",
                f"Approval comments are limited to {_MAX_COMMENT_CHARS} characters",
            )
        scope = f"run-command:{run_id}"
        digest = sha256_digest({"command": command})
        if note:
            digest = sha256_digest({"command": command, "comment": note})
        if checkpoint_id is not None:
            if command != "resume":
                raise RuntimeError(
                    "command_invalid", "Only Resume accepts a checkpoint"
                )
            digest = sha256_digest({"command": command, "checkpoint_id": checkpoint_id})
        with self.repository.transaction() as connection:
            replay = self.repository.idempotent_response(
                connection, scope, idempotency_key, digest
            )
            if replay is not None:
                return replay
        if command == "retry":
            return self._retry_run(
                row, scope=scope, idempotency_key=idempotency_key, digest=digest
            )
        if command == "stop":
            return self._stop_run(
                row, scope=scope, idempotency_key=idempotency_key, digest=digest
            )
        if command == "resume":
            return self._resume_run(
                row,
                checkpoint_id=checkpoint_id,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            )
        return self._resolve_approval(
            row,
            decision="approved" if command == "approve" else "rejected",
            comment=note,
            scope=scope,
            idempotency_key=idempotency_key,
            digest=digest,
        )

    def runs(self, project_id: str, agent_id: str) -> dict[str, Any]:
        self.library._agent_in_project(project_id, agent_id)
        return {
            "schema_version": SCHEMA_VERSION,
            "runs": [self._row_payload(row) for row in self.repository.runs(agent_id)],
        }

    def run_detail(self, project_id: str, agent_id: str, run_id: str) -> dict[str, Any]:
        self.library._agent_in_project(project_id, agent_id)
        row = self.repository.run(run_id)
        if (
            row is None
            or row["agent_id"] != agent_id
            or row["project_id"] != project_id
        ):
            raise ProjectError("unknown Agent run")
        payload = self._row_payload(row)
        payload["events"] = self.repository.run_events(run_id)
        return payload

    def ensure_run(self, project_id: str, agent_id: str, run_id: str) -> None:
        self.run_detail(project_id, agent_id, run_id)

    def follow_events(self, run_id: str, after: int) -> Iterator[str]:
        last = after
        while True:
            events = self.repository.run_events_after(run_id, last)
            for event in events:
                last = int(event["sequence"])
                yield _sse_frame("runtime", event, event_id=str(last))
            row = self.repository.run(run_id)
            if row is None:
                raise ProjectError("unknown Agent run")
            if row["status"] not in {"running", "waiting"} and not events:
                yield _sse_frame("done", {"status": row["status"]})
                return
            if not events:
                time.sleep(0.05)

    def _persist_event(
        self,
        run_id: str,
        node_id: str | None,
        kind: str,
        payload: dict[str, Any],
    ) -> None:
        with self.repository.transaction() as connection:
            if kind == "tool.started":
                row = connection.execute(
                    "SELECT status FROM runtime_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                if row is None or row["status"] != "running":
                    raise _RunAbandoned()
            self.repository.add_run_events(
                connection, run_id, [(node_id, kind, _json_safe_payload(payload))]
            )

    def _commit_outcome(
        self,
        run_id: str,
        outcome: _ExecutionOutcome,
        *,
        scope: str | None,
        idempotency_key: str | None,
        digest: str | None,
        conversation_id: str | None = None,
        extra_events: list[tuple[str | None, str, dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        if not self._is_running(run_id) and outcome.pause is None:
            return self._run_response(run_id)
        if outcome.pause is not None:
            return self._pause_run(
                run_id,
                _ExecutionPause(
                    node_id=outcome.pause.node_id,
                    prompt=outcome.pause.prompt,
                    values=outcome.pause.values,
                    events=[],
                    tool_calls=outcome.pause.tool_calls,
                    details=outcome.pause.details,
                ),
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            )
        with self.repository.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row["status"] != "running":
                return self._row_payload(row)
            self.repository.add_run_events(connection, run_id, list(extra_events or []))
            self._store_tool_calls(connection, run_id, outcome.tool_calls)
            final_status = "verified" if outcome.verified else "unverified"
            self.repository.add_run_events(
                connection,
                run_id,
                [(None, "run.completed", {"state": final_status})],
            )
            self.repository.finish_run(
                connection,
                run_id,
                status=final_status,
                result=outcome.result,
                code=None,
                message=None,
                finished_at=_now(),
            )
            if conversation_id and outcome.result is not None and self.conversations:
                self.conversations.append_assistant(
                    connection,
                    conversation_id=conversation_id,
                    run_id=run_id,
                    result=outcome.result,
                )
            return self._stored_run_response(
                connection,
                run_id,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            )

    def _fail_run(
        self,
        run_id: str,
        exc: RuntimeError,
        *,
        scope: str | None,
        idempotency_key: str | None,
        digest: str | None,
    ) -> dict[str, Any]:
        if not self._is_running(run_id):
            return self._run_response(run_id)
        with self.repository.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row["status"] != "running":
                return self._row_payload(row)
            self.repository.add_run_events(
                connection,
                run_id,
                [(None, "run.failed", {"code": exc.code})],
            )
            self._store_tool_calls(connection, run_id, exc.tool_calls)
            self.repository.finish_run(
                connection,
                run_id,
                status="failed",
                result=None,
                code=exc.code,
                message=str(exc),
                finished_at=_now(),
            )
            return self._stored_run_response(
                connection,
                run_id,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            )

    def _pause_run(
        self,
        run_id: str,
        pause: _ExecutionPause,
        *,
        scope: str | None,
        idempotency_key: str | None,
        digest: str | None,
    ) -> dict[str, Any]:
        now = _now()
        with self.repository.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row["status"] != "running":
                return self._row_payload(row)
            self._store_tool_calls(connection, run_id, pause.tool_calls)
            self.repository.insert_approval_request(
                connection,
                approval_id=new_uuid7(),
                run_id=run_id,
                node_id=pause.node_id,
                prompt=pause.prompt,
                created_at=now,
            )
            self.repository.insert_checkpoint(
                connection,
                checkpoint_id=new_uuid7(),
                run_id=run_id,
                node_id=pause.node_id,
                waiting_kind="approval",
                values=pause.values,
                created_at=now,
            )
            self.repository.set_run_status(connection, run_id, status="waiting")
            requested = {"prompt": pause.prompt, **dict(pause.details or {})}
            self.repository.add_run_events(
                connection,
                run_id,
                [
                    (pause.node_id, "node.waiting", {"reason": "approval"}),
                    (pause.node_id, "approval.requested", requested),
                    (
                        pause.node_id,
                        "checkpoint.created",
                        {"waiting_kind": "approval"},
                    ),
                ],
            )
            return self._stored_run_response(
                connection,
                run_id,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            )

    def _stored_run_response(
        self,
        connection: Any,
        run_id: str,
        *,
        scope: str | None,
        idempotency_key: str | None,
        digest: str | None,
    ) -> dict[str, Any]:
        response = self._row_payload(
            connection.execute(
                "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        )
        if scope and idempotency_key and digest:
            self.repository.replace_idempotent_response(
                connection, scope, idempotency_key, digest, response
            )
        self.repository.replace_run_idempotent_payload(connection, run_id, response)
        return response

    def _store_tool_calls(
        self,
        connection: Any,
        run_id: str,
        records: tuple[_ToolCallRecord, ...],
    ) -> None:
        now = _now()
        for record in records:
            self.repository.insert_tool_call(
                connection,
                run_id=run_id,
                node_id=record.node_id,
                tool_reference=record.tool_reference,
                authorization=record.authorization,
                decision_code=record.decision_code,
                decision_reason=record.decision_reason,
                input_digest=record.input_digest,
                receipt=record.receipt,
                created_at=now,
            )

    def _recovery_identity(
        self, project_id: str, source: AgentSource
    ) -> dict[str, Any]:
        project = self.repository.project(project_id)
        if project is None:
            raise RuntimeError("project_invalid", "Project is unavailable")
        model = self._model_for(project_id, source.agent_id)
        return {
            "source_hash": source.source_hash,
            "permissions": source.permissions.to_dict(),
            "resource_lock": dict(source.lock),
            "project_root": str(self.projects._existing_root(project["root_path"])),
            "model_base_url": model.settings.model_base_url,
            "model_id": model.settings.model_id,
            "model_api_key_env": model.settings.model_api_key_env,
        }

    def _checkpoint_execution(
        self,
        project_id: str,
        run_id: str,
        source: AgentSource,
        node_id: str,
        values: dict[str, Any],
        *,
        approved: bool,
        verified: bool,
        conversation_context: str,
        tool_calls: tuple[_ToolCallRecord, ...],
    ) -> None:
        state = {
            "values": values,
            "approved": approved,
            "verified": verified,
            "conversation_context": conversation_context,
            "identity": self._recovery_identity(project_id, source),
        }
        checkpoint_id = new_uuid7()
        with self.repository.transaction() as connection:
            row = connection.execute(
                "SELECT status FROM runtime_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None or row["status"] != "running":
                raise _RunAbandoned()
            self._store_tool_calls(connection, run_id, tool_calls)
            self.repository.add_run_events(
                connection,
                run_id,
                [
                    (
                        node_id,
                        "checkpoint.created",
                        {
                            "checkpoint_id": checkpoint_id,
                            "waiting_kind": "execution",
                            "next_node_id": node_id,
                        },
                    )
                ],
            )
            state["sequence"] = connection.execute(
                "SELECT MAX(sequence) FROM runtime_run_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
            self.repository.insert_checkpoint(
                connection,
                checkpoint_id=checkpoint_id,
                run_id=run_id,
                node_id=node_id,
                waiting_kind="execution",
                values=state,
                created_at=_now(),
            )

    def _resume_run(
        self,
        row: Any,
        *,
        checkpoint_id: str | None,
        scope: str,
        idempotency_key: str,
        digest: str,
    ) -> dict[str, Any]:
        if not checkpoint_id:
            raise RuntimeError(
                "command_not_applicable",
                "Resume requires an explicit execution checkpoint",
            )
        version = self.repository.version(row["version_id"])
        if version is None or version["agent_id"] != row["agent_id"]:
            raise RuntimeError(
                "agent_version_not_found", "Committed Agent version not found"
            )
        source = AgentSource.from_dict(json.loads(version["source_json"]))
        if (
            source.agent_id != row["agent_id"]
            or source.source_hash != version["source_hash"]
        ):
            raise RuntimeError(
                "agent_version_invalid", "Agent version integrity check failed"
            )
        inputs = self.repository.run_inputs(row["run_id"])
        inputs = self._prepare_inputs(row["project_id"], source, inputs)
        self._require_runtime_modalities(row["project_id"], row["agent_id"], source)
        now, command_id, run_id = _now(), new_uuid7(), new_uuid7()
        with self.repository.transaction() as connection:
            replay = self.repository.idempotent_response(
                connection, scope, idempotency_key, digest
            )
            if replay is not None:
                return replay
            current = connection.execute(
                "SELECT * FROM runtime_runs WHERE run_id = ?", (row["run_id"],)
            ).fetchone()
            if current["status"] not in {"failed", "interrupted"}:
                raise RuntimeError(
                    "command_not_applicable",
                    "Resume requires a failed or interrupted run; "
                    "Stop revokes recovery",
                )
            checkpoint = self.repository.latest_checkpoint(connection, row["run_id"])
            if (
                checkpoint is None
                or checkpoint["checkpoint_id"] != checkpoint_id
                or checkpoint["waiting_kind"] != "execution"
            ):
                raise RuntimeError(
                    "resume_checkpoint_invalid",
                    "Only the latest execution checkpoint is recoverable; "
                    "approval waits require Approve/Reject",
                )
            previous = connection.execute(
                "SELECT payload_json FROM runtime_run_commands WHERE run_id = ? "
                "AND command_type = 'resume' AND status = 'applied'",
                (row["run_id"],),
            ).fetchone()
            if previous is not None:
                child_id = json.loads(previous["payload_json"])["resume_run_id"]
                response = self._row_payload(
                    connection.execute(
                        "SELECT * FROM runtime_runs WHERE run_id = ?", (child_id,)
                    ).fetchone()
                )
                self.repository.remember_response(
                    connection, scope, idempotency_key, digest, response
                )
                return response
            state = json.loads(checkpoint["values_json"])
            dispatched = connection.execute(
                "SELECT 1 FROM runtime_run_events WHERE run_id = ? "
                "AND sequence > ? AND kind = 'tool.started' LIMIT 1",
                (row["run_id"], state["sequence"]),
            ).fetchone()
            if dispatched is not None:
                raise RuntimeError(
                    "resume_effect_unsafe",
                    "A Tool was dispatched after this checkpoint; "
                    "reconcile its effects before recovery",
                )
            if state["identity"] != self._recovery_identity(row["project_id"], source):
                raise RuntimeError(
                    "resume_identity_changed",
                    "Checkpoint resource, workspace or Runtime "
                    "profile identity changed",
                )
            dependencies = inspect_agent_dependencies(
                self.projects, self.tools.catalog, row["project_id"], source
            )
            if not dependencies["runtime_ready"]:
                raise RuntimeError(
                    "resume_dependencies_unavailable",
                    "Pinned checkpoint dependencies are not available",
                )
            self.repository.create_run(
                connection,
                run_id=run_id,
                project_id=row["project_id"],
                agent_id=row["agent_id"],
                version_id=row["version_id"],
                created_at=now,
                inputs=inputs,
                conversation_id=row["conversation_id"],
            )
            self.repository.insert_run_command(
                connection,
                command_id=command_id,
                run_id=row["run_id"],
                command_type="resume",
                payload={"resume_run_id": run_id, "checkpoint_id": checkpoint_id},
                status="applied",
                created_at=now,
                applied_at=now,
            )
            self.repository.add_run_events(
                connection,
                run_id,
                [
                    (
                        None,
                        "run.created",
                        {
                            "resume_of_run_id": row["run_id"],
                            "resume_command_id": command_id,
                            "checkpoint_id": checkpoint_id,
                            "next_node_id": checkpoint["node_id"],
                            "version_id": row["version_id"],
                            "inputs": inputs,
                            "recovery_identity": state["identity"],
                        },
                    ),
                    (None, "run.started", {}),
                ],
            )
            child_checkpoint_id = new_uuid7()
            self.repository.add_run_events(
                connection,
                run_id,
                [
                    (
                        checkpoint["node_id"],
                        "checkpoint.created",
                        {
                            "checkpoint_id": child_checkpoint_id,
                            "waiting_kind": "execution",
                            "next_node_id": checkpoint["node_id"],
                        },
                    )
                ],
            )
            self.repository.insert_checkpoint(
                connection,
                checkpoint_id=child_checkpoint_id,
                run_id=run_id,
                node_id=checkpoint["node_id"],
                waiting_kind="execution",
                values={
                    **state,
                    "sequence": connection.execute(
                        "SELECT MAX(sequence) FROM runtime_run_events WHERE run_id = ?",
                        (run_id,),
                    ).fetchone()[0],
                },
                created_at=now,
            )
            response = self._row_payload(
                connection.execute(
                    "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
            )
            self.repository.remember_response(
                connection, scope, idempotency_key, digest, response
            )
        self._schedule_execution(
            run_id,
            lambda: self._complete_execution(
                row["project_id"],
                run_id,
                source,
                state["values"],
                start_node=checkpoint["node_id"],
                approved=state["approved"],
                verified=state["verified"],
                conversation_context=state["conversation_context"],
                conversation_id=row["conversation_id"],
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            ),
        )
        return response

    def _retry_run(
        self,
        row: Any,
        *,
        scope: str,
        idempotency_key: str,
        digest: str,
    ) -> dict[str, Any]:
        if row["status"] not in {"failed", "interrupted", "cancelled"}:
            raise RuntimeError(
                "command_not_applicable",
                "Retry is only available for terminal unsuccessful runs",
            )
        inputs = self.repository.run_inputs(row["run_id"])
        version = self.repository.version(row["version_id"])
        if version is None or version["agent_id"] != row["agent_id"]:
            raise RuntimeError(
                "agent_version_not_found", "Committed Agent version not found"
            )
        source = AgentSource.from_dict(json.loads(version["source_json"]))
        if (
            source.agent_id != row["agent_id"]
            or source.source_hash != version["source_hash"]
        ):
            raise RuntimeError(
                "agent_version_invalid", "Agent version integrity check failed"
            )
        inputs = self._prepare_inputs(row["project_id"], source, inputs)
        self._require_runtime_modalities(row["project_id"], row["agent_id"], source)
        now = _now()
        command_id = new_uuid7()
        run_id = new_uuid7()
        conversation_id = row["conversation_id"]
        conversation_context = ""
        with self.repository.transaction() as connection:
            replay = self.repository.idempotent_response(
                connection, scope, idempotency_key, digest
            )
            if replay is not None:
                return replay
            # Receipts are stored at outcome/pause; absence cannot prove no effect.
            # The durable pre-dispatch event also covers cancellation and process loss.
            ancestor_id = row["run_id"]
            while ancestor_id:
                dispatched = connection.execute(
                    "SELECT 1 FROM runtime_run_events WHERE run_id = ? "
                    "AND kind = 'tool.started' LIMIT 1",
                    (ancestor_id,),
                ).fetchone()
                if dispatched is not None:
                    raise RuntimeError(
                        "retry_effect_unsafe",
                        "Retry blocked: a Tool may have produced external effects. "
                        "Inspect the original run and reconcile effects manually "
                        "before a new run.",
                    )
                created = connection.execute(
                    "SELECT payload_json FROM runtime_run_events WHERE run_id = ? "
                    "AND kind = 'run.created' ORDER BY sequence LIMIT 1",
                    (ancestor_id,),
                ).fetchone()
                ancestor_id = (
                    json.loads(created["payload_json"]).get("resume_of_run_id")
                    if created is not None
                    else None
                )
            if conversation_id and self.conversations is not None:
                conversation_id, conversation_context = self.conversations.prepare_turn(
                    connection,
                    project_id=row["project_id"],
                    agent_id=row["agent_id"],
                    conversation_id=conversation_id,
                    inputs=inputs,
                    run_id=run_id,
                    append_user=False,
                )
            elif conversation_id:
                raise RuntimeError(
                    "conversation_unavailable",
                    "Agent conversation service is unavailable",
                )
            self.repository.create_run(
                connection,
                run_id=run_id,
                project_id=row["project_id"],
                agent_id=row["agent_id"],
                version_id=row["version_id"],
                created_at=now,
                inputs=inputs,
                conversation_id=conversation_id,
            )
            self.repository.insert_run_command(
                connection,
                command_id=command_id,
                run_id=row["run_id"],
                command_type="retry",
                payload={"retry_run_id": run_id},
                status="applied",
                created_at=now,
                applied_at=now,
            )
            self.repository.add_run_events(
                connection,
                run_id,
                [
                    (
                        None,
                        "run.created",
                        {
                            "retry_of_run_id": row["run_id"],
                            "retry_command_id": command_id,
                            "version_id": row["version_id"],
                            "inputs": inputs,
                        },
                    ),
                    (None, "run.started", {}),
                ],
            )
            response = self._row_payload(
                connection.execute(
                    "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
            )
            self.repository.remember_response(
                connection, scope, idempotency_key, digest, response
            )
        self._schedule_execution(
            run_id,
            lambda: self._complete_execution(
                row["project_id"],
                run_id,
                source,
                inputs,
                start_node=None,
                approved=False,
                conversation_id=conversation_id,
                conversation_context=conversation_context,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            ),
        )
        return response

    def _stop_run(
        self,
        row: Any,
        *,
        scope: str,
        idempotency_key: str,
        digest: str,
    ) -> dict[str, Any]:
        now = _now()
        command_id = new_uuid7()
        with self.repository.transaction() as connection:
            replay = self.repository.idempotent_response(
                connection, scope, idempotency_key, digest
            )
            if replay is not None:
                return replay
            row = connection.execute(
                "SELECT * FROM runtime_runs WHERE run_id = ?", (row["run_id"],)
            ).fetchone()
            if row["status"] not in {"waiting", "running"}:
                raise RuntimeError(
                    "command_not_applicable", "Stop is only available for active runs"
                )
            self.repository.remember_response(
                connection, scope, idempotency_key, digest, self._row_payload(row)
            )
            self.repository.insert_run_command(
                connection,
                command_id=command_id,
                run_id=row["run_id"],
                command_type="stop",
                payload={},
                status="applied",
                created_at=now,
                applied_at=now,
            )
            self.repository.cancel_pending_approvals(
                connection, row["run_id"], resolved_at=now
            )
            self.repository.add_run_events(
                connection, row["run_id"], [(None, "run.cancelled", {})]
            )
            self.repository.finish_run(
                connection,
                row["run_id"],
                status="cancelled",
                result=None,
                code="run_cancelled",
                message="run stopped by command",
                finished_at=now,
            )
            self.repository.mark_command_applied(connection, command_id, applied_at=now)
            return self._stored_run_response(
                connection,
                row["run_id"],
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            )

    def _resolve_approval(
        self,
        row: Any,
        *,
        decision: str,
        scope: str,
        idempotency_key: str,
        digest: str,
        comment: str = "",
    ) -> dict[str, Any]:
        if row["status"] != "waiting":
            raise RuntimeError(
                "command_not_applicable", "This run is not waiting for approval"
            )
        now = _now()
        command_id = new_uuid7()
        with self.repository.transaction() as connection:
            replay = self.repository.idempotent_response(
                connection, scope, idempotency_key, digest
            )
            if replay is not None:
                return replay
            row = connection.execute(
                "SELECT * FROM runtime_runs WHERE run_id = ?", (row["run_id"],)
            ).fetchone()
            if row["status"] != "waiting":
                raise RuntimeError(
                    "command_not_applicable", "This run is not waiting for approval"
                )
            pending = self.repository.pending_approval(connection, row["run_id"])
            checkpoint = self.repository.latest_checkpoint(connection, row["run_id"])
            if pending is None or checkpoint is None:
                raise RuntimeError(
                    "command_not_applicable", "No pending approval checkpoint"
                )
            version = connection.execute(
                "SELECT source_json FROM agent_versions WHERE version_id = ?",
                (row["version_id"],),
            ).fetchone()
            if version is None:
                raise RuntimeError("version_missing", "Agent version is unavailable")
            source = AgentSource.from_dict(json.loads(version["source_json"]))
            values = json.loads(checkpoint["values_json"])
            if (
                decision == "rejected"
                and (written := source.outputs.get("written")) is not None
                and written.compact_type == "boolean"
                and "written" not in values
            ):
                values["written"] = False
            gate = next(
                (node for node in source.nodes if node.id == pending["node_id"]),
                None,
            )
            round_number = int(values.get(_VISITS, {}).get(pending["node_id"], 1))
            exhausted = (
                decision == "rejected"
                and gate is not None
                and gate.bounded_revisions > 0
                and round_number > gate.bounded_revisions
            )
            if source.is_loop:
                next_node = None
            else:
                next_node = next(
                    (
                        edge.to_node
                        for edge in source.transitions
                        if edge.from_node == pending["node_id"]
                        and edge.port.value == decision
                    ),
                    "",
                )
                if not next_node:
                    raise RuntimeError(
                        "transition_missing",
                        f"node {pending['node_id']} did not select a valid transition",
                    )
            if (
                not source.is_loop
                and pending["node_id"] not in source.inputs
                and pending["node_id"] not in source.outputs
            ):
                values[pending["node_id"]] = {
                    "decision": decision,
                    "comment": comment,
                    "round": round_number,
                }
            if not source.data_edges and not source.is_loop:
                assert next_node is not None
                values = _bind_blank_approval_condition(
                    source, next_node, decision, values
                )
            self.repository.remember_response(
                connection, scope, idempotency_key, digest, self._row_payload(row)
            )
            self.repository.insert_run_command(
                connection,
                command_id=command_id,
                run_id=row["run_id"],
                command_type="approve" if decision == "approved" else "reject",
                payload={"decision": decision, "comment": comment},
                status="accepted",
                created_at=now,
            )
            self.repository.resolve_approval(
                connection,
                pending["approval_id"],
                status=decision,
                command_id=command_id,
                resolved_at=now,
            )
            resolved_payload: dict[str, Any] = {"decision": decision}
            if comment:
                resolved_payload["comment"] = comment
            if exhausted:
                resolved_payload["revision_limit_reached"] = True
            if exhausted:
                self.repository.set_run_status(
                    connection, row["run_id"], status="running"
                )
                self.repository.add_run_events(
                    connection,
                    row["run_id"],
                    [
                        (pending["node_id"], "approval.resolved", resolved_payload),
                        (
                            pending["node_id"],
                            "node.failed",
                            {"code": "revision_limit_reached"},
                        ),
                        (None, "run.failed", {"code": "revision_limit_reached"}),
                    ],
                )
                self.repository.mark_command_applied(
                    connection, command_id, applied_at=now
                )
                self.repository.finish_run(
                    connection,
                    row["run_id"],
                    status="failed",
                    result=None,
                    code="revision_limit_reached",
                    message=("The review was rejected after the last allowed revision"),
                    finished_at=now,
                )
                return self._stored_run_response(
                    connection,
                    row["run_id"],
                    scope=scope,
                    idempotency_key=idempotency_key,
                    digest=digest,
                )
            self.repository.set_run_status(connection, row["run_id"], status="running")
            self.repository.add_run_events(
                connection,
                row["run_id"],
                [
                    (
                        pending["node_id"],
                        "approval.resolved",
                        resolved_payload,
                    ),
                    (
                        pending["node_id"],
                        "node.completed",
                        {"port": decision},
                    ),
                ],
            )
            self.repository.mark_command_applied(connection, command_id, applied_at=now)
            resumed = self._row_payload(
                connection.execute(
                    "SELECT * FROM runtime_runs WHERE run_id = ?", (row["run_id"],)
                ).fetchone()
            )
            self.repository.replace_idempotent_response(
                connection, scope, idempotency_key, digest, resumed
            )
            self.repository.replace_run_idempotent_payload(
                connection, row["run_id"], resumed
            )
        conversation_id = row["conversation_id"]
        conversation_context = (
            self.conversations.prompt_context(conversation_id)
            if self.conversations is not None and conversation_id
            else ""
        )
        self._schedule_execution(
            row["run_id"],
            lambda: self._complete_execution(
                row["project_id"],
                row["run_id"],
                source,
                values,
                start_node=next_node,
                approved=decision == "approved",
                conversation_id=conversation_id,
                conversation_context=conversation_context,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            ),
        )
        return resumed

    def _schedule_execution(self, run_id: str, worker: Callable[[], None]) -> None:
        threading.Thread(
            target=worker, daemon=True, name=f"veyra-run-{run_id[:8]}"
        ).start()

    def _complete_execution(
        self,
        project_id: str,
        run_id: str,
        source: AgentSource,
        inputs: dict[str, Any],
        *,
        start_node: str | None,
        approved: bool,
        scope: str | None,
        idempotency_key: str | None,
        digest: str | None,
        conversation_id: str | None = None,
        conversation_context: str = "",
        verified: bool = False,
    ) -> None:
        try:
            if self.credentials is not None:
                resolved = self.credentials.effective_credential(
                    project_id, source.agent_id
                )
                if resolved is not None:
                    self.credentials.mark_used(resolved[0].credential_id)
            executor = self._execute_loop if source.is_loop else self._execute
            outcome = executor(
                project_id,
                run_id,
                source,
                inputs,
                self._model_for(project_id, source.agent_id),
                start_node=start_node,
                approved=approved,
                conversation_context=conversation_context,
                verified=verified,
            )
            if not self._is_running(run_id):
                return
            self._commit_outcome(
                run_id,
                outcome,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
                conversation_id=conversation_id,
            )
        except _RunAbandoned:
            return
        except (RuntimeProviderError, ToolRuntimeError) as exc:
            if self._is_running(run_id):
                self._fail_run(
                    run_id,
                    RuntimeError(exc.code, str(exc)),
                    scope=scope,
                    idempotency_key=idempotency_key,
                    digest=digest,
                )
        except RuntimeError as exc:
            if self._is_running(run_id):
                self._fail_run(
                    run_id,
                    exc,
                    scope=scope,
                    idempotency_key=idempotency_key,
                    digest=digest,
                )

    def _is_running(self, run_id: str) -> bool:
        row = self.repository.run(run_id)
        return row is not None and row["status"] == "running"

    def _run_response(self, run_id: str) -> dict[str, Any]:
        row = self.repository.run(run_id)
        assert row is not None
        return self._row_payload(row)

    @staticmethod
    def _row_payload(row: Any) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": row["run_id"],
            "project_id": row["project_id"],
            "agent_id": row["agent_id"],
            "version_id": row["version_id"],
            "conversation_id": row["conversation_id"],
            "run_target_kind": "agent",
            "status": row["status"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": (
                {"code": row["error_code"], "message": row["error_message"]}
                if row["error_code"]
                else None
            ),
            "created_at": row["created_at"],
            "finished_at": row["finished_at"],
        }

    @staticmethod
    def _validate_inputs(
        source: AgentSource | WorkflowSource, inputs: dict[str, Any]
    ) -> None:
        declared = source.inputs
        extra = set(inputs) - set(declared)
        missing = {
            name
            for name, field in declared.items()
            if field.required and name not in inputs
        }
        if extra or missing:
            raise RuntimeError(
                "inputs_invalid", "inputs must exactly match the Agent source inputs"
            )
        for field_name, field in declared.items():
            if field_name not in inputs:
                continue
            if not value_matches_field(field, inputs[field_name]):
                raise RuntimeError(
                    "inputs_invalid",
                    f"input {field_name} must be a {field.compact_type}",
                )

    def _prepare_inputs(
        self,
        project_id: str,
        source: AgentSource | WorkflowSource,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        self._validate_inputs(source, inputs)
        return self._bind_typed_values(
            project_id, source.inputs, inputs, "inputs_invalid"
        )

    def _prepare_outputs(
        self,
        project_id: str,
        source: AgentSource | WorkflowSource,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        result = self._validated_outputs(source, values)
        error_code = (
            "output_type_invalid"
            if any(field.is_artifact() for field in source.outputs.values())
            else "output_invalid"
        )
        return self._bind_typed_values(project_id, source.outputs, result, error_code)

    def _bind_typed_values(
        self,
        project_id: str,
        fields: Mapping[str, TypedField],
        values: dict[str, Any],
        error_code: str,
    ) -> dict[str, Any]:
        bound = dict(values)
        for name, field in fields.items():
            if name not in bound or not field.is_artifact():
                continue
            bound[name] = self._bind_artifact_value(
                project_id, name, field, bound[name], error_code
            )
        return bound

    def _bind_artifact_value(
        self,
        project_id: str,
        name: str,
        field: TypedField,
        value: Any,
        error_code: str,
    ) -> Any:
        if field.multiple:
            if not isinstance(value, list):
                raise RuntimeError(
                    error_code, f"{name} must be a {field.compact_type} list"
                )
            return [
                self._resolve_artifact_ref(project_id, name, field, item, error_code)
                for item in value
            ]
        if field.artifact_kind == "collection":
            if not looks_like_collection_ref(value) or not isinstance(value, Mapping):
                raise RuntimeError(
                    error_code, f"{name} must be a collection of ArtifactRef items"
                )
            items = [
                self._resolve_artifact_ref(project_id, name, field, item, error_code)
                for item in value.get("items") or []
            ]
            return {
                "kind": "collection",
                "collection_id": str(value.get("collection_id") or ""),
                "items": items,
            }
        return self._resolve_artifact_ref(project_id, name, field, value, error_code)

    def _resolve_artifact_ref(
        self,
        project_id: str,
        name: str,
        field: TypedField,
        value: Any,
        error_code: str,
    ) -> dict[str, Any]:
        artifact_id = artifact_id_from_value(value)
        if artifact_id is None:
            raise RuntimeError(
                error_code, f"{name} must be a {field.compact_type} ArtifactRef"
            )
        try:
            record = self.artifacts.get(project_id, artifact_id)
        except ProjectError as exc:
            code = error_code if exc.code == "artifact_not_found" else exc.code
            raise RuntimeError(code, str(exc)) from exc
        media_type = str(record["media_type"])
        if isinstance(value, Mapping) and "media_type" in value:
            claimed = str(value["media_type"]).casefold()
            if claimed and claimed != media_type.casefold():
                raise RuntimeError(
                    error_code,
                    f"{name} artifact media type does not match stored bytes",
                )
        if not field.accepts_media(media_type):
            raise RuntimeError(
                error_code, f"{name} artifact media type is not accepted"
            )
        return {
            "kind": "artifact",
            "artifact_id": record["artifact_id"],
            "media_type": media_type,
            "filename": str(record["filename"]),
        }

    def _materialize_produced_artifacts(
        self,
        project_id: str,
        run_id: str,
        node_id: str,
        produced: tuple[ProducedArtifact, ...],
        emit: Callable[[str | None, str, dict[str, Any]], None],
    ) -> dict[str, Any]:
        mapped: dict[str, Any] = {}
        for item in produced:
            try:
                record = self.artifacts.upload(
                    project_id,
                    item.filename,
                    item.contents,
                    claimed_type=item.claimed_type,
                    source_kind="runtime_output",
                    run_id=run_id,
                )
            except ProjectError as exc:
                raise RuntimeError(exc.code, str(exc)) from exc
            emit(
                node_id,
                "artifact.created",
                {
                    "artifact_id": record["artifact_id"],
                    "media_type": record["media_type"],
                    "filename": record["filename"],
                    "size_bytes": record["size_bytes"],
                    "digest": record["sha256"],
                    "node_id": node_id,
                },
            )
            mapped[item.field] = {
                "kind": "artifact",
                "artifact_id": record["artifact_id"],
                "media_type": record["media_type"],
                "filename": record["filename"],
            }
        return mapped

    def _execute(
        self,
        project_id: str,
        run_id: str,
        source: AgentSource,
        inputs: dict[str, Any],
        model: RuntimeModelClient,
        *,
        start_node: str | None = None,
        approved: bool = False,
        conversation_context: str = "",
        verified: bool = False,
    ) -> _ExecutionOutcome:
        nodes = {node.id: node for node in source.nodes}
        edges = {
            (edge.from_node, edge.port.value): edge.to_node
            for edge in source.transitions
        }
        current = start_node or next(
            node.id
            for node in source.nodes
            if node.component_type is ComponentType.START
        )
        values = dict(inputs)
        store = DataflowStore.from_source(source, values) if source.data_edges else None
        result: dict[str, Any] = {}
        verifier_passed = verified
        events: list[tuple[str | None, str, dict[str, Any]]] = []
        tool_calls: list[_ToolCallRecord] = []

        def emit(node_id: str | None, kind: str, payload: dict[str, Any]) -> None:
            events.append((node_id, kind, payload))
            self._persist_event(run_id, node_id, kind, payload)

        rounds = 1 + sum(node.bounded_revisions for node in source.nodes)
        for _ in range((len(nodes) + 1) * rounds):
            if not self._is_running(run_id):
                raise _RunAbandoned()
            node = nodes[current]
            self._checkpoint_execution(
                project_id,
                run_id,
                source,
                node.id,
                values,
                approved=approved,
                verified=verifier_passed,
                conversation_context=conversation_context,
                tool_calls=tuple(tool_calls),
            )
            tool_calls.clear()
            start_payload: dict[str, Any] = {
                "component_type": node.component_type.value
            }
            if node.component_type in {ComponentType.AGENT, ComponentType.MODEL}:
                node_model = self._model_for_node(project_id, source, node)
                slot = MODEL_REF_SLOTS.get(node.model_ref or "", RUNTIME_BINDING_SLOT)
                start_payload.update(
                    self._model_evidence(
                        project_id,
                        source.agent_id,
                        node_model,
                        node_binding_slot(node.id)
                        if self.credentials is not None
                        and self.credentials.binding(
                            project_id, source.agent_id, node_binding_slot(node.id)
                        )
                        is not None
                        else slot,
                    )
                )
            emit(node.id, "node.started", start_payload)
            step_output: Any = None
            try:
                if node.component_type is ComponentType.START:
                    port = "next"
                elif node.component_type is ComponentType.TRANSFORM:
                    assert node.mapping is not None
                    local_values = self._typed_node_values(store, node, values)
                    mapped = {
                        key: _transform_value(template, local_values)
                        for key, template in node.mapping.items()
                    }
                    values.update(mapped)
                    if store is not None:
                        store.record(node.id, mapped)
                        values = store.merge_into(values)
                    step_output = _output_preview(mapped)
                    port = "next"
                elif node.component_type is ComponentType.CONDITION:
                    assert node.expression is not None
                    port = "true" if _condition(node.expression, values) else "false"
                elif node.component_type is ComponentType.VERIFIER:
                    assert node.checks is not None
                    result = self._prepare_outputs(project_id, source, values)
                    verifier_passed = all(
                        _check(check, result) for check in node.checks
                    )
                    port = "passed" if verifier_passed else "failed"
                    emit(node.id, "verifier.result", {"passed": verifier_passed})
                elif node.component_type is ComponentType.TOOL:
                    project = self.repository.project(project_id)
                    if project is None:
                        raise RuntimeError("project_invalid", "Project is unavailable")
                    tool_values = self._tool_input_values(node, values)
                    authorization = self._authorize_tool(
                        project_id, source, node, tool_values
                    )
                    resource = authorization.resource
                    identity = (
                        {
                            "resource_identity": {
                                "reference": resource["reference"],
                                "version": resource["version"],
                                "content_hash": resource["content_hash"],
                                "bound_content_hash": resource["bound_content_hash"],
                                "locked_content_hash": source.lock.get(node.uses or ""),
                            }
                        }
                        if resource is not None
                        else {}
                    )
                    emit(
                        node.id,
                        "tool.requested",
                        {
                            "tool_reference": authorization.tool_reference,
                            "input_digest": authorization.input_digest,
                            "permission": authorization.decision,
                            "code": authorization.code,
                            **identity,
                        },
                    )
                    record = _ToolCallRecord(
                        node_id=node.id,
                        tool_reference=authorization.tool_reference,
                        authorization=authorization.decision,
                        decision_code=authorization.code,
                        decision_reason=authorization.reason,
                        input_digest=authorization.input_digest,
                        receipt=None,
                    )
                    tool_calls.append(record)
                    if authorization.decision != "allowed":
                        raise RuntimeError(authorization.code, authorization.reason)
                    emit(
                        node.id,
                        "tool.started",
                        {"tool_reference": authorization.tool_reference, **identity},
                    )
                    execution = self.tools.execute(
                        project_root=self.projects._existing_root(project["root_path"]),
                        source=source,
                        node=node,
                        values=tool_values,
                        authorization=authorization,
                        approved=approved,
                        project_id=project_id,
                    )
                    produced = self._materialize_produced_artifacts(
                        project_id,
                        run_id,
                        node.id,
                        execution.produced_artifacts,
                        emit,
                    )
                    receipt = _json_safe_payload({**execution.receipt, **identity})
                    emit(node.id, "tool.completed", receipt)
                    tool_calls[-1] = _ToolCallRecord(
                        node_id=record.node_id,
                        tool_reference=record.tool_reference,
                        authorization=record.authorization,
                        decision_code=record.decision_code,
                        decision_reason=record.decision_reason,
                        input_digest=record.input_digest,
                        receipt=receipt,
                    )
                    tool_output = self._tool_output_values(
                        node, {**execution.output, **produced}
                    )
                    values.update(tool_output)
                    step_output = _output_preview(tool_output)
                    port = "next"
                elif node.component_type is ComponentType.CUSTOM_COMPONENT:
                    values.update(
                        self._run_custom_component(
                            project_id,
                            run_id,
                            source,
                            node,
                            values,
                            model,
                            emit,
                            tool_calls,
                            approved=approved,
                        )
                    )
                    port = "next"
                elif node.component_type is ComponentType.OUTPUT:
                    assert node.output_name is not None
                    if store is not None:
                        values = store.merge_into(values)
                        produced = store.run_outputs(source.outputs)
                        values.update(produced)
                    result = self._prepare_outputs(project_id, source, values)
                    emit(node.id, "node.completed", {})
                    return _ExecutionOutcome(
                        events=events,
                        tool_calls=tuple(tool_calls),
                        result=result,
                        verified=verifier_passed,
                        pause=None,
                    )
                elif node.component_type in {ComponentType.AGENT, ComponentType.MODEL}:
                    context_text = ""
                    if source.skill_refs:
                        emit(
                            node.id,
                            "tool.requested",
                            {
                                "tool_reference": "skill.context",
                                "authorization": "allowed",
                                "references": list(source.skill_refs),
                            },
                        )
                        skill_resources = self._skill_resources(source)
                        emit(
                            node.id,
                            "tool.completed",
                            {
                                "tool_reference": "skill.context",
                                "receipts": [
                                    {
                                        "reference": resource["reference"],
                                        "name": resource["name"],
                                        "content_hash": resource["content_hash"],
                                        "instruction_byte_length": len(
                                            str(
                                                resource["spec"].get("instruction", "")
                                            ).encode("utf-8")
                                        ),
                                        "verified": True,
                                    }
                                    for resource in skill_resources
                                ],
                            },
                        )
                    if source.knowledge_refs or any(
                        item["kind"] == "knowledge"
                        for item in (source.ui.get("bindings") or {}).values()
                    ):
                        emit(
                            node.id,
                            "tool.requested",
                            {
                                "tool_reference": "knowledge.context",
                                "authorization": "allowed",
                                "references": list(source.knowledge_refs),
                            },
                        )
                        try:
                            query = json.dumps(
                                [
                                    values[name]
                                    for name in sorted(source.inputs)
                                    if name in values
                                ],
                                ensure_ascii=False,
                                sort_keys=True,
                            )
                            context_text, receipts = read_knowledge_context(
                                self.projects,
                                project_id,
                                source,
                                query,
                            )
                        except ProjectError as exc:
                            raise RuntimeError(exc.code, str(exc)) from exc
                        emit(
                            node.id,
                            "tool.completed",
                            {
                                "tool_reference": "knowledge.context",
                                "receipts": receipts,
                                "query_hash": file_hash(query),
                                "hit_count": len(receipts),
                            },
                        )

                    def emit_model_delta(token: str, node_id: str = node.id) -> None:
                        emit(node_id, "model.delta", {"delta": token})

                    produced_values = self._run_agent(
                        project_id,
                        node,
                        source,
                        self._typed_node_values(store, node, values),
                        self._model_for_node(project_id, source, node),
                        context_text,
                        conversation_context,
                        on_token=emit_model_delta,
                        run_id=run_id,
                        emit=emit,
                    )
                    values.update(produced_values)
                    if store is not None:
                        recorded = produced_values.get(node.id)
                        ports = (
                            recorded
                            if isinstance(recorded, Mapping)
                            else {
                                name: produced_values[name]
                                for name in (node.outputs or {})
                                if name in produced_values
                            }
                        )
                        if isinstance(ports, Mapping):
                            store.record(node.id, dict(ports))
                        values = store.merge_into(values)
                    step_output = _output_preview(
                        produced_values.get(node.id, produced_values)
                    )
                    port = "next"
                elif node.component_type is ComponentType.HUMAN_APPROVAL:
                    prompt = node.prompt or ""
                    if "{{" in prompt:
                        prompt = _interpolate(prompt, values)
                    visits = dict(values.get(_VISITS) or {})
                    visits[node.id] = int(visits.get(node.id, 0)) + 1
                    values[_VISITS] = visits
                    return _ExecutionOutcome(
                        events=events,
                        tool_calls=tuple(tool_calls),
                        result=None,
                        verified=False,
                        pause=_ExecutionPause(
                            node_id=node.id,
                            prompt=prompt,
                            values=values,
                            events=events,
                            tool_calls=tuple(tool_calls),
                            details=_approval_details(node, values, visits[node.id]),
                        ),
                    )
                else:
                    raise RuntimeError(
                        "runtime_not_supported",
                        f"{node.component_type.value} is not supported by "
                        "this local Runtime",
                    )
            except _RunAbandoned:
                raise
            except (RuntimeProviderError, ToolRuntimeError) as exc:
                runtime_error = RuntimeError(exc.code, str(exc))
                if isinstance(exc, ToolRuntimeError) and exc.receipt is not None:
                    emit(node.id, "tool.failed", exc.receipt)
                    tool_calls[-1] = replace(tool_calls[-1], receipt=exc.receipt)
                emit(node.id, "node.failed", {"code": runtime_error.code})
                runtime_error.events = events
                runtime_error.tool_calls = tuple(tool_calls)
                raise runtime_error from exc
            except RuntimeError as exc:
                emit(node.id, "node.failed", {"code": exc.code})
                exc.events = events
                exc.tool_calls = tuple(tool_calls)
                raise
            except Exception:
                runtime_error = RuntimeError(
                    "executor_failed", "local Runtime execution failed"
                )
                emit(node.id, "node.failed", {"code": runtime_error.code})
                runtime_error.events = events
                runtime_error.tool_calls = tuple(tool_calls)
                raise runtime_error from None
            completed: dict[str, Any] = {"port": port}
            if step_output is not None:
                completed["output"] = step_output
            emit(node.id, "node.completed", completed)
            time.sleep(0.03)
            if not self._is_running(run_id):
                raise _RunAbandoned()
            current = edges.get((node.id, port), "")
            if not current:
                raise RuntimeError(
                    "transition_missing",
                    f"node {node.id} did not select a valid transition",
                )
        raise RuntimeError(
            "graph_execution_invalid", "graph exceeded deterministic execution limit"
        )

    @staticmethod
    def _validated_outputs(
        source: AgentSource | WorkflowSource, values: dict[str, Any]
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, field in source.outputs.items():
            if name not in values:
                if field.required:
                    raise RuntimeError(
                        "output_invalid",
                        f"output {name} is missing or is not a {field.compact_type}",
                    )
                continue
            if not value_matches_field(field, values[name]):
                raise RuntimeError(
                    "output_type_invalid" if field.is_artifact() else "output_invalid",
                    f"output {name} is missing or is not a {field.compact_type}",
                )
            result[name] = values[name]
        return result

    @staticmethod
    def _tool_input_values(node: Any, values: dict[str, Any]) -> dict[str, Any]:
        if not node.input_mapping:
            return values
        mapped: dict[str, Any] = {}
        for tool_name, source_name in node.input_mapping.items():
            if source_name not in values:
                raise RuntimeError(
                    "tool_input_missing",
                    f"Tool input mapping source {source_name} is unavailable",
                )
            mapped[tool_name] = values[source_name]
        return mapped

    @staticmethod
    def _tool_output_values(node: Any, output: dict[str, Any]) -> dict[str, Any]:
        if not node.output_mapping:
            return output
        mapped: dict[str, Any] = {}
        for tool_name, value in output.items():
            target_name = node.output_mapping.get(tool_name, tool_name)
            if target_name in mapped:
                raise RuntimeError(
                    "tool_output_mapping_invalid",
                    f"Tool outputs map to the same field {target_name}",
                )
            mapped[target_name] = value
        return mapped

    def _source_requires_model(self, project_id: str, source: AgentSource) -> bool:
        for node in source.nodes:
            if (
                node.component_type in {ComponentType.AGENT, ComponentType.MODEL}
                and node.model_ref != IMAGE_MODEL_REF
            ):
                return True
            if node.component_type is ComponentType.CUSTOM_COMPONENT:
                try:
                    kind = self._resolve_custom_component(
                        project_id, source, node
                    ).implementation.kind
                except RuntimeError:
                    continue
                if kind is CustomComponentImplementationKind.MODEL_RECIPE:
                    return True
        return False

    def _custom_component_kind(
        self, project_id: str, node: FlowNode
    ) -> CustomComponentImplementationKind | None:
        if node.uses is None:
            return None
        try:
            return self.custom_components.resolve(
                project_id, node.uses
            ).implementation.kind
        except (CustomComponentError, ContractValidationError, ProjectError):
            return None

    def _resolve_custom_component(
        self, project_id: str, source: AgentSource, node: FlowNode
    ) -> CustomComponentDefinition:
        if not node.uses:
            raise RuntimeError(
                "component_reference_missing", "Custom Component node is missing uses"
            )
        locked = source.lock.get(node.uses)
        try:
            definition = self.custom_components.resolve(project_id, node.uses)
        except CustomComponentError as exc:
            raise RuntimeError(exc.code, str(exc)) from exc
        if locked != definition.content_hash():
            raise RuntimeError(
                "component_lock_mismatch",
                "Agent lock does not match the pinned Custom Component",
            )
        return definition

    def _component_input_values(
        self,
        definition: CustomComponentDefinition,
        node: FlowNode,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        mapped = self._tool_input_values(node, values)
        for name, field in definition.inputs.items():
            if name not in mapped:
                if field.required:
                    raise RuntimeError(
                        "component_input_invalid",
                        f"Custom Component input {name} is missing",
                    )
                continue
            if not value_matches_field(field, mapped[name]):
                raise RuntimeError(
                    "component_input_invalid",
                    f"Custom Component input {name} is not a {field.compact_type}",
                )
        return {name: mapped[name] for name in definition.inputs if name in mapped}

    def _component_output_values(
        self,
        definition: CustomComponentDefinition,
        node: FlowNode,
        produced: dict[str, Any],
    ) -> dict[str, Any]:
        for name, field in definition.outputs.items():
            if name not in produced:
                if field.required:
                    raise RuntimeError(
                        "component_output_invalid",
                        f"Custom Component output {name} is missing",
                    )
                continue
            if not value_matches_field(field, produced[name]):
                raise RuntimeError(
                    "component_output_invalid",
                    f"Custom Component output {name} is not a {field.compact_type}",
                )
        return self._tool_output_values(node, produced)

    def _authorize_wrapped_tool(
        self,
        project_id: str,
        source: AgentSource,
        node: FlowNode,
        definition: CustomComponentDefinition,
        values: dict[str, Any],
    ) -> Any:
        if not definition.dependencies:
            return self.tools._denied(
                definition.implementation.tool_reference or "",
                "unavailable_dependency",
                "Tool wrapper has no pinned Tool",
                values,
            )
        try:
            resource = self.custom_components.resolve_dependency(
                project_id, definition.dependencies[0]
            )
        except CustomComponentError as exc:
            return self.tools._denied(
                definition.implementation.tool_reference or "",
                exc.code,
                str(exc),
                values,
            )
        tool_node = self._wrapper_tool_node(node, definition)
        pinned = self._source_with_component_pins(source, definition)
        return self.tools.authorize(
            source=pinned,
            node=tool_node,
            values=values,
            resource=self.resource_readiness.project(resource),
        )

    @staticmethod
    def _wrapper_tool_node(
        node: FlowNode, definition: CustomComponentDefinition
    ) -> FlowNode:
        payload: dict[str, Any] = {
            "id": node.id,
            "component_type": "Tool",
            "uses": definition.implementation.tool_reference,
        }
        return FlowNode.from_dict(payload)

    @staticmethod
    def _source_with_component_pins(
        source: AgentSource, definition: CustomComponentDefinition
    ) -> AgentSource:
        payload = source.to_dict()
        lock = dict(payload.get("lock") or {})
        for dependency in definition.dependencies:
            lock[dependency.reference] = dependency.content_hash
        payload["lock"] = lock
        return AgentSource.from_dict(payload)

    def _run_custom_component(
        self,
        project_id: str,
        run_id: str,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        model: RuntimeModelClient,
        emit: Callable[..., None],
        tool_calls: list[Any],
        *,
        approved: bool,
    ) -> dict[str, Any]:
        definition = self._resolve_custom_component(project_id, source, node)
        kind = definition.implementation.kind
        if kind is CustomComponentImplementationKind.COMPOSITE_GRAPH:
            raise RuntimeError(
                "design_only",
                "composite_graph Custom Components are not executed in this slice",
            )
        component_values = self._component_input_values(definition, node, values)
        if kind is CustomComponentImplementationKind.TRANSFORM:
            assert definition.implementation.mapping is not None
            produced = {
                key: _interpolate(template, component_values)
                for key, template in definition.implementation.mapping.items()
            }
            return self._component_output_values(definition, node, produced)
        if kind is CustomComponentImplementationKind.MODEL_RECIPE:
            if not model.configured:
                raise RuntimeError(
                    "runtime_not_configured",
                    "model_recipe Custom Components require a Runtime model",
                )
            prompt = definition.implementation.instruction or ""
            if "{{" in prompt:
                prompt = _interpolate(prompt, component_values)
            prompt = _with_output_contract(prompt, definition.outputs)
            user_content = json.dumps(
                component_values, ensure_ascii=False, sort_keys=True
            )
            fragments: list[str] = []

            def emit_delta(token: str) -> None:
                emit(node.id, "model.delta", {"delta": token})

            for token in model.stream(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format=_runtime_response_format(definition.outputs),
            ):
                if not isinstance(token, str) or not token:
                    continue
                fragments.append(token)
                emit_delta(token)
            produced = _model_output_values(
                "".join(fragments).strip(),
                definition.outputs,
                component_values,
                node.id,
            )
            produced.pop(node.id, None)
            return self._component_output_values(definition, node, produced)
        tool_values = dict(component_values)
        if definition.implementation.input_mapping:
            tool_values = {}
            for (
                tool_name,
                source_name,
            ) in definition.implementation.input_mapping.items():
                if source_name not in component_values:
                    raise RuntimeError(
                        "component_input_invalid",
                        f"Tool wrapper input {source_name} is missing",
                    )
                tool_values[tool_name] = component_values[source_name]
        tool_node = self._wrapper_tool_node(node, definition)
        pinned = self._source_with_component_pins(source, definition)
        authorization = self._authorize_wrapped_tool(
            project_id, source, node, definition, tool_values
        )
        resource = authorization.resource
        identity: dict[str, Any] = (
            {
                "resource_identity": {
                    "reference": resource["reference"],
                    "version": resource["version"],
                    "content_hash": resource["content_hash"],
                    "bound_content_hash": resource.get("bound_content_hash"),
                    "locked_content_hash": definition.dependencies[0].content_hash
                    if definition.dependencies
                    else None,
                    "component_reference": node.uses,
                }
            }
            if resource is not None
            else {"component_reference": node.uses}
        )
        emit(
            node.id,
            "tool.requested",
            {
                "tool_reference": authorization.tool_reference,
                "input_digest": authorization.input_digest,
                "permission": authorization.decision,
                "code": authorization.code,
                **identity,
            },
        )
        record = _ToolCallRecord(
            node_id=node.id,
            tool_reference=authorization.tool_reference,
            authorization=authorization.decision,
            decision_code=authorization.code,
            decision_reason=authorization.reason,
            input_digest=authorization.input_digest,
            receipt=None,
        )
        tool_calls.append(record)
        if authorization.decision != "allowed":
            raise RuntimeError(authorization.code, authorization.reason)
        emit(
            node.id,
            "tool.started",
            {"tool_reference": authorization.tool_reference, **identity},
        )
        project = self.repository.project(project_id)
        if project is None:
            raise RuntimeError("project_invalid", "Project is unavailable")
        execution = self.tools.execute(
            project_root=self.projects._existing_root(project["root_path"]),
            source=pinned,
            node=tool_node,
            values=tool_values,
            authorization=authorization,
            approved=approved,
            project_id=project_id,
        )
        produced_artifacts = self._materialize_produced_artifacts(
            project_id,
            run_id,
            node.id,
            execution.produced_artifacts,
            emit,
        )
        receipt = _json_safe_payload({**execution.receipt, **identity})
        emit(node.id, "tool.completed", receipt)
        tool_calls[-1] = _ToolCallRecord(
            node_id=record.node_id,
            tool_reference=record.tool_reference,
            authorization=record.authorization,
            decision_code=record.decision_code,
            decision_reason=record.decision_reason,
            input_digest=record.input_digest,
            receipt=receipt,
        )
        produced = {**execution.output, **produced_artifacts}
        if definition.implementation.output_mapping:
            produced = {
                definition.implementation.output_mapping.get(name, name): value
                for name, value in produced.items()
            }
        return self._component_output_values(definition, node, produced)

    def _run_agent(
        self,
        project_id: str,
        node: Any,
        source: AgentSource,
        values: dict[str, Any],
        model: RuntimeModelClient,
        knowledge_context: str = "",
        conversation_context: str = "",
        on_token: Callable[[str], None] | None = None,
        *,
        run_id: str | None = None,
        emit: Callable[[str | None, str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if node.model_ref == IMAGE_MODEL_REF:
            return self._run_image_model(project_id, run_id, node, source, values, emit)
        if not model.configured:
            raise RuntimeError(
                "runtime_not_configured",
                "Agent nodes require a Runtime model API key",
            )
        if node.model_ref != PRIMARY_MODEL_REF:
            raise RuntimeError(
                "runtime_model_unknown",
                "Agent model_ref is not the host Runtime profile",
            )
        prompt = self._agent_system_prompt(node, source)
        if "{{" in prompt:
            prompt = _interpolate(prompt, values)
        structured: Mapping[str, TypedField] | None = node.outputs
        if structured:
            prompt = _with_step_contract(prompt, structured)
            response_format = (
                None if _plain_text_field(structured) else {"type": "json_object"}
            )
            emits_outputs = True
        else:
            emits_outputs = _model_writes_agent_outputs(source, node.id)
            if emits_outputs:
                prompt = _with_output_contract(prompt, source.outputs)
            response_format = (
                _runtime_response_format(source.outputs) if emits_outputs else None
            )
        capabilities = runtime_model_capabilities(model.settings)
        user_content: Any = self._model_user_content(
            project_id,
            source,
            values,
            capabilities,
            current_node=node.id,
            fields=node.inputs,
        )
        extra = knowledge_context + conversation_context
        if extra:
            if isinstance(user_content, str):
                user_content = user_content + extra
            else:
                user_content = [
                    *user_content,
                    {"type": "text", "text": extra},
                ]
        user_content = self._provider_user_content(project_id, user_content)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ]
        content = _stream_model_text(model, messages, response_format, on_token)
        if not emits_outputs:
            return {node.id: content}

        def parse(text: str) -> dict[str, Any]:
            if structured:
                return self._structured_step_values(
                    project_id, run_id, node.id, structured, text, emit
                )
            return _model_output_values(text, source.outputs, values, node.id)

        try:
            return parse(content)
        except RuntimeError as exc:
            if exc.code != "agent_output_invalid":
                raise
            repair = [
                *messages,
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        f"Your reply did not match the output contract: {exc}. "
                        "Reply again with only the corrected result."
                    ),
                },
            ]
            if on_token is not None:
                on_token("\n\n")
            return parse(_stream_model_text(model, repair, response_format, on_token))

    def _structured_step_values(
        self,
        project_id: str,
        run_id: str | None,
        node_id: str,
        fields: Mapping[str, TypedField],
        content: str,
        emit: Callable[[str | None, str, dict[str, Any]], None] | None,
    ) -> dict[str, Any]:
        plain = _plain_text_field(fields)
        if plain is not None:
            raw: dict[str, Any] = {plain: content}
        else:
            try:
                raw = _json_object_reply(content)
            except RuntimeError:
                if len(fields) != 1:
                    raise
                name, field = next(iter(fields.items()))
                if field.compact_type != "object" or field.multiple:
                    raise
                raw = {name: {"text": content}}
        result: dict[str, Any] = {}
        for name, field in fields.items():
            if name not in raw or raw[name] is None:
                if field.required:
                    raise RuntimeError(
                        "agent_output_invalid", f"field {name} is missing"
                    )
                continue
            value = raw[name]
            if field.is_artifact():
                value = self._text_artifacts(
                    project_id, run_id, node_id, name, field, value, emit
                )
            else:
                value = _coerce_field_value(field, value)
                if not value_matches_field(field, value):
                    expected = field.compact_type + ("[]" if field.multiple else "")
                    allowed = f" (one of {', '.join(field.enum)})" if field.enum else ""
                    raise RuntimeError(
                        "agent_output_invalid",
                        f"field {name} must be a {expected}{allowed}",
                    )
            result[name] = value
        return {node_id: result, **result}

    def _text_artifacts(
        self,
        project_id: str,
        run_id: str | None,
        node_id: str,
        name: str,
        field: TypedField,
        value: Any,
        emit: Callable[[str | None, str, dict[str, Any]], None] | None,
    ) -> Any:
        """Save model-authored text as document or file artifacts."""

        if field.artifact_kind not in {"document", "file"}:
            raise RuntimeError(
                "agent_output_invalid",
                f"field {name} is a {field.compact_type}; a text model cannot "
                "produce it. Use an image model step for images.",
            )
        items = value if field.multiple and isinstance(value, list) else [value]
        if not all(isinstance(item, str) and item.strip() for item in items):
            raise RuntimeError(
                "agent_output_invalid", f"field {name} must be document text"
            )
        suffix, media = (
            (".md", "text/markdown")
            if field.artifact_kind == "document"
            else (".txt", "text/plain")
        )
        refs = [
            self._store_artifact(
                project_id,
                run_id,
                node_id,
                f"{name}-{index}{suffix}" if len(items) > 1 else f"{name}{suffix}",
                str(item).encode("utf-8"),
                media,
                emit,
            )
            for index, item in enumerate(items, start=1)
        ]
        return refs if field.multiple else refs[0]

    def _store_artifact(
        self,
        project_id: str,
        run_id: str | None,
        node_id: str,
        filename: str,
        contents: bytes,
        claimed_type: str | None,
        emit: Callable[[str | None, str, dict[str, Any]], None] | None,
    ) -> dict[str, Any]:
        try:
            record = self.artifacts.upload(
                project_id,
                filename,
                contents,
                claimed_type=claimed_type,
                source_kind="runtime_output",
                run_id=run_id,
            )
        except ProjectError as exc:
            raise RuntimeError(exc.code, str(exc)) from exc
        if emit is not None:
            emit(
                node_id,
                "artifact.created",
                {
                    "artifact_id": record["artifact_id"],
                    "media_type": record["media_type"],
                    "filename": record["filename"],
                    "size_bytes": record["size_bytes"],
                    "digest": record["sha256"],
                    "node_id": node_id,
                },
            )
        return {
            "kind": "artifact",
            "artifact_id": record["artifact_id"],
            "media_type": record["media_type"],
            "filename": record["filename"],
        }

    def _run_image_model(
        self,
        project_id: str,
        run_id: str | None,
        node: FlowNode,
        source: AgentSource,
        values: dict[str, Any],
        emit: Callable[[str | None, str, dict[str, Any]], None] | None,
    ) -> dict[str, Any]:
        fields = node.outputs or {}
        images = [
            (name, field)
            for name, field in fields.items()
            if field.is_artifact() and field.artifact_kind == "image"
        ]
        if len(images) != 1:
            raise RuntimeError(
                "image_step_invalid",
                "An image generation step needs exactly one image output",
            )
        name, field = images[0]
        prompt = self._agent_system_prompt(node, source)
        if "{{" in prompt:
            prompt = _interpolate(prompt, values)
        try:
            brief = _agent_user_message(source, values)
        except RuntimeError:
            brief = ""
        prompt = "\n\n".join(part for part in (prompt.strip(), brief.strip()) if part)
        if not prompt:
            raise RuntimeError("image_step_invalid", "The image prompt is empty")
        client = self._model_for(project_id, source.agent_id, IMAGE_BINDING_SLOT)
        if not client.configured:
            raise RuntimeError(
                "image_model_not_configured",
                "Bind an image generation model to this Agent before running it",
            )
        count = 2 if field.multiple else 1
        generated: list[GeneratedImage] = []
        try:
            while len(generated) < count:
                batch = client.generate_images(prompt, count=count - len(generated))
                if not batch:
                    break
                generated.extend(batch)
        except RuntimeProviderError as exc:
            raise RuntimeError(exc.code, str(exc)) from exc
        if not generated:
            raise RuntimeError(
                "image_generation_empty", "The image model returned no image"
            )
        refs = [
            self._store_artifact(
                project_id,
                run_id,
                node.id,
                f"{name}-{index}{image.suffix}",
                image.contents,
                image.media_type,
                emit,
            )
            for index, image in enumerate(generated[:_MAX_IMAGES_PER_STEP], start=1)
        ]
        result: dict[str, Any] = {name: refs if field.multiple else refs[0]}
        for other, other_field in fields.items():
            if other != name and other_field.compact_type == "string":
                result[other] = prompt
        return {node.id: result, **result}

    def _provider_user_content(
        self, project_id: str, content: str | list[dict[str, Any]]
    ) -> str | list[dict[str, Any]]:
        if isinstance(content, str):
            return content
        rewritten: list[dict[str, Any]] = []
        for part in content:
            if part.get("type") != "image_url":
                rewritten.append(part)
                continue
            image = part.get("image_url")
            if not isinstance(image, Mapping):
                raise RuntimeError("runtime_request_invalid", "Image part is invalid")
            url = str(image.get("url") or "")
            if url.startswith("artifact://"):
                artifact_id = url.removeprefix("artifact://")
                try:
                    record, payload = self.artifacts.read_bytes(project_id, artifact_id)
                except ProjectError as exc:
                    raise RuntimeError(exc.code, str(exc)) from exc
                encoded = b64encode(payload).decode("ascii")
                rewritten.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{record.media_type};base64,{encoded}",
                        },
                    }
                )
                continue
            lowered = url.casefold()
            if lowered.startswith(("file:", "artifact:")) or url.startswith("/"):
                raise RuntimeError(
                    "runtime_request_invalid",
                    "Image parts cannot use host or artifact URLs",
                )
            rewritten.append(dict(part))
        return rewritten

    def _model_user_content(
        self,
        project_id: str,
        source: AgentSource,
        values: dict[str, Any],
        capabilities: RuntimeModelCapabilities,
        *,
        current_node: str | None = None,
        fields: Mapping[str, TypedField] | None = None,
    ) -> str | list[dict[str, Any]]:
        declared = fields or source.inputs
        extracted: dict[str, str] = {}
        for name, field in declared.items():
            if not field.is_artifact() or field.artifact_kind in {
                "image",
                "collection",
            }:
                continue
            text = self._artifact_plain_text(project_id, field, values.get(name))
            if text:
                extracted[name] = text
        documents: dict[str, str] = {}
        for key, value in _public_values(values).items():
            if key in declared:
                continue
            for ref in _artifact_refs(value):
                artifact_id = artifact_id_from_value(ref)
                media = str(ref.get("media_type") or "")
                if not artifact_id or media.startswith("image/"):
                    continue
                if artifact_id in documents:
                    continue
                try:
                    record, payload = self.artifacts.read_bytes(project_id, artifact_id)
                except ProjectError:
                    continue
                content = extract_document(
                    record.filename, record.media_type, payload, artifact_id
                )
                text = content.plaintext()
                if text:
                    documents[artifact_id] = text
        return _agent_user_content(
            source,
            values,
            capabilities,
            extracted,
            current_node=current_node,
            documents=documents,
            fields=declared,
        )

    def _artifact_plain_text(
        self, project_id: str, field: TypedField, value: Any
    ) -> str:
        items = value if field.multiple and isinstance(value, list) else [value]
        chunks: list[str] = []
        for item in items:
            if not looks_like_artifact_ref(item) or not isinstance(item, Mapping):
                continue
            artifact_id = artifact_id_from_value(item)
            if not artifact_id:
                continue
            try:
                record, payload = self.artifacts.read_bytes(project_id, artifact_id)
            except ProjectError:
                continue
            text = artifact_plain_text(record.filename, record.media_type, payload)
            if text:
                chunks.append(text)
        return "\n".join(chunks)

    def _typed_node_values(
        self,
        store: DataflowStore | None,
        node: FlowNode,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        if store is None:
            return values
        context = store.context_for(node)
        local = dict(values)
        local.update(context.resolved_inputs)
        return local

    def _model_for_node(
        self, project_id: str, source: AgentSource, node: FlowNode
    ) -> RuntimeModelClient:
        slots = [
            node_binding_slot(node.id),
            MODEL_REF_SLOTS.get(node.model_ref or "", RUNTIME_BINDING_SLOT),
        ]
        if node.model_ref == IMAGE_MODEL_REF:
            slots.append(IMAGE_BINDING_SLOT)
        slots.append(RUNTIME_BINDING_SLOT)
        seen: set[str] = set()
        last = self._model_for(project_id, source.agent_id, RUNTIME_BINDING_SLOT)
        for slot in slots:
            if slot in seen:
                continue
            seen.add(slot)
            client = self._model_for(project_id, source.agent_id, slot)
            last = client
            if client.configured:
                return client
        return last

    def _model_for(
        self, project_id: str, agent_id: str, slot: str = RUNTIME_BINDING_SLOT
    ) -> RuntimeModelClient:
        if self.credentials is not None:
            resolved = self.credentials.effective_credential(project_id, agent_id, slot)
            if resolved is not None:
                credential, binding = resolved
                settings = self.model.settings.model_copy(
                    update={
                        "provider_type": credential.provider_type,
                        "model_base_url": credential.base_url,
                        "model_id": binding.model_id,
                        "allow_process_environment_key": False,
                    }
                )
                return RuntimeModelClient(
                    settings,
                    transport=self.model.transport,
                    secret_store=self.model.secret_store,
                    secret_ref=self.credentials.secret_ref(credential.credential_id),
                )
        # Injected transports are test/runtime adapters and do not carry a
        # process credential. Keep them usable for deterministic local tests.
        if self.model.transport is not None:
            return self.model
        # A missing binding is a normal user-action state, not permission to
        # reuse the Platform Builder credential or the shared model.primary ref.
        settings = self.model.settings.model_copy(
            update={"allow_process_environment_key": False}
        )
        return RuntimeModelClient(
            settings,
            transport=None,
            secret_store=self.model.secret_store,
            secret_ref=f"runtime.unbound.{project_id}.{agent_id}.{slot}",
        )

    def _model_evidence(
        self,
        project_id: str,
        agent_id: str,
        model: RuntimeModelClient,
        slot: str = RUNTIME_BINDING_SLOT,
    ) -> dict[str, str]:
        if self.credentials is not None:
            resolved = self.credentials.effective_credential(project_id, agent_id, slot)
            if resolved is not None:
                credential, binding = resolved
                return {
                    "provider": credential.provider_type,
                    "model": binding.model_id,
                    "credential_type": "user",
                    "credential_alias": credential.label,
                    "credential_scope": credential.credential_scope,
                }
        return {
            "provider": model.settings.provider_type,
            "model": model.settings.model_id,
            "credential_type": "test" if model.transport is not None else "unbound",
        }

    def _agent_system_prompt(self, node: Any, source: AgentSource) -> str:
        prompt = node.system_prompt or ""
        for resource in self._skill_resources(source):
            instruction = str(resource["spec"].get("instruction", "")).strip()
            marker = f"[{resource['name']}]"
            if instruction and marker not in prompt:
                block = f"{marker} {instruction}"
                prompt = f"{prompt}\n\n{block}" if prompt else block
        return prompt

    def _skill_resources(self, source: AgentSource) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        for reference in source.skill_refs:
            try:
                resource = self.tools.catalog.by_reference(reference)
            except ResourceCatalogError as exc:
                raise RuntimeError(
                    "skill_not_registered",
                    "Skill reference is not registered in the catalog",
                ) from exc
            if source.lock.get(reference) != resource["content_hash"]:
                raise RuntimeError(
                    "skill_lock_invalid",
                    "Skill lock does not match the catalog version",
                )
            if resource["kind"] != "skill":
                raise RuntimeError("skill_invalid", "Locked skill_ref is not a Skill")
            if resource["availability"] != "ready":
                raise RuntimeError(
                    "skill_unavailable",
                    "Skill is not enabled for local Runtime use",
                )
            resources.append(resource)
        return resources


_BINARY_EVENT_KEYS = frozenset(
    {"bytes", "base64", "contents", "content_b64", "data_base64"}
)


def _json_safe_payload(value: Any) -> Any:
    if isinstance(value, bytes | bytearray):
        raise RuntimeError(
            "event_payload_invalid", "Run events cannot contain binary values"
        )
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            if key in _BINARY_EVENT_KEYS:
                raise RuntimeError(
                    "event_payload_invalid",
                    "Run events cannot contain binary artifact payloads",
                )
            safe[str(key)] = _json_safe_payload(item)
        return safe
    if isinstance(value, list):
        return [_json_safe_payload(item) for item in value]
    return value


def _uses_image_model(source: AgentSource) -> bool:
    return any(
        node.component_type in {ComponentType.AGENT, ComponentType.MODEL}
        and node.model_ref == IMAGE_MODEL_REF
        for node in source.nodes
    )


def _readiness_profile_source(source: str) -> str:
    """Map internal binding sources onto the RuntimeReadiness contract."""

    if source == "explicit":
        return "agent"
    if source in {"agent", "project", "default"}:
        return source
    return "default"


def _runtime_modality_readiness(
    source: AgentSource,
    requires_model: bool,
    modalities: RuntimeModelCapabilities,
) -> dict[str, Any]:
    kinds = {
        field.artifact_kind for field in source.inputs.values() if field.is_artifact()
    }
    if "audio" in kinds or "video" in kinds:
        return {
            "ready": False,
            "code": "unsupported_modality",
            "detail": "Audio/video runtime adapters are not enabled",
        }
    if "image" in kinds and requires_model and modalities.image_input == "unsupported":
        return {
            "ready": False,
            "code": "runtime_model_incompatible",
            "detail": "Runtime model does not support image input",
        }
    if "image" in kinds and requires_model:
        return {
            "ready": True,
            "code": "ready",
            "detail": "Runtime model accepts image input.",
        }
    return {
        "ready": True,
        "code": "ready",
        "detail": "Runtime model modalities match this Agent.",
    }


def _agent_user_content(
    source: AgentSource,
    values: dict[str, Any],
    capabilities: RuntimeModelCapabilities,
    extracted: Mapping[str, str] | None = None,
    *,
    current_node: str | None = None,
    documents: Mapping[str, str] | None = None,
    fields: Mapping[str, TypedField] | None = None,
) -> str | list[dict[str, Any]]:
    image_parts: list[dict[str, Any]] = []
    seen: set[str] = set()
    declared = fields or source.inputs

    def add_image(item: Any, *, required: bool) -> None:
        artifact_id = artifact_id_from_value(item)
        if not artifact_id or artifact_id in seen:
            return
        if len(image_parts) >= _MAX_PROMPT_IMAGES:
            return
        if capabilities.image_input == "unsupported":
            if required:
                raise RuntimeError(
                    "runtime_model_incompatible",
                    "Runtime model does not support image input",
                )
            return
        seen.add(artifact_id)
        media_type = (
            str(item.get("media_type") or "") if isinstance(item, Mapping) else ""
        )
        image_parts.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"artifact://{artifact_id}",
                    "media_type": media_type,
                },
            }
        )

    for name, field in declared.items():
        raw = values.get(name)
        if looks_like_collection_ref(raw) and isinstance(raw, Mapping):
            for item in raw.get("items") or []:
                if looks_like_artifact_ref(item) and str(
                    item.get("media_type") or ""
                ).startswith("image/"):
                    add_image(item, required=field.artifact_kind == "image")
            continue
        if not field.is_artifact() or field.artifact_kind != "image":
            continue
        refs = raw if field.multiple and isinstance(raw, list) else [raw]
        for item in refs:
            if looks_like_artifact_ref(item):
                add_image(item, required=True)
    for key, value in _public_values(values).items():
        if key in declared or key == current_node:
            continue
        for ref in _artifact_refs(value):
            if str(ref.get("media_type") or "").startswith("image/"):
                add_image(ref, required=False)
    text = _agent_user_message(
        source,
        values,
        extracted,
        current_node=current_node,
        documents=documents,
        fields=declared,
    )
    if not image_parts:
        return text
    return [{"type": "text", "text": text}, *image_parts]


def _agent_user_message(
    source: AgentSource,
    values: dict[str, Any],
    extracted: Mapping[str, str] | None = None,
    *,
    current_node: str | None = None,
    documents: Mapping[str, str] | None = None,
    fields: Mapping[str, TypedField] | None = None,
) -> str:
    excerpts = extracted or {}
    public = _public_values(values)
    declared = fields or source.inputs
    parts: list[str] = []
    for name, field in declared.items():
        if name not in public:
            continue
        value = public[name]
        if field.is_artifact():
            parts.append(
                _artifact_prompt_line(name, field, value, excerpts.get(name, ""))
            )
            continue
        parts.append(f"{name}: {_render_value(value)}")
    if fields is None:
        node_ids = {node.id for node in source.nodes}
        labels = source.ui.get("labels") or {}
        covered = {
            field_name
            for node in source.nodes
            if node.outputs and node.id in public
            for field_name in node.outputs
        }
        earlier: list[str] = []
        for key, value in public.items():
            if key in source.inputs or key == current_node or key in covered:
                continue
            heading = f"[{key}]"
            if key in node_ids and labels.get(key):
                heading = f"[{key}] {labels[key]}"
            body = _render_value(value)
            for ref in _artifact_refs(value):
                artifact_id = artifact_id_from_value(ref) or ""
                text = (documents or {}).get(artifact_id)
                if text:
                    body += f"\n{ref.get('filename') or 'document'}:\n{text}"
            earlier.append(f"{heading}\n{_bounded(body)}")
        if earlier:
            parts.append("\nEarlier step results:\n" + "\n\n".join(earlier))
    if not parts:
        raise RuntimeError(
            "agent_input_missing", "Agent nodes need at least one input value"
        )
    return "\n".join(parts)


def _public_values(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if not key.startswith("$")}


def _artifact_refs(value: Any) -> list[Mapping[str, Any]]:
    """Every ArtifactRef nested in a JSON value, depth-first."""

    if looks_like_artifact_ref(value) and isinstance(value, Mapping):
        return [value]
    found: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        for item in value.values():
            found.extend(_artifact_refs(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_artifact_refs(item))
    return found


def _render_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, int | float):
        return str(value)
    if looks_like_artifact_ref(value) and isinstance(value, Mapping):
        kind = str(value.get("media_type") or "file").split("/")[0]
        return f"[{kind}: {value.get('filename') or 'artifact'}]"
    return json.dumps(
        _artifact_placeholders(value), ensure_ascii=False, indent=2, sort_keys=False
    )


def _artifact_placeholders(value: Any) -> Any:
    if looks_like_artifact_ref(value) and isinstance(value, Mapping):
        return _render_value(value)
    if isinstance(value, Mapping):
        return {key: _artifact_placeholders(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_artifact_placeholders(item) for item in value]
    return value


def _bounded(text: str, limit: int = _MAX_VALUE_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…[truncated]"


def _output_preview(value: Any) -> Any:
    """A JSON-safe, size-bounded copy of a step result for run events."""

    if isinstance(value, str):
        return _bounded(value, _MAX_PREVIEW_CHARS)
    if isinstance(value, Mapping):
        if looks_like_artifact_ref(value):
            return dict(value)
        return {
            str(key): _output_preview(item)
            for key, item in value.items()
            if not str(key).startswith("$")
        }
    if isinstance(value, list):
        return [_output_preview(item) for item in value[:50]]
    return value


def _approval_details(
    node: FlowNode, values: Mapping[str, Any], round_number: int
) -> dict[str, Any]:
    details: dict[str, Any] = {"round": round_number}
    if node.bounded_revisions:
        details["max_revisions"] = node.bounded_revisions
        details["revisions_left"] = max(0, node.bounded_revisions - round_number + 1)
    if node.review:
        try:
            review = resolve_value_path(values, tuple(node.review.split(".")))
        except KeyError:
            review = None
        if review is not None:
            details["review"] = _output_preview(review)
    return details


def _stream_model_text(
    model: RuntimeModelClient,
    messages: list[dict[str, Any]],
    response_format: Mapping[str, Any] | None,
    on_token: Callable[[str], None] | None,
) -> str:
    fragments: list[str] = []
    for token in model.stream(messages, response_format=response_format):
        if not isinstance(token, str) or not token:
            continue
        fragments.append(token)
        if on_token is not None:
            on_token(token)
    return "".join(fragments).strip()


_TEXT_ARTIFACT_KINDS = frozenset({"document", "file"})


def _plain_text_field(fields: Mapping[str, TypedField]) -> str | None:
    """A single text-like step output is returned as plain text, not JSON."""

    if len(fields) != 1:
        return None
    name, field = next(iter(fields.items()))
    if field.multiple or field.enum:
        return None
    if field.type == "string":
        return name
    if field.is_artifact() and field.artifact_kind in _TEXT_ARTIFACT_KINDS:
        return name
    return None


def _field_contract_line(name: str, field: TypedField) -> str:
    kind: str = field.compact_type
    if field.is_artifact() and field.artifact_kind == "document":
        kind = "document (Markdown text)"
    elif field.is_artifact() and field.artifact_kind == "file":
        kind = "file (plain text contents)"
    elif field.type == "table":
        kind = "table (array of row objects with the same keys)"
    if field.multiple:
        kind = f"list of {kind}"
    line = f"- {name}: {kind}"
    if field.enum:
        choices = ", ".join(json.dumps(item, ensure_ascii=False) for item in field.enum)
        line += f"; one of {choices}"
    if not field.required:
        line += "; optional"
    if field.description:
        line += f" — {field.description}"
    return line


def _with_step_contract(prompt: str, fields: Mapping[str, TypedField]) -> str:
    lines = [_field_contract_line(name, field) for name, field in fields.items()]
    plain = _plain_text_field(fields)
    if plain is not None:
        contract = (
            "Runtime output contract (authoritative): reply with only the content "
            f"of `{plain}`, no preamble and no JSON wrapper.\n" + "\n".join(lines)
        )
    else:
        skeleton = {name: "…" for name in fields}
        contract = (
            "Runtime output contract (authoritative): reply with one JSON object "
            "using exactly these keys. Do not ask the user questions; if a fact is "
            "missing, state a reasonable assumption inside the result.\n"
            + "\n".join(lines)
            + "\nShape: "
            + json.dumps(skeleton, ensure_ascii=False)
        )
    return f"{prompt}\n\n{contract}" if prompt else contract


_FENCE = re.compile(r"^```[a-zA-Z0-9_-]*\s*\n(?P<body>.*)\n```\s*$", re.DOTALL)


def _json_reply(content: str) -> Any:
    text = content.strip()
    fenced = _FENCE.match(text)
    if fenced is not None:
        text = fenced.group("body").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "agent_output_invalid", "the reply is not valid JSON"
        ) from exc


def _json_object_reply(content: str) -> dict[str, Any]:
    parsed = _json_reply(content)
    if not isinstance(parsed, dict):
        raise RuntimeError("agent_output_invalid", "the reply is not a JSON object")
    return parsed


def _coerce_field_value(field: TypedField, value: Any) -> Any:
    """Repair obvious JSON shape slips without guessing content."""

    if field.multiple:
        if not isinstance(value, list):
            value = [value]
        inner = replace(field, multiple=False)
        return [_coerce_field_value(inner, item) for item in value]
    if field.type == "string":
        if isinstance(value, int | float) and not isinstance(value, bool):
            value = str(value)
        if isinstance(value, str) and field.enum and value not in field.enum:
            folded = {item.casefold(): item for item in field.enum}
            return folded.get(value.strip().casefold(), value)
        if isinstance(value, dict | list):
            return json.dumps(value, ensure_ascii=False)
        return value
    if field.type == "integer" and isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return value
    if field.type == "number" and isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return value
    if field.type == "boolean" and isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in {"true", "yes", "是"}:
            return True
        if lowered in {"false", "no", "否"}:
            return False
    if field.type in {"object", "array", "table"} and isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _artifact_prompt_line(
    name: str, field: TypedField, value: Any, extracted: str = ""
) -> str:
    items = value if field.multiple and isinstance(value, list) else [value]
    labels: list[str] = []
    for item in items:
        filename = ""
        if looks_like_artifact_ref(item) and isinstance(item, Mapping):
            filename = str(item.get("filename") or "")
        labels.append(filename or "artifact")
    line = f"{name}: [{field.compact_type} {', '.join(labels)}]"
    if extracted:
        return f"{line}\n{extracted}"
    return line


def _model_writes_agent_outputs(source: AgentSource, node_id: str) -> bool:
    """True when this Model can reach Output before another Model node."""

    outgoing: dict[str, list[str]] = {}
    kinds = {node.id: node.component_type for node in source.nodes}
    for edge in source.transitions:
        outgoing.setdefault(edge.from_node, []).append(edge.to_node)
    seen: set[str] = set()
    pending = list(outgoing.get(node_id, []))
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        kind = kinds.get(current)
        if kind is ComponentType.OUTPUT:
            return True
        if kind in {ComponentType.MODEL, ComponentType.AGENT}:
            continue
        pending.extend(outgoing.get(current, []))
    return False


def _bind_blank_approval_condition(
    source: AgentSource,
    next_node: str,
    decision: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    """Treat a blank approval as the Condition's confirm literal.

    Generated graphs often compare a free-text input such as ``decision`` to
    ``confirm``, while the approval card only offers approve/reject. Approve
    with an empty field takes the true branch; an explicit value is kept.
    """

    if decision != "approved":
        return values
    node = next((item for item in source.nodes if item.id == next_node), None)
    if (
        node is None
        or node.component_type is not ComponentType.CONDITION
        or not node.expression
    ):
        return values
    try:
        parsed = parse_condition_expression(node.expression)
    except ContractValidationError:
        return values
    if parsed.operator != "==" or len(parsed.path) != 1:
        return values
    current = values.get(parsed.field)
    if current is None or (isinstance(current, str) and not current.strip()):
        updated = dict(values)
        updated[parsed.field] = parsed.literal
        return updated
    return values


def _json_outputs_required(outputs: Mapping[str, TypedField]) -> bool:
    targets = list(outputs.items())
    if not targets:
        return False
    return not (
        len(targets) == 1
        and targets[0][1].compact_type == "string"
        and not targets[0][1].multiple
    )


def _runtime_response_format(
    outputs: Mapping[str, TypedField],
) -> dict[str, str] | None:
    if not _json_outputs_required(outputs):
        return None
    return {"type": "json_object"}


def _with_output_contract(prompt: str, outputs: Mapping[str, TypedField]) -> str:
    if not _json_outputs_required(outputs):
        return prompt
    fields = "\n".join(
        f"- {name} ({field.compact_type})" for name, field in outputs.items()
    )
    contract = (
        "Runtime output contract (authoritative): return one JSON object with "
        "exactly these declared fields; do not rename, omit, or add fields.\n"
        f"{fields}"
    )
    return f"{prompt}\n\n{contract}" if prompt else contract


def _model_output_values(
    content: str,
    outputs: Mapping[str, TypedField],
    values: dict[str, Any],
    node_id: str,
) -> dict[str, Any]:
    """Accept declared outputs; later Model nodes may overwrite earlier results."""

    recorded = {} if node_id in outputs else {node_id: content}
    # Model output fields are allowed to reuse an input name. For example, a
    # review Agent can accept ``status`` and return the normalized/decided
    # ``status``. The model response is the authoritative value for every
    # declared output; filtering names already present in ``values`` would
    # turn a multi-field JSON response into a string-valued field.
    targets = list(outputs.items())
    if (
        len(targets) == 1
        and targets[0][1].compact_type == "string"
        and not targets[0][1].multiple
    ):
        return {**recorded, targets[0][0]: content}
    try:
        parsed: Any = _json_reply(content)
    except RuntimeError as exc:
        raise RuntimeError(
            "agent_output_invalid", "Agent model did not return valid JSON outputs"
        ) from exc
    if len(targets) == 1:
        name, field = targets[0]
        if not value_matches_field(field, parsed):
            raise RuntimeError(
                "agent_output_invalid",
                f"Agent output {name} is not a {field.compact_type}",
            )
        return {**recorded, name: parsed}
    if not isinstance(parsed, dict) or set(parsed) != {name for name, _ in targets}:
        raise RuntimeError(
            "agent_output_invalid", "Agent model output fields do not match the Agent"
        )
    if not all(value_matches_field(field, parsed[name]) for name, field in targets):
        raise RuntimeError(
            "agent_output_invalid", "Agent model output types are invalid"
        )
    return {**recorded, **parsed}


def _lookup(values: Mapping[str, Any], path: str) -> Any:
    if path.startswith("$"):
        raise RuntimeError("interpolation_missing", f"field {path} is unavailable")
    try:
        return resolve_value_path(values, tuple(path.split(".")))
    except KeyError as exc:
        raise RuntimeError(
            "interpolation_missing", f"field {path} is unavailable"
        ) from exc


def _interpolate(template: str, values: dict[str, Any]) -> str:
    leftover = TEMPLATE_TOKEN_RE.sub("", template)
    if "{{" in leftover or "}}" in leftover:
        raise RuntimeError(
            "interpolation_invalid",
            "Templates only accept {{field}} or {{step.field}} references",
        )
    return TEMPLATE_TOKEN_RE.sub(
        lambda match: _render_value(_lookup(values, match.group(1))), template
    )


def _transform_value(template: str, values: dict[str, Any]) -> Any:
    """A whole-value reference keeps its type; mixed text renders a string."""

    whole = TEMPLATE_TOKEN_RE.fullmatch(template.strip())
    if whole is not None:
        return _lookup(values, whole.group(1))
    return _interpolate(template, values)


def _condition(expression: str, values: dict[str, Any]) -> bool:
    try:
        parsed = parse_condition_expression(expression)
    except ContractValidationError as exc:
        raise RuntimeError("condition_invalid", str(exc)) from exc
    try:
        return parsed.evaluate(values)
    except KeyError as exc:
        raise RuntimeError(
            "condition_invalid",
            f"Condition references {parsed.field}, which is unavailable at runtime",
        ) from exc
    except ValueError as exc:
        raise RuntimeError("condition_invalid", str(exc)) from exc


def _check(check: str, values: dict[str, Any]) -> bool:
    if check == "output.not_empty":
        return any(bool(value) for value in values.values())
    if check == "schema_valid":
        result = values.get("result")
        return isinstance(result, dict)
    if check.startswith("required_fields:"):
        name = check.split(":", 1)[1]
        return name in values and values[name] not in {None, "", []}
    if check.startswith("artifact_exists:"):
        name = check.split(":", 1)[1]
        return bool(values.get(name))
    if check.startswith("constraint_match:"):
        expression = check.split(":", 1)[1]
        return _condition(expression, values)
    raise RuntimeError("verifier_invalid", f"unsupported verifier check: {check}")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sse_frame(event: str, data: dict[str, Any], event_id: str | None = None) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {payload}")
    return "\n".join(lines) + "\n\n"
