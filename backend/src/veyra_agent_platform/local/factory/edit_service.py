"""Generate source-only proposals; explicit commands own all Draft mutations."""

from __future__ import annotations

import json
from contextlib import suppress
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any, Literal

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.common import ContractValidationError, new_uuid7
from veyra_agent_platform.contracts.custom_component import CustomComponentDefinition
from veyra_agent_platform.contracts.workflow import WorkflowSource
from veyra_agent_platform.local.builder.component_planning import (
    matching_existing_component,
)
from veyra_agent_platform.local.builder.composite_apply import (
    CompositeApplyError,
    apply_composite,
)
from veyra_agent_platform.local.builder.harness import BuilderHarness
from veyra_agent_platform.local.builder.knowledge_binding import (
    bind_knowledge,
    knowledge_readiness,
    resolve_knowledge,
)
from veyra_agent_platform.local.builder.resource_binding import (
    FILESYSTEM_READ_RESOURCE_ID,
    ResourceMutationError,
    bind_project_tool,
    is_resource_binding_intent,
    resolve_project_resource,
    resource_readiness,
)
from veyra_agent_platform.local.builder.validation_repair import (
    ValidationRepairError,
    project_issues,
    repair_agent_source,
    repair_plan,
    select_issue,
)
from veyra_agent_platform.local.library.dependencies import inspect_agent_dependencies
from veyra_agent_platform.local.library.resource_truth import pin_catalog_locks
from veyra_agent_platform.local.library.service import DraftConflict, LibraryService
from veyra_agent_platform.local.library.workflow_dependencies import (
    resolve_workflow_calls,
)
from veyra_agent_platform.local.projects.custom_components import (
    CustomComponentError,
    CustomComponentService,
)
from veyra_agent_platform.local.projects.service import ProjectError
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.resources.project import (
    ProjectResourceError,
    ProjectResourceService,
)
from veyra_agent_platform.local.resources.readiness import ResourceReadiness

from .client import KimiClient
from .edit_store import EditProposalStore
from .service import FactoryError

TargetKind = Literal["agent", "workflow"]
ProposalTargetKind = Literal["agent", "workflow", "custom_component"]
COMPONENT_PROPOSAL_KIND = "create_custom_component"
AGENT_CREATION_PROPOSAL_KIND = "create_agent"
WORKFLOW_CREATION_PROPOSAL_KIND = "create_workflow"
EditCommand = Literal["apply", "reject", "undo"]
MAX_SOURCE_BYTES = 200_000


class KnowledgeBindingUnresolved(Exception):
    """No single Project Knowledge document matched; the caller must clarify."""

    def __init__(self, status: str, candidates: tuple[dict[str, Any], ...]) -> None:
        super().__init__(f"knowledge mention is {status}")
        self.status = status
        self.candidates = tuple(
            {
                "knowledge_id": str(item["knowledge_id"]),
                "name": str(item.get("name") or ""),
                "version": str(item["version"]),
            }
            for item in candidates
        )


class ResourceBindingUnresolved(Exception):
    """No single Project-owned Tool matched; the caller must clarify or stop."""

    def __init__(self, status: str, candidates: tuple[dict[str, Any], ...]) -> None:
        super().__init__(f"resource mention is {status}")
        self.status = status
        self.candidates = tuple(
            {
                "reference": str(item["reference"]),
                "name": str(item.get("name") or ""),
            }
            for item in candidates
        )


class EditProposalService:
    def __init__(
        self,
        store: EditProposalStore,
        library: LibraryService,
        catalog: ResourceCatalog,
        client: KimiClient,
        *,
        project_resources: ProjectResourceService,
        resource_readiness: ResourceReadiness,
        custom_components: CustomComponentService,
        entity_store: Any | None = None,
    ) -> None:
        self.store = store
        self.library = library
        self.catalog = catalog
        self.client = client
        self.project_resources = project_resources
        self.resource_readiness = resource_readiness
        self.custom_components = custom_components
        self.entity_store = entity_store
        self.harness = BuilderHarness(library.projects, catalog)

    def create_agent_proposal(
        self,
        project_id: str,
        *,
        candidate: dict[str, Any],
        conversation_id: str,
        operation_id: str,
        factory_session_id: str,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Persist one immutable review snapshot for a Factory Agent candidate."""
        existing = self.store.builder_operation(project_id, operation_id)
        if existing is not None and persist:
            return self.get(project_id, existing["proposal_id"])
        raw_source = candidate.get("source")
        if not isinstance(raw_source, dict):
            raise FactoryError(
                "agent_proposal_invalid", "The Factory candidate source is missing"
            )
        source_model = AgentSource.from_dict(raw_source)
        source = source_model.to_dict()
        proposal_id = new_uuid7()
        proposal: dict[str, Any] = {
            "schema_version": "1.0",
            "proposal_id": proposal_id,
            "proposal_kind": AGENT_CREATION_PROPOSAL_KIND,
            "project_id": project_id,
            "target_kind": "agent",
            "target_id": source["agent_id"],
            "instruction": "Create the reviewed Agent Draft",
            "created_at": datetime.now(UTC).isoformat(),
            "candidate_source": source,
            "candidate_hashes": {
                "source_hash": source_model.source_hash,
                "behavior_hash": source_model.behavior_hash,
                "lock_hash": source_model.lock_hash,
            },
            "candidate_blueprint": deepcopy(candidate.get("blueprint") or {}),
            "resource_plan": deepcopy(candidate.get("resource_plan") or []),
            "required_project_resources": deepcopy(
                candidate.get("required_project_resources") or []
            ),
            "semantic_plan": deepcopy(candidate.get("semantic_plan")),
            "identity": deepcopy(candidate.get("identity") or {}),
            "conversation_id": conversation_id,
            "operation_id": operation_id,
            "builder_creation_operation_id": operation_id,
            "factory_session_id": factory_session_id,
            "changes": [],
            "permission_changes": [],
            "impact": {
                "target_kind": "agent",
                "target_id": source["agent_id"],
                "scope": "agent_creation",
                "immutable_versions_changed": False,
                "runs_started": False,
                "creates_agent": True,
            },
            "validation": {
                "valid": True,
                "run_availability": candidate.get("run_availability", "unknown"),
            },
            "state": "review",
        }
        if persist:
            self.store.create(proposal)
            return self.get(project_id, proposal_id)
        return proposal

    def apply_agent_creation_proposal(
        self,
        project_id: str,
        proposal_id: str,
        *,
        confirm: bool,
    ) -> dict[str, Any]:
        """Install exactly the persisted create-agent Proposal snapshot."""
        if not confirm:
            raise FactoryError(
                "edit_confirmation_required", "Explicit confirmation is required"
            )
        proposal = self.store.get(project_id, proposal_id)
        if proposal is None:
            raise FactoryError("edit_proposal_not_found", "Edit proposal was not found")
        if proposal.get("proposal_kind") != AGENT_CREATION_PROPOSAL_KIND:
            raise FactoryError(
                "agent_proposal_kind_invalid",
                "The supplied Proposal is not an Agent creation Proposal",
            )
        if proposal.get("state") == "applied":
            return self.get(project_id, proposal_id)
        if proposal.get("state") != "review":
            raise FactoryError(
                "edit_proposal_closed", "This Proposal cannot be applied"
            )
        try:
            source = AgentSource.from_dict(proposal["candidate_source"])
        except (ContractValidationError, TypeError, ValueError) as exc:
            raise FactoryError(
                "agent_proposal_snapshot_invalid",
                "The persisted Agent Proposal snapshot is invalid",
            ) from exc
        hashes = proposal.get("candidate_hashes")
        if not isinstance(hashes, dict) or any(
            hashes.get(key) != value
            for key, value in {
                "source_hash": source.source_hash,
                "behavior_hash": source.behavior_hash,
                "lock_hash": source.lock_hash,
            }.items()
        ):
            raise FactoryError(
                "agent_proposal_snapshot_invalid",
                "The persisted Agent Proposal snapshot hash does not match",
            )
        try:
            pin_catalog_locks(self.project_resources, self.catalog, project_id, source)
        except ProjectResourceError as exc:
            raise FactoryError(exc.code, str(exc)) from exc
        dependencies = inspect_agent_dependencies(
            self.library.projects,
            self.catalog,
            project_id,
            source,
            resource_projection=self.resource_readiness.project,
        )
        blocking = [
            item
            for item in dependencies["dependencies"]
            if item.get("status") not in {"ready", "configuration_required"}
        ]
        if blocking:
            raise FactoryError(
                "agent_proposal_stale",
                "Project dependencies changed since this Proposal was reviewed",
            )
        try:
            existing = self.library.projects.agent_summary(project_id, source.agent_id)
        except ProjectError:
            existing = None
        if existing is not None:
            try:
                current = self.library.draft(project_id, source.agent_id)
            except (DraftConflict, ProjectError):
                current = None
            if current is None or current.get("source") != source.to_dict():
                raise FactoryError(
                    "agent_proposal_identity_conflict",
                    "The Proposal Agent identity is already used by another source",
                )
            self.store.mark_applied(proposal_id, source.agent_id, existing)
            return self.get(project_id, proposal_id)
        try:
            installed = self.library.projects.create_agent_from_source(
                project_id=project_id,
                source=source,
                preserve_identity=True,
            )
        except ProjectError as exc:
            raise FactoryError("agent_proposal_apply_failed", str(exc)) from exc
        self.store.mark_applied(proposal_id, source.agent_id, installed)
        return self.get(project_id, proposal_id)

    def create_workflow_proposal(
        self,
        project_id: str,
        *,
        candidate: dict[str, Any],
        conversation_id: str,
        operation_id: str,
        factory_session_id: str,
        persist: bool = True,
    ) -> dict[str, Any]:
        existing = self.store.builder_operation(project_id, operation_id)
        if existing is not None and persist:
            return self.get(project_id, existing["proposal_id"])
        workflow = candidate.get("workflow")
        companions = candidate.get("companions")
        if not isinstance(workflow, dict) or not isinstance(companions, list):
            raise FactoryError(
                "workflow_proposal_invalid",
                "The Factory Workflow candidate is missing",
            )
        parsed_companions = [AgentSource.from_dict(item) for item in companions]
        proposal_id = new_uuid7()
        proposal: dict[str, Any] = {
            "schema_version": "1.0",
            "proposal_id": proposal_id,
            "proposal_kind": WORKFLOW_CREATION_PROPOSAL_KIND,
            "project_id": project_id,
            "target_kind": "workflow",
            "target_id": str(workflow.get("workflow_id") or proposal_id),
            "instruction": "Create the reviewed Workflow Draft",
            "created_at": datetime.now(UTC).isoformat(),
            "candidate_workflow": deepcopy(workflow),
            "candidate_companions": [item.to_dict() for item in parsed_companions],
            "flow": list(candidate.get("flow") or []),
            "identity": deepcopy(candidate.get("identity") or {}),
            "entity_schema": deepcopy(candidate.get("entity_schema") or {}),
            "execution_plan": deepcopy(candidate.get("execution_plan") or {}),
            "conversation_id": conversation_id,
            "operation_id": operation_id,
            "builder_creation_operation_id": operation_id,
            "factory_session_id": factory_session_id,
            "changes": [],
            "permission_changes": [],
            "impact": {
                "target_kind": "workflow",
                "target_id": str(workflow.get("workflow_id") or proposal_id),
                "scope": "workflow_creation",
                "immutable_versions_changed": True,
                "runs_started": False,
                "creates_workflow": True,
            },
            "validation": {"valid": True, "run_availability": "requires_configuration"},
            "state": "review",
        }
        if persist:
            self.store.create(proposal)
            return self.get(project_id, proposal_id)
        return proposal

    def apply_workflow_creation_proposal(
        self,
        project_id: str,
        proposal_id: str,
        *,
        confirm: bool,
    ) -> dict[str, Any]:
        if not confirm:
            raise FactoryError(
                "edit_confirmation_required", "Explicit confirmation is required"
            )
        proposal = self.store.get(project_id, proposal_id)
        if proposal is None:
            raise FactoryError("edit_proposal_not_found", "Edit proposal was not found")
        if proposal.get("proposal_kind") != WORKFLOW_CREATION_PROPOSAL_KIND:
            raise FactoryError(
                "workflow_proposal_kind_invalid",
                "The supplied Proposal is not a Workflow creation Proposal",
            )
        if proposal.get("state") == "applied":
            return self.get(project_id, proposal_id)
        if proposal.get("state") != "review":
            raise FactoryError(
                "edit_proposal_closed", "This Proposal cannot be applied"
            )
        companions = tuple(
            AgentSource.from_dict(item)
            for item in proposal.get("candidate_companions") or []
        )
        entity_schema = proposal.get("entity_schema")
        if not isinstance(entity_schema, dict) or not entity_schema:
            entity_schema = None
        try:
            result = apply_composite(
                projects=self.library.projects,
                library=self.library,
                project_id=project_id,
                companions=companions,
                workflow=deepcopy(proposal["candidate_workflow"]),
                flow=tuple(proposal.get("flow") or []),
                entity_schema=entity_schema,
                entity_store=self.entity_store,
            )
        except CompositeApplyError as exc:
            raise FactoryError(exc.code, str(exc)) from exc
        self.store.mark_applied(
            proposal_id, str(result.get("workflow_id") or ""), result
        )
        return self.get(project_id, proposal_id)

    def create_component_proposal(
        self,
        project_id: str,
        component_plan: dict[str, Any],
        *,
        conversation_id: str,
        operation_id: str,
        factory_session_id: str | None,
        continuation: Literal["agent", "direct_component"],
    ) -> dict[str, Any]:
        existing = self.store.builder_operation(project_id, operation_id)
        if (
            existing is not None
            and existing.get("proposal_kind") == COMPONENT_PROPOSAL_KIND
        ):
            return self.get(project_id, existing["proposal_id"])
        plan = deepcopy(component_plan)
        implementation = plan.get("implementation")
        if not isinstance(implementation, dict):
            raise FactoryError(
                "component_plan_invalid", "Component implementation is missing"
            )
        if implementation.get("kind") == "model_recipe":
            configured = self.custom_components.model_recipe_configured
            plan["readiness_expectation"] = (
                "ready"
                if configured is None or configured()
                else "requires_configuration"
            )
        elif plan.get("readiness_expectation") == "runtime_dependent":
            plan["readiness_expectation"] = "unavailable"

        proposal_id = new_uuid7()
        plan["component_id"] = new_uuid7()
        capability_name = str(
            plan.get("capability_requirement")
            or plan.get("display_name")
            or "Custom Component"
        )[:240]
        proposal: dict[str, Any] = {
            "schema_version": "1.0",
            "proposal_id": proposal_id,
            "proposal_kind": COMPONENT_PROPOSAL_KIND,
            "project_id": project_id,
            "target_kind": "custom_component",
            "target_id": proposal_id,
            "instruction": f"Create reusable capability: {capability_name}",
            "created_at": datetime.now(UTC).isoformat(),
            "component_plan": plan,
            "continuation": continuation,
            "conversation_id": conversation_id,
            "operation_id": operation_id,
            "factory_session_id": factory_session_id,
            "changes": [],
            "permission_changes": [],
            "impact": {
                "target_kind": "custom_component",
                "target_id": proposal_id,
                "scope": "project_resource",
                "immutable_versions_changed": False,
                "runs_started": False,
                "creates_component": True,
            },
            "validation": {
                "valid": True,
                "readiness_expectation": plan["readiness_expectation"],
                "dependencies": deepcopy(plan.get("dependencies") or []),
            },
            "state": "review",
        }
        self._validate_component_draft_plan(project_id, proposal)
        self.store.create(proposal)
        return self.get(project_id, proposal_id)

    def get_proposal(self, project_id: str, proposal_id: str) -> dict[str, Any]:
        return self.get(project_id, proposal_id)

    def _validate_component_draft_plan(
        self, project_id: str, proposal: dict[str, Any]
    ) -> None:
        plan = proposal.get("component_plan")
        allowed = {
            "component_id",
            "display_name",
            "description",
            "capability_requirement",
            "agent_step",
            "agent_step_key",
            "inputs",
            "outputs",
            "implementation",
            "dependencies",
            "required_permissions",
            "readiness_expectation",
            "why",
        }
        if not isinstance(plan, dict) or set(plan) - allowed:
            raise FactoryError(
                "component_plan_invalid", "Component plan contains unsupported fields"
            )
        if not {
            "component_id",
            "display_name",
            "description",
            "inputs",
            "outputs",
            "implementation",
            "dependencies",
            "required_permissions",
            "readiness_expectation",
        } <= set(plan):
            raise FactoryError(
                "component_plan_invalid", "Component plan is missing required fields"
            )
        if plan["readiness_expectation"] not in {
            "ready",
            "requires_configuration",
        }:
            raise FactoryError(
                "component_plan_invalid", "Component readiness expectation is invalid"
            )
        now = datetime.now(UTC).isoformat()
        try:
            definition = CustomComponentDefinition.from_dict(
                {
                    "schema_version": "1.0",
                    "component_id": plan["component_id"],
                    "project_id": project_id,
                    "slug": "component-proposal",
                    "display_name": plan["display_name"],
                    "description": plan["description"],
                    "version": "0.0.0",
                    "inputs": plan["inputs"],
                    "outputs": plan["outputs"],
                    "implementation": plan["implementation"],
                    "metadata": {},
                    "dependencies": plan["dependencies"],
                    "required_permissions": plan["required_permissions"],
                    "provenance": "builder",
                    "lifecycle": "draft",
                    "created_at": now,
                    "updated_at": now,
                }
            )
        except (ContractValidationError, TypeError, ValueError) as exc:
            raise FactoryError(
                "component_plan_invalid", "Component plan failed contract validation"
            ) from exc

        implementation = definition.implementation
        dependencies = [item.to_dict() for item in definition.dependencies]
        if implementation.kind.value == "tool_wrapper":
            if (
                len(dependencies) != 1
                or dependencies[0]["reference"] != implementation.tool_reference
            ):
                raise FactoryError(
                    "component_plan_invalid", "Tool wrapper needs one exact Tool pin"
                )
            resource = next(
                (
                    item
                    for item in self.project_resources.list(project_id)["resources"]
                    if item.get("scope") == "project"
                    and item.get("reference") == implementation.tool_reference
                ),
                None,
            )
            if (
                resource is None
                or resource.get("bound_content_hash") != dependencies[0]["content_hash"]
                or resource.get("required_permissions")
                != definition.required_permissions.to_dict()
            ):
                raise FactoryError(
                    "component_plan_stale", "The exact Project-bound Tool pin changed"
                )
        elif dependencies or any(definition.required_permissions.to_dict().values()):
            raise FactoryError(
                "component_plan_invalid",
                "Model and Transform components must have no external "
                "dependencies or permissions",
            )

    def _component_proposal_stale(
        self, project_id: str, proposal: dict[str, Any]
    ) -> bool:
        if self.custom_components.find_builder_proposal(
            project_id, proposal["proposal_id"]
        ):
            return False
        plan = proposal["component_plan"]
        requirement = str(plan.get("capability_requirement") or plan["display_name"])
        if matching_existing_component(
            self.project_resources.list(project_id)["resources"], requirement
        ):
            return True
        implementation = plan["implementation"]
        if implementation.get("kind") == "model_recipe":
            configured = self.custom_components.model_recipe_configured
            current = (
                "ready"
                if configured is None or configured()
                else "requires_configuration"
            )
            if current != plan["readiness_expectation"]:
                return True
        try:
            self._validate_component_draft_plan(project_id, proposal)
        except (FactoryError, ContractValidationError, ProjectError):
            return True
        return False

    def _apply_component_proposal(
        self, project_id: str, proposal: dict[str, Any]
    ) -> None:
        plan = proposal["component_plan"]
        self._validate_component_draft_plan(project_id, proposal)
        existing = self.custom_components.find_builder_proposal(
            project_id, proposal["proposal_id"]
        )
        if existing is not None and existing.get("version") != "0.0.0":
            return
        if existing is None:
            if self._component_proposal_stale(project_id, proposal):
                raise DraftConflict(
                    "Project capabilities or Runtime readiness changed; "
                    "review a new Component proposal"
                )
            metadata = {
                "builder.proposal_id": proposal["proposal_id"],
                "builder.conversation_id": proposal["conversation_id"],
                "builder.operation_id": proposal["operation_id"],
            }
            payload = {
                "display_name": plan["display_name"],
                "description": plan["description"],
                "inputs": plan["inputs"],
                "outputs": plan["outputs"],
                "implementation": plan["implementation"],
                "dependencies": plan["dependencies"],
                "required_permissions": plan["required_permissions"],
                "provenance": "builder",
                "metadata": metadata,
            }
            draft = self.custom_components.create_draft(
                project_id,
                payload,
                component_id=plan["component_id"],
            )
            component_id = str(draft["component_id"])
        else:
            component_id = str(existing["component_id"])
            if not self._component_definition_matches_plan(
                existing, plan, proposal_id=str(proposal["proposal_id"])
            ):
                raise DraftConflict(
                    "The Component draft changed after proposal review; "
                    "create a new proposal"
                )

        try:
            validated = self.custom_components.validate(project_id, component_id)
            if validated.get("readiness") != plan["readiness_expectation"]:
                self.custom_components.delete_draft(project_id, component_id)
                raise DraftConflict(
                    "Runtime readiness changed since review; no Component was published"
                )
            self.custom_components.publish(project_id, component_id)
        except DraftConflict:
            raise
        except (CustomComponentError, ContractValidationError, ProjectError) as exc:
            with suppress(CustomComponentError):
                draft_now = self.custom_components.get(
                    project_id, component_id, version="0.0.0"
                )
                if (
                    draft_now.get("metadata", {}).get("builder.proposal_id")
                    == proposal["proposal_id"]
                ):
                    self.custom_components.delete_draft(project_id, component_id)
            raise FactoryError(
                "component_validation_failed",
                "The Component did not pass validation and was not published.",
            ) from exc

    @staticmethod
    def _component_definition_matches_plan(
        existing: dict[str, Any], plan: dict[str, Any], *, proposal_id: str
    ) -> bool:
        return (
            all(
                existing.get(key) == plan.get(key)
                for key in (
                    "component_id",
                    "display_name",
                    "description",
                    "inputs",
                    "outputs",
                    "implementation",
                    "dependencies",
                )
            )
            and existing.get("metadata", {}).get("builder.proposal_id") == proposal_id
        )

    def draft(
        self, project_id: str, kind: TargetKind, target_id: str
    ) -> dict[str, Any]:
        reader = (
            self.library.workflow_draft if kind == "workflow" else self.library.draft
        )
        return reader(project_id, target_id)

    def create(
        self,
        project_id: str,
        kind: TargetKind,
        target_id: str,
        instruction: str,
        expected_revision: int,
        expected_etag: str,
    ) -> dict[str, Any]:
        base = self.draft(project_id, kind, target_id)
        if base["revision"] != expected_revision or base["etag"] != expected_etag:
            raise DraftConflict(
                "Save or reload the current Draft before proposing edits"
            )
        if not instruction.strip():
            raise FactoryError("edit_instruction_empty", "Describe the change first")
        permissions = base["source"]["extensions"]["veyra"]["permissions"]
        if any(
            Path(root).is_absolute() or PureWindowsPath(root).is_absolute()
            for field in ("filesystem_read_roots", "filesystem_write_roots")
            for root in permissions.get(field, [])
        ):
            raise FactoryError(
                "edit_source_host_paths",
                "Use Project-relative filesystem permissions before sending this "
                "source to Builder. The Draft is unchanged.",
            )
        encoded = json.dumps(base["source"], ensure_ascii=False)
        if len(encoded.encode()) > MAX_SOURCE_BYTES:
            raise FactoryError(
                "edit_source_too_large", "This source exceeds the edit limit"
            )
        schema = _source_schema(kind)
        messages = self.harness.messages(
            project_id,
            "edit_source",
            target={
                "kind": kind,
                "target_id": target_id,
                "revision": base["revision"],
                "etag": base["etag"],
                "source": base["source"],
            },
            schema=schema,
        )
        self.client.ensure_model()
        messages.append({"role": "user", "content": instruction})
        for _ in range(self.client.settings.repair_attempts):
            completion = self.client.complete(
                messages, response_format={"type": "json_object"}
            )
            try:
                if len(completion.content.encode()) > MAX_SOURCE_BYTES:
                    raise ContractValidationError(
                        "Proposed source exceeds the edit limit"
                    )
                candidate = json.loads(completion.content)
                validation = self._validate(project_id, kind, base["source"], candidate)
                parsed = _parse(kind, candidate).to_dict()
                changes = _changes(base["source"], parsed)
                if not changes:
                    raise ContractValidationError(
                        "The proposal does not change the source"
                    )
            except (ValueError, TypeError, ProjectError) as exc:
                messages.extend(
                    [
                        completion.assistant_message,
                        {"role": "user", "content": str(exc)},
                    ]
                )
                continue
            proposal = {
                "schema_version": "1.0",
                "proposal_id": new_uuid7(),
                "apply_key": new_uuid7(),
                "undo_key": new_uuid7(),
                "project_id": project_id,
                "target_kind": kind,
                "target_id": target_id,
                "instruction": instruction.strip(),
                "created_at": datetime.now(UTC).isoformat(),
                "base_revision": base["revision"],
                "base_etag": base["etag"],
                "previous_source": base["source"],
                "candidate_source": parsed,
                "changes": changes,
                "permission_changes": _changes(
                    base["source"]["extensions"]["veyra"]["permissions"],
                    parsed["extensions"]["veyra"]["permissions"],
                ),
                "impact": {
                    "target_kind": kind,
                    "target_id": target_id,
                    "scope": "single_draft",
                    "immutable_versions_changed": False,
                    "runs_started": False,
                },
                "validation": validation,
                "state": "review",
            }
            self.store.create(proposal)
            return self.get(project_id, proposal["proposal_id"])
        raise FactoryError(
            "edit_generation_invalid",
            "The provider could not produce a valid source change; "
            "the Draft is unchanged",
        )

    def create_knowledge_binding(
        self,
        project_id: str,
        agent_id: str,
        instruction: str,
        expected_revision: int,
        expected_etag: str,
    ) -> dict[str, Any]:
        """Propose one Project Knowledge binding without asking the model to choose.

        The document is resolved from the Project inventory and the lock digest is
        computed by the server, so an ambiguous or absent mention fails visibly
        instead of becoming a guessed binding.
        """
        base = self.draft(project_id, "agent", agent_id)
        if base["revision"] != expected_revision or base["etag"] != expected_etag:
            raise DraftConflict(
                "Save or reload the current Draft before proposing edits"
            )
        if not instruction.strip():
            raise FactoryError("edit_instruction_empty", "Describe the change first")
        inventory = self.library.projects.project_summary(project_id)["knowledge"]
        match = resolve_knowledge(inventory, instruction)
        if match.status != "resolved" or match.selected is None:
            raise KnowledgeBindingUnresolved(match.status, match.candidates)
        document = match.selected
        candidate = bind_knowledge(base["source"], document)
        changes = _changes(base["source"], candidate)
        if not changes:
            raise FactoryError(
                "knowledge_already_bound",
                "This Knowledge version is already bound to the Agent",
            )
        validation = self._validate(project_id, "agent", base["source"], candidate)
        proposal = {
            "schema_version": "1.0",
            "proposal_id": new_uuid7(),
            "apply_key": new_uuid7(),
            "undo_key": new_uuid7(),
            "project_id": project_id,
            "target_kind": "agent",
            "target_id": agent_id,
            "instruction": instruction.strip(),
            "created_at": datetime.now(UTC).isoformat(),
            "base_revision": base["revision"],
            "base_etag": base["etag"],
            "previous_source": base["source"],
            "candidate_source": _parse("agent", candidate).to_dict(),
            "changes": changes,
            "permission_changes": [],
            "impact": {
                "target_kind": "agent",
                "target_id": agent_id,
                "scope": "single_draft",
                "immutable_versions_changed": False,
                "runs_started": False,
            },
            "knowledge_binding": knowledge_readiness(document),
            "validation": validation,
            "state": "review",
        }
        self.store.create(proposal)
        return self.get(project_id, proposal["proposal_id"])

    def create_resource_binding(
        self,
        project_id: str,
        agent_id: str,
        instruction: str,
        expected_revision: int,
        expected_etag: str,
    ) -> dict[str, Any]:
        """Propose one Project-owned filesystem.read Tool without model selection."""

        base = self.draft(project_id, "agent", agent_id)
        if base["revision"] != expected_revision or base["etag"] != expected_etag:
            raise DraftConflict(
                "Save or reload the current Draft before proposing edits"
            )
        if not instruction.strip():
            raise FactoryError("edit_instruction_empty", "Describe the change first")
        if not is_resource_binding_intent(instruction):
            raise ResourceBindingUnresolved("unresolved", ())
        project_view = self.project_resources.list(project_id)
        project_view["resources"] = [
            item
            for item in project_view["resources"]
            if item.get("resource_id") == FILESYSTEM_READ_RESOURCE_ID
        ]
        project_view = self.resource_readiness.response(project_view)
        catalog_view = self.catalog.resources(kind="tool")
        match = resolve_project_resource(
            project_view["resources"],
            catalog_view["resources"],
            instruction,
        )
        if match.status != "resolved" or match.selected is None:
            raise ResourceBindingUnresolved(match.status, match.candidates)
        resource = match.selected
        try:
            candidate = bind_project_tool(base["source"], resource)
        except ResourceMutationError as exc:
            raise FactoryError(exc.code, str(exc)) from exc
        parsed = _parse("agent", candidate).to_dict()
        changes = _changes(base["source"], parsed)
        validation = self._validate(project_id, "agent", base["source"], parsed)
        proposal = {
            "schema_version": "1.0",
            "proposal_id": new_uuid7(),
            "apply_key": new_uuid7(),
            "undo_key": new_uuid7(),
            "project_id": project_id,
            "target_kind": "agent",
            "target_id": agent_id,
            "instruction": instruction.strip(),
            "created_at": datetime.now(UTC).isoformat(),
            "base_revision": base["revision"],
            "base_etag": base["etag"],
            "previous_source": base["source"],
            "candidate_source": parsed,
            "changes": changes,
            "permission_changes": _changes(
                base["source"]["extensions"]["veyra"]["permissions"],
                parsed["extensions"]["veyra"]["permissions"],
            ),
            "impact": {
                "target_kind": "agent",
                "target_id": agent_id,
                "scope": "single_draft",
                "immutable_versions_changed": False,
                "runs_started": False,
            },
            "resource_binding": resource_readiness(resource),
            "validation": validation,
            "state": "review",
        }
        self.store.create(proposal)
        return self.get(project_id, proposal["proposal_id"])

    def create_validation_repair(
        self,
        project_id: str,
        agent_id: str,
        reference: str,
        code: str,
        expected_revision: int,
        expected_etag: str,
    ) -> dict[str, Any]:
        """Propose one deterministic validation repair without calling the model."""

        base = self.draft(project_id, "agent", agent_id)
        if base["revision"] != expected_revision or base["etag"] != expected_etag:
            raise DraftConflict(
                "Save or reload the current Draft before proposing edits"
            )
        parsed = AgentSource.from_dict(base["source"])
        inspected = inspect_agent_dependencies(
            self.library.projects,
            self.catalog,
            project_id,
            parsed,
            resource_projection=self.resource_readiness.project,
        )
        try:
            issue = select_issue(
                {"dependencies": inspected["dependencies"]}, reference, code
            )
            candidate = repair_agent_source(base["source"], issue)
            if issue["code"] in {"lock_mismatch", "lock_missing"}:
                extra_source = AgentSource.from_dict(candidate)
                extra_inspected = inspect_agent_dependencies(
                    self.library.projects,
                    self.catalog,
                    project_id,
                    extra_source,
                    resource_projection=self.resource_readiness.project,
                )
                for extra in project_issues(extra_inspected):
                    if extra["repairable"] and extra["code"] in {
                        "lock_mismatch",
                        "lock_missing",
                    }:
                        candidate = repair_agent_source(candidate, extra)
        except ValidationRepairError as exc:
            raise FactoryError(exc.code, str(exc)) from exc
        parsed_candidate = _parse("agent", candidate).to_dict()
        changes = _changes(base["source"], parsed_candidate)
        if not changes:
            raise FactoryError(
                "validation_repair_not_needed",
                "This validation issue does not change the Agent source",
            )
        validation = self._validate(
            project_id, "agent", base["source"], parsed_candidate
        )
        proposal = {
            "schema_version": "1.0",
            "proposal_id": new_uuid7(),
            "apply_key": new_uuid7(),
            "undo_key": new_uuid7(),
            "project_id": project_id,
            "target_kind": "agent",
            "target_id": agent_id,
            "instruction": f"Repair {issue['code']} for {issue['reference']}",
            "created_at": datetime.now(UTC).isoformat(),
            "base_revision": base["revision"],
            "base_etag": base["etag"],
            "previous_source": base["source"],
            "candidate_source": parsed_candidate,
            "changes": changes,
            "permission_changes": _changes(
                base["source"]["extensions"]["veyra"]["permissions"],
                parsed_candidate["extensions"]["veyra"]["permissions"],
            ),
            "impact": {
                "target_kind": "agent",
                "target_id": agent_id,
                "scope": "single_draft",
                "immutable_versions_changed": False,
                "runs_started": False,
            },
            "validation_repair": repair_plan(issue),
            "validation": validation,
            "state": "review",
        }
        self.store.create(proposal)
        return self.get(project_id, proposal["proposal_id"])

    def _validate(
        self,
        project_id: str,
        kind: TargetKind,
        previous: dict[str, Any],
        candidate: Any,
    ) -> dict[str, Any]:
        parsed = _parse(kind, candidate)
        normalized = parsed.to_dict()
        for field in (f"{kind}_id", "slug", "component_type"):
            if normalized[field] != previous[field]:
                raise ContractValidationError(
                    "An edit cannot replace the target identity"
                )
        result: dict[str, Any] = {
            "schema_version": "1.0",
            "valid": True,
            "source_hash": parsed.source_hash,
            "behavior_hash": parsed.behavior_hash,
            "lock_hash": parsed.lock_hash,
        }
        if isinstance(parsed, AgentSource):
            result.update(
                inspect_agent_dependencies(
                    self.library.projects, self.catalog, project_id, parsed
                )
            )
            for dependency in result["dependencies"]:
                if dependency["status"] in {
                    "missing",
                    "lock_missing",
                    "lock_mismatch",
                    "kind_mismatch",
                    "context_not_declared",
                    "context_too_large",
                }:
                    raise ContractValidationError(
                        f"Invalid dependency {dependency['reference']}: "
                        f"{dependency['status']}"
                    )
                if (
                    dependency["kind"] != "knowledge"
                    and dependency["reference"] not in previous["lock"]
                ):
                    resource = self.catalog.by_reference(dependency["reference"])
                    if not resource["factory_selectable"] or resource[
                        "availability"
                    ] in {
                        "quarantined",
                        "disabled",
                        "unavailable",
                    }:
                        raise ContractValidationError(
                            "New dependencies must be selectable Factory resources"
                        )
        else:
            calls = resolve_workflow_calls(self.library.repository, project_id, parsed)
            result["agent_calls"] = [
                {
                    "node_id": node,
                    "agent_id": call.agent_id,
                    "version_id": call.version_id,
                }
                for node, call in calls.items()
            ]
        return result

    def get(self, project_id: str, proposal_id: str) -> dict[str, Any]:
        proposal = self.store.get(project_id, proposal_id)
        if proposal is None:
            raise FactoryError("edit_proposal_not_found", "Edit proposal was not found")
        if proposal.get("proposal_kind") == AGENT_CREATION_PROPOSAL_KIND:
            proposal["stale"] = False
            proposal["applied_agent"] = proposal.get("applied_result")
            proposal["applied_revision"] = None
            return proposal
        if proposal.get("proposal_kind") == WORKFLOW_CREATION_PROPOSAL_KIND:
            proposal["stale"] = False
            proposal["applied_workflow"] = proposal.get("applied_result")
            proposal["applied_revision"] = None
            return proposal
        if proposal.get("proposal_kind") == COMPONENT_PROPOSAL_KIND:
            created = self.custom_components.find_builder_proposal(
                project_id, proposal_id
            )
            published = bool(
                created
                and created.get("version") != "0.0.0"
                and created.get("lifecycle") == "active"
            )
            if published:
                proposal["state"] = "applied"
            proposal["created_component"] = (
                {
                    "component_id": created["component_id"],
                    "display_name": created["display_name"],
                    "version": created["version"],
                    "reference": created["reference"],
                    "content_hash": created["content_hash"],
                    "readiness": created["readiness"],
                    "implementation_kind": created["implementation"]["kind"],
                }
                if published and created is not None
                else None
            )
            proposal["stale"] = (
                False
                if published or proposal["state"] == "rejected"
                else self._component_proposal_stale(project_id, proposal)
            )
            proposal["applied_revision"] = None
            return proposal
        try:
            current = self.draft(
                project_id, proposal["target_kind"], proposal["target_id"]
            )
        except DraftConflict:
            current = None
        applied = self.store.receipt(proposal)
        undone = self.store.receipt(proposal, undo=True)
        if undone:
            proposal["state"] = "undone"
        elif applied:
            proposal["state"] = "applied"
        expected = (
            undone
            or applied
            or {"revision": proposal["base_revision"], "etag": proposal["base_etag"]}
        )
        proposal["stale"] = current is None or any(
            current[key] != expected[key] for key in ("revision", "etag")
        )
        proposal["applied_revision"] = applied["revision"] if applied else None
        proposal.pop("undo_key")
        proposal.pop("apply_key", None)
        proposal.pop("previous_source")
        return proposal

    def list(
        self, project_id: str, kind: ProposalTargetKind, target_id: str
    ) -> dict[str, Any]:
        if kind != "custom_component":
            with suppress(DraftConflict):
                self.draft(project_id, kind, target_id)
        return {
            "schema_version": "1.0",
            "proposals": [
                self.get(project_id, item["proposal_id"])
                for item in self.store.list(project_id, kind, target_id)
            ],
        }

    def command(
        self, project_id: str, proposal_id: str, command: EditCommand, *, confirm: bool
    ) -> dict[str, Any]:
        if not confirm:
            raise FactoryError(
                "edit_confirmation_required", "Explicit confirmation is required"
            )
        with self.library.projects._writer_lock:
            view = self.get(project_id, proposal_id)
            proposal = self.store.get(project_id, proposal_id)
            assert proposal is not None
            if proposal.get("proposal_kind") == AGENT_CREATION_PROPOSAL_KIND:
                if command == "reject":
                    if view["state"] != "rejected":
                        self.store.reject(proposal_id)
                    return self.get(project_id, proposal_id)
                if command == "apply":
                    return self.apply_agent_creation_proposal(
                        project_id, proposal_id, confirm=True
                    )
                raise FactoryError(
                    "agent_creation_undo_unsupported",
                    "An Agent creation Proposal cannot be undone before creation.",
                )
            if proposal.get("proposal_kind") == WORKFLOW_CREATION_PROPOSAL_KIND:
                if command == "reject":
                    if view["state"] != "rejected":
                        self.store.reject(proposal_id)
                    return self.get(project_id, proposal_id)
                if command == "apply":
                    return self.apply_workflow_creation_proposal(
                        project_id, proposal_id, confirm=True
                    )
                raise FactoryError(
                    "workflow_creation_undo_unsupported",
                    "A Workflow creation Proposal cannot be undone before creation.",
                )
            if proposal.get("proposal_kind") == COMPONENT_PROPOSAL_KIND:
                if command == "undo":
                    raise FactoryError(
                        "component_proposal_undo_unsupported",
                        "Published Custom Component versions are immutable; "
                        "create a new version instead.",
                    )
                if view["state"] == "rejected" and command == "reject":
                    return view
                if view["state"] == "applied" and command == "apply":
                    return view
                if view["state"] != "review":
                    raise FactoryError(
                        "edit_proposal_closed",
                        "This proposal cannot accept that command",
                    )
                if command == "reject":
                    self.store.reject(proposal_id)
                else:
                    if view["stale"]:
                        raise DraftConflict(
                            "Project capabilities or Runtime readiness changed; "
                            "review a new proposal"
                        )
                    self._apply_component_proposal(project_id, proposal)
                return self.get(project_id, proposal_id)
            desired = {"apply": "applied", "reject": "rejected", "undo": "undone"}[
                command
            ]
            if view["state"] == desired:
                return view
            allowed = "applied" if command == "undo" else "review"
            if view["state"] != allowed:
                raise FactoryError(
                    "edit_proposal_closed", "This proposal cannot accept that command"
                )
            if command == "reject":
                self.store.reject(proposal_id)
            else:
                if view["stale"]:
                    raise DraftConflict(
                        "The Draft changed since this proposal; generate a new proposal"
                    )
                kind = proposal["target_kind"]
                undo = command == "undo"
                candidate = proposal["previous_source" if undo else "candidate_source"]
                if not undo:
                    try:
                        validation = self._validate(
                            project_id, kind, proposal["previous_source"], candidate
                        )
                    except (ContractValidationError, ProjectError) as exc:
                        raise DraftConflict(
                            "Dependencies changed since review; generate a new proposal"
                        ) from exc
                    if validation != proposal["validation"]:
                        raise DraftConflict(
                            "Dependencies changed since review; generate a new proposal"
                        )
                base = (
                    self.store.receipt(proposal)
                    if undo
                    else {
                        "revision": proposal["base_revision"],
                        "etag": proposal["base_etag"],
                    }
                )
                writer = (
                    self.library.replace_workflow_draft
                    if kind == "workflow"
                    else self.library.replace_draft
                )
                writer(
                    project_id=project_id,
                    **{f"{kind}_id": proposal["target_id"]},
                    source=candidate,
                    expected_revision=base["revision"],
                    expected_etag=base["etag"],
                    idempotency_key=proposal["undo_key"]
                    if undo
                    else proposal.get("apply_key", proposal_id),
                )
            return self.get(project_id, proposal_id)


def _parse(kind: TargetKind, source: Any) -> AgentSource | WorkflowSource:
    return (
        WorkflowSource.from_dict(source)
        if kind == "workflow"
        else AgentSource.from_dict(source)
    )


def _source_schema(kind: TargetKind) -> dict[str, Any]:
    for parent in Path(__file__).resolve().parents:
        path = parent / "contracts" / "schemas" / f"{kind}-source.schema.json"
        if path.is_file():
            schema: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return schema
    raise FactoryError("factory_schema_unavailable", "The source schema is unavailable")


def _changes(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        changes = []
        for key in sorted(before.keys() | after.keys()):
            pointer = path + "/" + key.replace("~", "~0").replace("/", "~1")
            if key in before and key in after:
                changes.extend(_changes(before[key], after[key], pointer))
            else:
                changes.append(
                    {
                        "path": pointer,
                        "operation": "add" if key in after else "remove",
                        "before": deepcopy(before.get(key)),
                        "after": deepcopy(after.get(key)),
                    }
                )
        return changes
    return [
        {
            "path": path,
            "operation": "replace",
            "before": deepcopy(before),
            "after": deepcopy(after),
        }
    ]
