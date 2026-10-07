"""Project-scoped Factory conversations and bounded Blueprint generation."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping
from contextlib import suppress
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from veyra_agent_platform.contracts.agent import (
    AgentBlueprint,
    AgentSource,
    ComponentType,
)
from veyra_agent_platform.contracts.agent_spec import AgentSpecification
from veyra_agent_platform.contracts.common import (
    ContractValidationError,
    new_uuid7,
    thaw_json,
)
from veyra_agent_platform.contracts.execution_plan import ExecutionPlan
from veyra_agent_platform.contracts.resource_factory import ResourceFactoryPlan
from veyra_agent_platform.contracts.resource_plan import ResourcePlan
from veyra_agent_platform.contracts.semantic_plan import AgentSemanticPlanV1
from veyra_agent_platform.local.builder.agent_composer import compose_loop_agent
from veyra_agent_platform.local.builder.agent_loop_compiler import (
    loop_agent_blueprint_payload,
)
from veyra_agent_platform.local.builder.agent_state import (
    check_agent_state,
    register_agent_state,
)
from veyra_agent_platform.local.builder.capability_from_plan import (
    derive_plan_capabilities,
)
from veyra_agent_platform.local.builder.capability_requirements import (
    derive_capability_requirements,
)
from veyra_agent_platform.local.builder.composite_apply import (
    CompositeApplyError,
    apply_composite,
)
from veyra_agent_platform.local.builder.generate_product import (
    generate_builder_product,
    proposal_preview,
)
from veyra_agent_platform.local.builder.harness import BuilderHarness, BuilderMode
from veyra_agent_platform.local.builder.operation_events import (
    CAPABILITIES_RESOLVED,
    CAPABILITIES_STARTED,
    COMPILE_COMPLETED,
    COMPILE_STARTED,
    SPECIFICATION_COMPLETED,
    SPECIFICATION_STARTED,
    VALIDATION_COMPLETED,
    VALIDATION_STARTED,
)
from veyra_agent_platform.local.builder.prompt import RUNNABLE_AGENT_PRIMITIVES
from veyra_agent_platform.local.builder.quality import validate_agent_quality
from veyra_agent_platform.local.builder.receipts import (
    HarnessReceiptRecorder,
    InvocationKind,
    structured_mode_of,
)
from veyra_agent_platform.local.builder.resource_binding import (
    project_capability_catalog,
)
from veyra_agent_platform.local.builder.semantic_compiler import (
    BuilderProjectContext,
    builder_project_context,
    compile_semantic_plan,
    finalize_compiled_source,
)
from veyra_agent_platform.local.builder.simulation import simulate_agent
from veyra_agent_platform.local.builder.specification import (
    infer_agent_specification,
    resolve_agent_specification,
)
from veyra_agent_platform.local.builder.target_kind import BuilderTargetClassification
from veyra_agent_platform.local.builder.workflow_orchestration import (
    compile_workflow_orchestration,
)
from veyra_agent_platform.local.library.resource_truth import (
    annotate_resource_plan,
    pin_catalog_locks,
)
from veyra_agent_platform.local.models.registry import ModelRegistry
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService
from veyra_agent_platform.local.resources import (
    ResourceCatalog,
    ResourceCatalogError,
    ResourceFactory,
    ResourceFactoryError,
    ResourceWorkshop,
)
from veyra_agent_platform.local.resources.project import (
    ProjectResourceError,
    ProjectResourceService,
)
from veyra_agent_platform.local.resources.resolver import (
    ResourceResolver,
    plan_factory_items,
)
from veyra_agent_platform.local.secrets import resolve_secret

from .capability_probe import probe_provider_capabilities
from .capability_profile import (
    ProviderCapabilityProfile,
    derive_provider_capability_profile,
    structured_response_format,
)
from .capability_store import ProviderCapabilityStore
from .client import (
    FactoryProviderError,
    FactoryProviderNotConfigured,
    KimiClient,
    KimiCompletion,
)
from .compiler import (
    BlueprintCompileError,
    agent_candidate_identity,
    compile_blueprint,
    is_pinned_project_component,
    resource_plan,
    run_availability,
)
from .semantic_plan_repair import (
    classify_plan_error,
    semantic_plan_shape,
    validation_error_path,
)
from .store import FactorySessionRepository, _specification_record
from .task_structure_planner import FactoryTaskStructurePlanner


class _StageEmitter(Protocol):
    def __call__(self, kind: str, facts: dict[str, str] | None = None) -> None: ...


_STATES = {
    "collecting",
    "ready",
    "generating",
    "review",
    "missing_capability",
    "completed",
    "abandoned",
}
_BLOCKED_AVAILABILITY = {"unavailable", "disabled", "quarantined"}
_INITIAL_PROMPT = (
    "Tell me what this Agent should accomplish, what it receives, and what a "
    "successful result looks like."
)
_READY_PROMPT = (
    "The requirement is ready for a Blueprint. Review the resource plan, then "
    "generate a Draft when you are ready."
)
_CANNED_FOLLOW_UP = (
    "What inputs should it receive, what does success look like, and which "
    "catalog Components, Tools, or Skills should it use?"
)


class FactoryError(Exception):
    """A safe, typed Factory failure translated by the HTTP boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class FactoryService:
    def __init__(
        self,
        store: FactorySessionRepository,
        projects: ProjectService,
        catalog: ResourceCatalog,
        client: KimiClient,
        profiles: ProviderCapabilityStore | None = None,
        *,
        project_resources: ProjectResourceService | None = None,
        workshop: ResourceWorkshop | None = None,
        library: Any | None = None,
        entity_store: Any | None = None,
        model_registry: ModelRegistry | None = None,
        runtime_bindings: Callable[[str], Mapping[str, Mapping[str, str]]]
        | None = None,
    ) -> None:
        self.store = store
        self.projects = projects
        self.catalog = catalog
        self.client = client
        self.workshop = workshop
        self.library = library
        self.entity_store = entity_store
        self.model_registry = model_registry
        self.runtime_bindings = runtime_bindings
        self.project_resources = project_resources or ProjectResourceService(
            projects, catalog
        )
        self.profiles = profiles or ProviderCapabilityStore(store.database_path)
        self.harness = BuilderHarness(projects, catalog)
        self._writer_lock = threading.RLock()
        self.resource_factory = (
            ResourceFactory(workshop, catalog) if workshop is not None else None
        )

    def status(self) -> dict[str, Any]:
        settings = self.client.settings
        profile = self._capability_profile()
        return {
            "schema_version": "1.0",
            "configured": self.client.configured,
            "model_id": settings.model_id,
            "model_base_url": settings.model_base_url,
            "model_api_key_env": settings.model_api_key_env,
            "reasoning_effort": settings.reasoning_effort,
            "repair_attempts": settings.repair_attempts,
            "executes_drafts": False,
            "capability_profile": profile.to_dict(),
        }

    def probe_capabilities(self) -> dict[str, Any]:
        if not self.client.configured:
            raise FactoryProviderNotConfigured()
        previous = self._capability_profile()
        profile = probe_provider_capabilities(
            self.client.complete, previous, now=_now()
        )
        self.profiles.put(profile)
        return self.status()

    def _capability_profile(self) -> ProviderCapabilityProfile:
        seed = derive_provider_capability_profile(self.client.settings)
        cached = self.profiles.get(seed.identity_key)
        return cached if cached is not None else seed

    def resolved_capability_profile(self) -> ProviderCapabilityProfile:
        return self._capability_profile()

    def create_session(
        self,
        project_id: str,
        goal: str | None = None,
        *,
        receipts: HarnessReceiptRecorder | None = None,
    ) -> dict[str, Any]:
        self._require_project(project_id)
        session_id = new_uuid7()
        now = _now()
        clean_goal = _clean_text(goal)
        ready = bool(clean_goal)
        with self.store.transaction() as connection:
            self.store.create_session(
                connection,
                session_id=session_id,
                project_id=project_id,
                state="ready" if ready else "collecting",
                ready=ready,
                next_prompt=_READY_PROMPT if ready else _INITIAL_PROMPT,
                resource_plan=[],
                created_at=now,
            )
            if clean_goal:
                self.store.append_message(
                    connection,
                    message_id=new_uuid7(),
                    session_id=session_id,
                    sequence=0,
                    role="user",
                    content=clean_goal,
                    created_at=now,
                )
        if clean_goal:
            self._append_interview(session_id, receipts=receipts)
        return self.get_session(project_id, session_id)

    def get_session(self, project_id: str, session_id: str) -> dict[str, Any]:
        self._require_project(project_id)
        row = self.store.session(session_id, project_id)
        if row is None:
            raise FactoryError(
                "factory_session_not_found", "Factory session was not found"
            )
        if row["state"] not in _STATES:
            raise FactoryError(
                "factory_session_invalid", "Factory session has an invalid state"
            )
        payload = self.store.payload(row, self.store.messages(session_id))
        record = _generation_record(row)
        if record.get("target_kind"):
            payload["target_kind"] = record["target_kind"]
        if record.get("execution_kind"):
            payload["execution_kind"] = record["execution_kind"]
        plans = record.get("resource_factory_plans")
        if isinstance(plans, list):
            payload["resource_factory_plans"] = plans
        payload["run_availability"] = self._run_availability(payload)
        payload["executes_drafts"] = False
        if record.get("product_shape"):
            payload["product_shape"] = record["product_shape"]
        if isinstance(record.get("task_structure"), dict):
            payload["task_structure"] = record["task_structure"]
        if isinstance(record.get("execution_plan"), dict):
            payload["execution_plan"] = record["execution_plan"]
        if isinstance(record.get("proposal_preview"), dict):
            payload["proposal_preview"] = record["proposal_preview"]
        if record.get("blocked_reason"):
            payload["blocked_reason"] = record["blocked_reason"]
        if _model_setup_required(record.get("proposal_preview")):
            payload["run_availability"] = "requires_configuration"
        return payload

    def compile_review_source(self, project_id: str, session_id: str) -> dict[str, Any]:
        """Compile the reviewed candidate without creating a Project Agent.

        Builder Proposal materialization stores this result as a review snapshot.
        It must not read a mutable Factory session again during review.
        """
        session = self._row(project_id, session_id)
        if session["state"] != "review" or not session["blueprint_json"]:
            raise FactoryError(
                "factory_blueprint_missing",
                "A reviewable Factory Blueprint is required before materialization",
            )
        record = _generation_record(session)
        identity = _session_identity(session)
        display, slug = agent_candidate_identity(str(identity.get("name") or "Agent"))
        if record.get("target_kind") == "workflow":
            return {
                "target_kind": "workflow",
                "workflow": record.get("workflow") or {},
                "companions": record.get("companions") or [],
                "flow": record.get("flow") or [],
                "blueprint": json.loads(session["blueprint_json"]),
                "resource_plan": json.loads(session["resource_plan_json"]),
                "identity": {"name": display, "slug": slug},
                "specification": record.get("specification"),
                "execution_plan": record.get("execution_plan"),
                "entity_schema": record.get("entity_schema"),
                "proposal_preview": record.get("proposal_preview"),
                "product_shape": record.get("product_shape"),
            }
        compiled = record.get("compiled_source")
        if isinstance(compiled, dict):
            source = AgentSource.from_dict(compiled)
            blueprint_payload = json.loads(session["blueprint_json"])
            run_availability = self._run_availability(
                {
                    "blueprint": blueprint_payload,
                    "resource_plan": json.loads(session["resource_plan_json"]),
                }
            )
            if _model_setup_required(record.get("proposal_preview")):
                run_availability = "requires_configuration"
            return {
                "target_kind": "agent",
                "source": source.to_dict(),
                "blueprint": blueprint_payload,
                "resource_plan": json.loads(session["resource_plan_json"]),
                "required_project_resources": (
                    record.get("required_project_resources")
                    if isinstance(record.get("required_project_resources"), list)
                    else []
                ),
                "run_availability": run_availability,
                "identity": {"name": source.name, "slug": source.slug},
                "semantic_plan": json.loads(session["semantic_plan_json"])
                if session["semantic_plan_json"]
                else None,
                "specification": record.get("specification"),
                "execution_plan": record.get("execution_plan"),
                "proposal_preview": record.get("proposal_preview"),
            }
        try:
            blueprint = AgentBlueprint.from_dict(json.loads(session["blueprint_json"]))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise FactoryError(
                "factory_blueprint_invalid",
                "The stored Blueprint is no longer valid",
            ) from exc
        if self._missing_capabilities(blueprint, project_id):
            raise FactoryError(
                "factory_missing_capability",
                "The Blueprint references resources that are not available",
            )
        try:
            source, plan, availability = compile_blueprint(
                blueprint,
                self.catalog,
                project_resources=self._project_resource_list(project_id),
                name=display,
                slug=slug,
            )
            source = finalize_compiled_source(source, self._project_context(project_id))
        except BlueprintCompileError as exc:
            raise FactoryError(
                "factory_generation_invalid", "; ".join(exc.diagnostics)
            ) from exc
        return {
            "target_kind": "agent",
            "source": source.to_dict(),
            "blueprint": blueprint.to_dict(),
            "resource_plan": plan,
            "run_availability": availability,
            "identity": {"name": display, "slug": slug},
            "semantic_plan": json.loads(session["semantic_plan_json"])
            if session["semantic_plan_json"]
            else None,
            "specification": record.get("specification"),
        }

    def mark_agent_applied(
        self, project_id: str, session_id: str, agent_id: str
    ) -> dict[str, Any]:
        """Close a Factory session after a canonical Proposal Apply."""
        session = self._row(project_id, session_id)
        if session["state"] == "completed":
            return self.get_session(project_id, session_id)
        self._set_state(
            session_id,
            "completed",
            ready=True,
            next_prompt=(
                "Agent Draft created from the confirmed Proposal. Open Studio "
                "to review it, then test-run it with the local Runtime."
            ),
            identity={**_session_identity(session), "agent_id": agent_id},
        )
        return self.get_session(project_id, session_id)

    def mark_workflow_applied(
        self, project_id: str, session_id: str, workflow_id: str
    ) -> dict[str, Any]:
        session = self._row(project_id, session_id)
        if session["state"] == "completed":
            return self.get_session(project_id, session_id)
        self._set_state(
            session_id,
            "completed",
            ready=True,
            next_prompt=(
                "Workflow Draft created from the confirmed Proposal. Open Studio "
                "to review the graph, then run a committed version."
            ),
            identity={**_session_identity(session), "workflow_id": workflow_id},
        )
        return self.get_session(project_id, session_id)

    def add_message(
        self, project_id: str, session_id: str, content: str
    ) -> dict[str, Any]:
        with self._writer_lock:
            session = self._row(project_id, session_id)
            if session["state"] in {"completed", "abandoned"}:
                raise FactoryError(
                    "factory_session_closed", "Factory session is already closed"
                )
            clean_content = _clean_text(content)
            if not clean_content:
                raise FactoryError(
                    "factory_message_empty", "Factory message must not be empty"
                )
            previous = self.store.messages(session_id)
            now = _now()
            with self.store.transaction() as connection:
                self.store.append_message(
                    connection,
                    message_id=new_uuid7(),
                    session_id=session_id,
                    sequence=len(previous),
                    role="user",
                    content=clean_content,
                    created_at=now,
                )
                self.store.update_session(
                    connection,
                    session_id,
                    state="ready",
                    ready=True,
                    next_prompt=_READY_PROMPT,
                    updated_at=now,
                )
            self._append_interview(session_id)
            return self.get_session(project_id, session_id)

    def generate(
        self,
        project_id: str,
        session_id: str,
        *,
        on_stage: Callable[[str, dict[str, str]], None] | None = None,
        receipts: HarnessReceiptRecorder | None = None,
    ) -> dict[str, Any]:
        def stage(kind: str, facts: dict[str, str] | None = None) -> None:
            if on_stage is not None:
                on_stage(kind, facts or {})

        with self._writer_lock:
            session = self._row(project_id, session_id)
            if not bool(session["ready"]):
                raise FactoryError(
                    "factory_not_ready",
                    "Add enough requirement detail before generating a Blueprint",
                )
            if receipts is not None and not self.client.configured:
                raise FactoryProviderNotConfigured()
            requirement = self._session_requirement(session_id)
            return self._generate_v2_product(
                project_id, session_id, requirement, stage, receipts=receipts
            )

    def _generate_v2_product(
        self,
        project_id: str,
        session_id: str,
        requirement: str,
        stage: _StageEmitter,
        *,
        receipts: HarnessReceiptRecorder | None = None,
    ) -> dict[str, Any]:
        stage(SPECIFICATION_STARTED)
        planner = (
            FactoryTaskStructurePlanner(
                harness=self.harness,
                project_id=project_id,
                complete=self._complete_with_receipt,
                profile=self._capability_profile(),
                receipts=receipts,
                ensure_model=self.client.ensure_model,
                max_repairs=self.client.settings.repair_attempts,
            )
            if self.client.configured
            else None
        )
        planning_source = "provider" if planner is not None else "offline_heuristic"
        knowledge = list(
            self.projects.project_summary(project_id).get("knowledge") or []
        )
        product = generate_builder_product(
            requirement,
            self.catalog,
            project_resources=self._project_resource_list(project_id),
            knowledge_inventory=knowledge,
            secret_configured=self._secret_configured,
            planner_provider=planner,
            planner_repair=planner.repair if planner is not None else None,
            planner_review=planner.review_product if planner is not None else None,
            model_profiles=(
                self.model_registry.list_profiles()
                if self.model_registry is not None
                else ()
            ),
            model_bindings=(
                self.runtime_bindings(project_id)
                if self.runtime_bindings is not None
                else {}
            ),
            model_defaults=(
                self.model_registry.list_defaults()
                if self.model_registry is not None
                else ()
            ),
        )
        preview = proposal_preview(product)
        preview["planning_source"] = planning_source
        if planner is None:
            preview["semantic_validated"] = False
        if product.status != "review" or product.plan is None:
            stage(
                SPECIFICATION_COMPLETED,
                {"target_kind": "blocked", "blocked_reason": product.blocked_reason},
            )
            self._set_state(
                session_id,
                "ready",
                ready=True,
                next_prompt=f"BLOCKED — {product.blocked_reason}",
                diagnostics=list(product.diagnostics),
                missing_capabilities=[],
                resource_plan=[],
                specification={
                    "status": "blocked",
                    "missing": [product.blocked_reason],
                    "blocked_reason": product.blocked_reason,
                    "task_structure": (
                        product.structure.to_dict() if product.structure else None
                    ),
                    "execution_plan": (
                        product.plan.to_dict() if product.plan else None
                    ),
                    "proposal_preview": preview,
                },
            )
            return self.get_session(project_id, session_id)
        plan = product.plan
        shape = plan.product_shape
        display = (
            product.specification.suggested_name
            if product.specification is not None
            else "Agent"
        )
        from veyra_agent_platform.local.factory.compiler import agent_candidate_identity

        display, slug = agent_candidate_identity(display)
        stage(
            SPECIFICATION_COMPLETED,
            {
                "suggested_name": display,
                "suggested_slug": slug,
                "target_kind": "workflow" if shape != "PURE_AGENT" else "agent",
                "product_shape": shape,
            },
        )
        resolved = product.resolved
        assert resolved is not None
        record = _generation_record(self._row(project_id, session_id))
        factory_plans = self._build_factory_plans(
            session_id, resolved, record, requirement=requirement
        )
        stage(CAPABILITIES_STARTED)
        if product.orchestration is not None:
            return self._store_composite_review(
                project_id,
                session_id,
                requirement,
                product,
                display,
                slug,
                factory_plans,
                preview,
                stage,
                planning_source=planning_source,
            )
        assert product.source is not None
        assert product.specification is not None
        source = product.source
        blueprint_payload = loop_agent_blueprint_payload(source)
        blueprint = AgentBlueprint.from_dict(blueprint_payload)
        resolver_items = plan_factory_items(resolved)
        component_plan = annotate_resource_plan(
            resource_plan(
                blueprint,
                self.catalog,
                project_resources=self._project_resource_list(project_id),
            ),
            catalog=self.catalog,
            project_resources=self._project_resource_list(project_id),
        )
        plan_items = _merge_resolver_plan(resolver_items, component_plan)
        plan_items = _annotate_factory_missing(plan_items, factory_plans)
        stage(
            CAPABILITIES_RESOLVED,
            {
                "tool_count": str(
                    len(
                        [
                            item
                            for item in (source.ui.get("bindings") or {}).values()
                            if isinstance(item, dict) and item.get("kind") == "tool"
                        ]
                    )
                ),
                "missing_count": str(len(resolved.missing_required)),
            },
        )
        stage(COMPILE_STARTED)
        stage(COMPILE_COMPLETED)
        stage(VALIDATION_STARTED)
        AgentSource.from_dict(source.to_dict())
        stage(VALIDATION_COMPLETED)
        self._set_state(
            session_id,
            "review",
            ready=True,
            next_prompt=(
                "Review the Agent capabilities, then apply only when you confirm."
                if planner is not None
                else "Offline compiler preview; semantic planning has not been "
                "performed. Review the draft before applying."
            ),
            blueprint=blueprint_payload,
            diagnostics=list(resolved.diagnostics),
            missing_capabilities=[],
            resource_plan=plan_items,
            identity={
                "name": source.name,
                "slug": source.slug,
                "target_kind": "agent",
                "execution_kind": source.execution_kind,
            },
            specification={
                "status": "complete",
                "missing": [],
                "specification": product.specification.to_dict(),
                "compiled_source": thaw_json(source.to_dict()),
                "target_kind": "agent",
                "execution_kind": source.execution_kind,
                "product_shape": shape,
                "task_structure": product.structure.to_dict()
                if product.structure
                else None,
                "execution_plan": plan.to_dict(),
                "proposal_preview": preview,
                "resource_plan_snapshot": resolved.to_dict(),
                "resource_factory_plans": [item.to_dict() for item in factory_plans],
                "factory_wrappers": record.get("factory_wrappers") or {},
                "blocked_reason": product.blocked_reason,
            },
        )
        return self.get_session(project_id, session_id)

    def _store_composite_review(
        self,
        project_id: str,
        session_id: str,
        requirement: str,
        product: Any,
        display: str,
        slug: str,
        factory_plans: list[Any],
        preview: dict[str, Any],
        stage: _StageEmitter,
        *,
        planning_source: str,
    ) -> dict[str, Any]:
        orchestration = product.orchestration
        resolved = product.resolved
        stage(
            CAPABILITIES_RESOLVED,
            {
                "companion_count": str(len(orchestration.companions)),
                "missing_count": str(len(resolved.missing_required)),
            },
        )
        stage(COMPILE_STARTED)
        preview_blueprint = orchestration.workflow_preview()
        preview_blueprint["proposal"] = preview
        preview_blueprint["product_shape"] = product.plan.product_shape
        stage(COMPILE_COMPLETED)
        stage(VALIDATION_STARTED)
        if product.plan.product_shape != "WORKFLOW" and not orchestration.companions:
            raise FactoryError(
                "factory_generation_invalid",
                "Workflow compilation produced no companion Agents",
            )
        stage(VALIDATION_COMPLETED)
        resolver_items = plan_factory_items(resolved)
        plan_items = _annotate_factory_missing(resolver_items, factory_plans)
        self._set_state(
            session_id,
            "review",
            ready=True,
            next_prompt=(
                "Review the composite plan, then apply only when you confirm."
                if planning_source == "provider"
                else "Offline compiler preview; semantic planning has not been "
                "performed. Review the draft before applying."
            ),
            blueprint=preview_blueprint,
            diagnostics=list(resolved.diagnostics),
            missing_capabilities=[],
            resource_plan=plan_items,
            identity={
                "name": display,
                "slug": slug,
                "target_kind": "workflow",
                "execution_kind": "workflow",
            },
            specification={
                "status": "complete",
                "missing": [],
                "specification": (
                    product.specification.to_dict()
                    if product.specification is not None
                    else {"goal": requirement[:400]}
                ),
                "target_kind": "workflow",
                "execution_kind": "workflow",
                "product_shape": product.plan.product_shape,
                "task_structure": (
                    product.structure.to_dict() if product.structure else None
                ),
                "execution_plan": product.plan.to_dict(),
                "proposal_preview": preview,
                "workflow": orchestration.workflow,
                "companions": [
                    thaw_json(item.to_dict()) for item in orchestration.companions
                ],
                "flow": list(orchestration.flow),
                "resource_plan_snapshot": resolved.to_dict(),
                "resource_factory_plans": [item.to_dict() for item in factory_plans],
                "entity_schema": (
                    product.plan.state.to_dict()
                    if product.plan is not None and product.plan.state is not None
                    else None
                ),
                "blocked_reason": product.blocked_reason,
            },
        )
        return self.get_session(project_id, session_id)

    def _session_requirement(self, session_id: str) -> str:
        parts = [
            str(row["content"] or "").strip()
            for row in self.store.messages(session_id)
            if row["role"] == "user"
        ]
        return "\n".join(item for item in parts if item)

    def _generate_loop_agent_product(
        self,
        project_id: str,
        session_id: str,
        requirement: str,
        classified: BuilderTargetClassification,
        stage: _StageEmitter,
    ) -> dict[str, Any]:
        stage(SPECIFICATION_STARTED)
        completeness = resolve_agent_specification(requirement)
        spec = completeness.specification or infer_agent_specification(requirement)
        missing = [
            item
            for item in completeness.missing
            if item not in {"approval_requirement"}
        ]
        if missing and "unsupported_capability" in missing:
            self._set_state(
                session_id,
                "ready",
                ready=True,
                next_prompt=(
                    "This request needs a capability Veyra cannot express yet. "
                    "Describe a text, image, document, or tool-using Agent."
                ),
                diagnostics=list(missing),
            )
            return self.get_session(project_id, session_id)
        display, slug = agent_candidate_identity(spec.suggested_name or "Agent")
        stage(
            SPECIFICATION_COMPLETED,
            {
                "suggested_name": display,
                "suggested_slug": slug,
                "target_kind": "agent",
            },
        )
        stage(CAPABILITIES_STARTED)
        project_resources = self._project_resource_list(project_id)
        knowledge = list(
            self.projects.project_summary(project_id).get("knowledge") or []
        )
        requirements = derive_capability_requirements(spec, requirement)
        resolved = ResourceResolver(
            self.catalog,
            secret_configured=self._secret_configured,
        ).resolve(
            spec,
            requirements,
            project_resources=project_resources,
            knowledge_inventory=knowledge,
            requirement_text=requirement,
        )
        source = compose_loop_agent(spec, resolved, requirement=requirement)
        blueprint_payload = loop_agent_blueprint_payload(source)
        blueprint = AgentBlueprint.from_dict(blueprint_payload)
        resolver_items = plan_factory_items(resolved)
        component_plan = annotate_resource_plan(
            resource_plan(
                blueprint,
                self.catalog,
                project_resources=project_resources,
            ),
            catalog=self.catalog,
            project_resources=project_resources,
        )
        plan = _merge_resolver_plan(resolver_items, component_plan)
        record = _generation_record(self._row(project_id, session_id))
        factory_plans = self._build_factory_plans(
            session_id, resolved, record, requirement=requirement
        )
        plan = _annotate_factory_missing(plan, factory_plans)
        tool_count = str(
            len(
                [
                    item
                    for item in (source.ui.get("bindings") or {}).values()
                    if isinstance(item, dict) and item.get("kind") == "tool"
                ]
            )
        )
        missing_count = str(len(resolved.missing_required))
        stage(
            CAPABILITIES_RESOLVED,
            {
                "tool_count": tool_count,
                "knowledge_count": str(len(source.knowledge_refs)),
                "missing_count": missing_count,
                "extra_permission_count": str(len(source.permissions.tools)),
            },
        )
        stage(COMPILE_STARTED)
        stage(COMPILE_COMPLETED)
        stage(VALIDATION_STARTED)
        AgentSource.from_dict(source.to_dict())
        stage(VALIDATION_COMPLETED)
        self._set_state(
            session_id,
            "review",
            ready=True,
            next_prompt=(
                classified.message_en
                + " Review the Agent capabilities, then apply only when you confirm."
            ),
            blueprint=blueprint_payload,
            diagnostics=list(resolved.diagnostics),
            missing_capabilities=[],
            resource_plan=plan,
            identity={
                "name": source.name,
                "slug": source.slug,
                "target_kind": "agent",
                "execution_kind": source.execution_kind,
            },
            specification={
                "status": "complete",
                "missing": [],
                "specification": spec.to_dict(),
                "compiled_source": thaw_json(source.to_dict()),
                "target_kind": "agent",
                "execution_kind": source.execution_kind,
                "recommendation": classified.recommendation,
                "classification_reason": classified.reason,
                "resource_plan_snapshot": resolved.to_dict(),
                "resource_factory_plans": [item.to_dict() for item in factory_plans],
                "factory_wrappers": record.get("factory_wrappers") or {},
                "required_project_resources": [
                    {
                        "reference": item["reference"],
                        "kind": item.get("kind"),
                        "bind_status": item.get("bind_status"),
                        "name": item.get("name"),
                        "capability": item.get("capability"),
                        "reason": item.get("reason"),
                    }
                    for item in plan
                    if item.get("bind_status")
                ],
            },
        )
        return self.get_session(project_id, session_id)

    def _generate_workflow_product(
        self,
        project_id: str,
        session_id: str,
        requirement: str,
        classified: BuilderTargetClassification,
        stage: _StageEmitter,
    ) -> dict[str, Any]:
        stage(SPECIFICATION_STARTED)
        orchestration = compile_workflow_orchestration(requirement, self.catalog)
        display, slug = agent_candidate_identity(
            orchestration.workflow.get("name") or "Workflow"
        )
        stage(
            SPECIFICATION_COMPLETED,
            {
                "suggested_name": display,
                "suggested_slug": slug,
                "target_kind": "workflow",
            },
        )
        stage(CAPABILITIES_STARTED)
        stage(
            CAPABILITIES_RESOLVED,
            {
                "tool_count": "0",
                "knowledge_count": "0",
                "missing_count": "0",
                "companion_count": str(len(orchestration.companions)),
            },
        )
        stage(COMPILE_STARTED)
        preview = orchestration.workflow_preview()
        stage(COMPILE_COMPLETED)
        stage(VALIDATION_STARTED)
        if not orchestration.companions:
            raise FactoryError(
                "factory_generation_invalid",
                "Workflow compilation produced no companion Agents",
            )
        stage(VALIDATION_COMPLETED)
        self._set_state(
            session_id,
            "review",
            ready=True,
            next_prompt=(
                classified.message_en
                + " Review the Workflow stages, then apply only when you confirm."
            ),
            blueprint=preview,
            diagnostics=[],
            missing_capabilities=[],
            resource_plan=[],
            identity={
                "name": display,
                "slug": slug,
                "target_kind": "workflow",
                "execution_kind": "workflow",
            },
            specification={
                "status": "complete",
                "missing": [],
                "specification": {
                    "goal": requirement[:400],
                    "suggested_name": display,
                    "flow": list(orchestration.flow),
                },
                "target_kind": "workflow",
                "execution_kind": "workflow",
                "workflow": orchestration.workflow,
                "companions": [
                    thaw_json(item.to_dict()) for item in orchestration.companions
                ],
                "flow": list(orchestration.flow),
                "recommendation": classified.recommendation,
                "classification_reason": classified.reason,
            },
        )
        return self.get_session(project_id, session_id)

    def resume_after_component(
        self,
        project_id: str,
        session_id: str,
        *,
        on_stage: Callable[[str, dict[str, str]], None] | None = None,
    ) -> dict[str, Any]:
        """Recompile the stored plan after a separately confirmed Component write."""

        session = self._row(project_id, session_id)
        raw_plan = session["semantic_plan_json"]
        if not raw_plan:
            raise FactoryError(
                "factory_continuation_unavailable",
                "The original semantic plan is unavailable; no Agent was created.",
            )
        try:
            plan = AgentSemanticPlanV1.from_dict(json.loads(raw_plan))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise FactoryError(
                "factory_continuation_invalid",
                "The stored semantic plan could not be safely recompiled.",
            ) from exc

        identity = json.loads(session["identity_json"] or "{}")
        display, slug = agent_candidate_identity(
            str(identity.get("name") or plan.suggested_name)
        )

        def stage(kind: str, facts: dict[str, str] | None = None) -> None:
            if on_stage is not None:
                on_stage(kind, facts or {})

        stage(CAPABILITIES_STARTED)
        compiled = compile_semantic_plan(plan, self._project_context(project_id))
        if compiled.status == "compile_error":
            raise FactoryError(
                "factory_continuation_invalid",
                "The stored semantic plan could not be compiled without losing "
                "graph semantics: "
                + (compiled.error or "unknown semantic compile error"),
            )
        if compiled.status == "clarification":
            self._set_state(
                session_id,
                "ready",
                ready=True,
                next_prompt=compiled.question or _READY_PROMPT,
                blueprint=None,
                diagnostics=[],
                missing_capabilities=[],
                resource_plan=[],
                semantic_plan=plan.to_dict(),
                identity={"name": display, "slug": slug},
            )
            return self.get_session(project_id, session_id)

        stage(
            "builder.capabilities.resolved",
            {
                "tool_count": str(len(compiled.tools)),
                "knowledge_count": str(len(compiled.documents)),
                "missing_count": str(len(compiled.missing)),
            },
        )
        if compiled.status == "missing_capability":
            self._set_state(
                session_id,
                "missing_capability",
                diagnostics=[],
                missing_capabilities=list(compiled.missing),
                resource_plan=[],
                semantic_plan=plan.to_dict(),
                identity={"name": display, "slug": slug},
            )
            return self.get_session(project_id, session_id)

        blueprint = compiled.blueprint
        assert blueprint is not None
        missing = self._missing_capabilities(blueprint, project_id)
        if missing:
            self._set_state(
                session_id,
                "missing_capability",
                blueprint=blueprint.to_dict(),
                diagnostics=[],
                missing_capabilities=missing,
                resource_plan=resource_plan(
                    blueprint,
                    self.catalog,
                    project_resources=self._project_resource_list(project_id),
                ),
                semantic_plan=plan.to_dict(),
                identity={"name": display, "slug": slug},
            )
            return self.get_session(project_id, session_id)

        stage(COMPILE_STARTED)
        stage(COMPILE_COMPLETED)
        stage(VALIDATION_STARTED)
        try:
            compile_blueprint(
                blueprint,
                self.catalog,
                project_resources=self._project_resource_list(project_id),
                name=display,
                slug=slug,
            )
        except BlueprintCompileError as exc:
            raise FactoryError(
                "factory_continuation_invalid",
                "The Agent candidate failed validation after Component creation: "
                + "; ".join(exc.diagnostics),
            ) from exc
        quality = validate_agent_quality(blueprint)
        simulation = simulate_agent(blueprint)
        if quality.verdict != "PASS" or not simulation.passed:
            raise FactoryError(
                "factory_continuation_invalid",
                "The Agent candidate failed typed dataflow validation: "
                + "; ".join((*quality.diagnostics, *simulation.diagnostics)),
            )
        stage(VALIDATION_COMPLETED)
        self._set_state(
            session_id,
            "review",
            ready=True,
            next_prompt=(
                "The confirmed Component is pinned. Review the Agent Blueprint and "
                "Resource Plan, then explicitly confirm Agent Draft creation."
            ),
            blueprint=blueprint.to_dict(),
            diagnostics=[],
            missing_capabilities=[],
            resource_plan=resource_plan(
                blueprint,
                self.catalog,
                project_resources=self._project_resource_list(project_id),
            ),
            semantic_plan=plan.to_dict(),
            identity={"name": display, "slug": slug},
        )
        return self.get_session(project_id, session_id)

    def apply_draft(
        self,
        project_id: str,
        session_id: str,
        *,
        confirm: bool,
        name: str | None = None,
        description: str | None = None,
        parent_agent_id: str | None = None,
    ) -> dict[str, Any]:
        if not confirm:
            raise FactoryError(
                "factory_confirmation_required",
                "Explicit confirmation is required to create the Agent Draft",
            )
        with self._writer_lock:
            session = self._row(project_id, session_id)
            if (
                not session["blueprint_json"]
                or session["state"] == "missing_capability"
            ):
                raise FactoryError(
                    "factory_blueprint_missing",
                    "A valid Blueprint must be reviewed before applying a Draft",
                )
            identity = _session_identity(session)
            record = _generation_record(session)
            if record.get("blocked_reason"):
                raise FactoryError(
                    "factory_generation_blocked",
                    str(record["blocked_reason"]),
                )
            if record.get("target_kind") == "workflow":
                if record.get("blocked_reason"):
                    raise FactoryError(
                        "factory_generation_blocked",
                        str(record["blocked_reason"]),
                    )
                return self._apply_composite_draft(
                    project_id, session_id, record, name=name, description=description
                )
            compiled = record.get("compiled_source")
            applied_name = (name or "").strip() or identity.get("name")
            applied_slug = identity.get("slug")
            if isinstance(compiled, dict):
                source = AgentSource.from_dict(compiled)
                if applied_name:
                    payload = source.to_dict()
                    payload["name"] = applied_name
                    if description:
                        payload["description"] = description
                    source = AgentSource.from_dict(payload)
                snapshot = record.get("resource_plan_snapshot")
                if isinstance(snapshot, dict):
                    _assert_snapshot_locks(source, ResourcePlan.from_dict(snapshot))
            else:
                try:
                    blueprint = AgentBlueprint.from_dict(
                        json.loads(session["blueprint_json"])
                    )
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise FactoryError(
                        "factory_blueprint_invalid",
                        "The stored Blueprint is no longer valid",
                    ) from exc
                if self._missing_capabilities(blueprint, project_id):
                    raise FactoryError(
                        "factory_missing_capability",
                        "The Blueprint references resources that are not available",
                    )
                try:
                    source, _, _ = compile_blueprint(
                        blueprint,
                        self.catalog,
                        project_resources=self._project_resource_list(project_id),
                        name=applied_name,
                        slug=applied_slug,
                        description=description,
                    )
                    source = finalize_compiled_source(
                        source, self._project_context(project_id)
                    )
                except BlueprintCompileError as exc:
                    raise FactoryError(
                        "factory_generation_invalid",
                        "; ".join(exc.diagnostics),
                    ) from exc
            try:
                check_agent_state(project_id, source, self.entity_store)
            except ValueError as exc:
                raise FactoryError("factory_state_contract_invalid", str(exc)) from exc
            try:
                pin_catalog_locks(
                    self.project_resources, self.catalog, project_id, source
                )
            except ProjectResourceError as exc:
                raise FactoryError(exc.code, str(exc)) from exc
            try:
                agent = self.projects.create_agent_from_source(
                    project_id=project_id,
                    source=source,
                    parent_agent_id=parent_agent_id,
                )
            except ProjectError as exc:
                raise FactoryError("factory_apply_failed", str(exc)) from exc
            try:
                register_agent_state(project_id, source, self.entity_store)
            except Exception as exc:
                with suppress(ProjectError, OSError):
                    self.projects.remove_agent(project_id, str(agent["agent_id"]))
                raise FactoryError(
                    "factory_state_registration_failed", str(exc)
                ) from exc
            self._set_state(
                session_id,
                "completed",
                ready=True,
                next_prompt=(
                    "Agent Draft created. Open Studio to review it, then test-run "
                    "it with the local Runtime. Factory still does not execute drafts."
                ),
            )
            return {
                "schema_version": "1.0",
                "session": self.get_session(project_id, session_id),
                "agent": agent,
            }

    def _apply_composite_draft(
        self,
        project_id: str,
        session_id: str,
        record: dict[str, Any],
        *,
        name: str | None,
        description: str | None,
    ) -> dict[str, Any]:
        if self.library is None:
            raise FactoryError(
                "factory_library_unavailable",
                "Composite apply requires the Library commit service",
            )
        workflow = record.get("workflow")
        companions_raw = record.get("companions")
        if not isinstance(workflow, dict) or not isinstance(companions_raw, list):
            raise FactoryError(
                "factory_workflow_candidate_missing",
                "The composite proposal is missing Workflow or companion Agents",
            )
        if name:
            workflow = {**workflow, "name": name}
        if description:
            workflow = {**workflow, "description": description}
        companions = tuple(AgentSource.from_dict(item) for item in companions_raw)
        for companion in companions:
            try:
                pin_catalog_locks(
                    self.project_resources, self.catalog, project_id, companion
                )
            except ProjectResourceError as exc:
                raise FactoryError(exc.code, str(exc)) from exc
        plan = record.get("execution_plan")
        entity_schema = None
        if isinstance(plan, dict) and isinstance(plan.get("state"), dict):
            entity_schema = plan["state"]
        try:
            installed = apply_composite(
                projects=self.projects,
                library=self.library,
                project_id=project_id,
                companions=companions,
                workflow=workflow,
                flow=tuple(str(item) for item in (record.get("flow") or [])),
                entity_schema=entity_schema,
                entity_store=self.entity_store,
            )
        except CompositeApplyError as exc:
            raise FactoryError(exc.code, str(exc)) from exc
        self._set_state(
            session_id,
            "completed",
            ready=True,
            next_prompt=(
                "Composite Draft created. Companion Agents are committed and "
                "Workflow AgentCalls pin those immutable versions."
            ),
        )
        return {
            "schema_version": "1.0",
            "session": self.get_session(project_id, session_id),
            "workflow": installed,
            "agent": (installed.get("companion_agents") or [None])[0],
        }

    def revise_plan(self, project_id: str, session_id: str) -> dict[str, Any]:
        """Return a reviewable plan to ready so the user can change it."""

        with self._writer_lock:
            session = self._row(project_id, session_id)
            if session["state"] != "review":
                raise FactoryError(
                    "factory_revise_not_review",
                    "Only a reviewed proposal can be sent back for changes",
                )
            self._set_state(
                session_id,
                "ready",
                ready=True,
                next_prompt=(
                    "Describe what to change in the plan. Generation will not "
                    "silently keep the previous structure."
                ),
            )
            return self.get_session(project_id, session_id)

    def generate_factory_draft(
        self,
        project_id: str,
        session_id: str,
        *,
        confirm: bool,
        capability: str,
        wrapper: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not confirm:
            raise FactoryError(
                "factory_confirmation_required",
                "Explicit confirmation is required to create a Factory draft",
            )
        with self._writer_lock:
            session = self._row(project_id, session_id)
            record = _generation_record(session)
            factory = self._require_resource_factory()
            plans = [
                ResourceFactoryPlan.from_dict(item)
                for item in (record.get("resource_factory_plans") or [])
            ]
            planned = next(
                (item for item in plans if item.capability == capability), None
            )
            if planned is None:
                raise FactoryError(
                    "factory_capability_missing",
                    "This Factory session has no plan for that capability",
                )
            wrappers = dict(record.get("factory_wrappers") or {})
            if wrapper:
                wrappers[capability] = dict(wrapper)
            snapshot = record.get("resource_plan_snapshot") or {}
            resolved = ResourcePlan.from_dict(snapshot) if snapshot else None
            if resolved is None:
                raise FactoryError(
                    "factory_blueprint_missing",
                    "A ResourcePlan snapshot is required before Factory drafts",
                )
            requirement = next(
                (
                    item
                    for item in resolved.requirements
                    if item.capability == capability
                ),
                None,
            )
            if requirement is None:
                from veyra_agent_platform.contracts.capability import (
                    CapabilityRequirement,
                )

                requirement = CapabilityRequirement(
                    capability=capability, required=True
                )
            try:
                classified = factory.plan_missing(
                    resolved,
                    wrappers=wrappers,
                    existing=[item.to_dict() for item in plans],
                    proposal_id=session_id,
                )
                planned = next(
                    (item for item in classified if item.capability == capability),
                    None,
                )
                if planned is None:
                    raise FactoryError(
                        "factory_capability_missing",
                        "This Factory session has no plan for that capability",
                    )
                if planned.strategy == "skill_instruction":
                    planned = factory.ensure_skill_draft(planned, requirement)
                elif planned.strategy in {
                    "http_tool_wrapper",
                    "filesystem_tool_wrapper",
                }:
                    planned = factory.ensure_wrapper_draft(
                        planned, requirement, wrappers.get(capability) or {}
                    )
                else:
                    raise ResourceFactoryError(
                        "factory_unsupported"
                        if planned.status == "unsupported"
                        else "factory_requires_configuration"
                        if planned.status == "requires_user_configuration"
                        else "factory_requires_external_integration",
                        planned.reason,
                    )
            except ResourceFactoryError as exc:
                raise FactoryError(exc.code, str(exc)) from exc
            merged = [
                planned if item.capability == capability else item
                for item in classified
            ]
            specification = dict(record.get("specification") or {})
            specification_payload = {
                "status": record.get("status") or "complete",
                "missing": record.get("missing") or [],
                "specification": specification,
                "compiled_source": record.get("compiled_source"),
                "target_kind": record.get("target_kind"),
                "execution_kind": record.get("execution_kind"),
                "resource_plan_snapshot": snapshot,
                "resource_factory_plans": [item.to_dict() for item in merged],
                "factory_wrappers": wrappers,
                "required_project_resources": record.get("required_project_resources")
                or [],
            }
            self._set_state(
                session_id,
                str(session["state"]),
                specification=specification_payload,
                resource_plan=_annotate_factory_missing(
                    json.loads(session["resource_plan_json"]), merged
                ),
            )
            return self.get_session(project_id, session_id)

    def approve_factory_resource(
        self,
        project_id: str,
        session_id: str,
        *,
        confirm: bool,
        capability: str,
        content_hash: str | None = None,
        bind_to_project: bool = False,
    ) -> dict[str, Any]:
        with self._writer_lock:
            session = self._row(project_id, session_id)
            record = _generation_record(session)
            factory = self._require_resource_factory()
            plans = [
                ResourceFactoryPlan.from_dict(item)
                for item in (record.get("resource_factory_plans") or [])
            ]
            planned = next(
                (item for item in plans if item.capability == capability), None
            )
            if planned is None or planned.draft is None:
                raise FactoryError(
                    "factory_draft_missing",
                    "Review a Factory draft before publishing it",
                )
            try:
                published = factory.publish(
                    planned, confirm=confirm, snapshot_hash=content_hash
                )
            except ResourceFactoryError as exc:
                raise FactoryError(exc.code, str(exc)) from exc
            if bind_to_project and published.published:
                try:
                    self.project_resources.add(
                        project_id,
                        str(published.published["reference"]),
                        source="factory",
                        content_hash=str(published.published["content_hash"]),
                    )
                except ProjectResourceError as exc:
                    raise FactoryError(exc.code, str(exc)) from exc
            merged = [
                published if item.capability == capability else item for item in plans
            ]
            specification = record.get("specification")
            if not isinstance(specification, dict):
                raise FactoryError(
                    "factory_blueprint_missing",
                    "A specification snapshot is required to retry Resolver",
                )
            spec = AgentSpecification.from_dict(specification)
            requirement = self._session_requirement(session_id)
            project_resources = self._project_resource_list(project_id)
            knowledge = list(
                self.projects.project_summary(project_id).get("knowledge") or []
            )
            plan_payload = record.get("execution_plan")
            if isinstance(plan_payload, dict):
                requirements = derive_plan_capabilities(
                    ExecutionPlan.from_dict(plan_payload)
                )
            else:
                requirements = derive_capability_requirements(spec, requirement)
            resolved = ResourceResolver(
                self.catalog,
                secret_configured=self._secret_configured,
            ).resolve(
                spec,
                requirements,
                project_resources=project_resources,
                knowledge_inventory=knowledge,
                requirement_text=requirement,
            )
            source = compose_loop_agent(spec, resolved, requirement=requirement)
            blueprint_payload = loop_agent_blueprint_payload(source)
            resolver_items = plan_factory_items(resolved)
            component_plan = annotate_resource_plan(
                resource_plan(
                    AgentBlueprint.from_dict(blueprint_payload),
                    self.catalog,
                    project_resources=project_resources,
                ),
                catalog=self.catalog,
                project_resources=project_resources,
            )
            plan = _annotate_factory_missing(
                _merge_resolver_plan(resolver_items, component_plan), merged
            )
            self._set_state(
                session_id,
                "review",
                ready=True,
                blueprint=blueprint_payload,
                diagnostics=list(resolved.diagnostics),
                resource_plan=plan,
                identity={
                    "name": source.name,
                    "slug": source.slug,
                    "target_kind": "agent",
                    "execution_kind": source.execution_kind,
                },
                specification={
                    "status": "complete",
                    "missing": [],
                    "specification": spec.to_dict(),
                    "compiled_source": thaw_json(source.to_dict()),
                    "target_kind": "agent",
                    "execution_kind": source.execution_kind,
                    "resource_plan_snapshot": resolved.to_dict(),
                    "resource_factory_plans": [item.to_dict() for item in merged],
                    "factory_wrappers": record.get("factory_wrappers") or {},
                    "required_project_resources": [
                        {
                            "reference": item["reference"],
                            "kind": item.get("kind"),
                            "bind_status": item.get("bind_status"),
                            "name": item.get("name"),
                            "capability": item.get("capability"),
                            "reason": item.get("reason"),
                        }
                        for item in plan
                        if item.get("bind_status")
                    ],
                },
            )
            return self.get_session(project_id, session_id)

    def _build_factory_plans(
        self,
        session_id: str,
        resolved: ResourcePlan,
        record: Mapping[str, Any],
        *,
        requirement: str,
    ) -> list[ResourceFactoryPlan]:
        del requirement
        factory = self.resource_factory
        if factory is None:
            return []
        wrappers = dict(record.get("factory_wrappers") or {})
        existing = record.get("resource_factory_plans") or []
        plans = factory.plan_missing(
            resolved,
            wrappers=wrappers,
            existing=existing if isinstance(existing, list) else [],
            proposal_id=session_id,
        )
        built: list[ResourceFactoryPlan] = []
        for planned in plans:
            requirement_item = next(
                (
                    item
                    for item in resolved.requirements
                    if item.capability == planned.capability
                ),
                None,
            )
            if requirement_item is None:
                from veyra_agent_platform.contracts.capability import (
                    CapabilityRequirement,
                )

                requirement_item = CapabilityRequirement(
                    capability=planned.capability, required=True
                )
            if (
                planned.can_generate
                and planned.strategy == "skill_instruction"
                and planned.draft is None
            ):
                try:
                    planned = factory.ensure_skill_draft(planned, requirement_item)
                except ResourceFactoryError as exc:
                    raise FactoryError(exc.code, str(exc)) from exc
            if (
                planned.can_generate
                and planned.strategy in {"http_tool_wrapper", "filesystem_tool_wrapper"}
                and planned.draft is None
                and wrappers.get(planned.capability)
            ):
                try:
                    planned = factory.ensure_wrapper_draft(
                        planned,
                        requirement_item,
                        wrappers[planned.capability],
                    )
                except ResourceFactoryError as exc:
                    raise FactoryError(exc.code, str(exc)) from exc
            built.append(planned)
        return built

    def _require_resource_factory(self) -> ResourceFactory:
        if self.resource_factory is None:
            raise FactoryError("workshop_unavailable", "Resource Workshop is starting")
        return self.resource_factory

    def _append_interview(
        self,
        session_id: str,
        *,
        receipts: HarnessReceiptRecorder | None = None,
    ) -> None:
        previous = self.store.messages(session_id)
        reply = self._interview_reply(session_id, receipts=receipts)
        with self.store.transaction() as connection:
            self.store.append_message(
                connection,
                message_id=new_uuid7(),
                session_id=session_id,
                sequence=len(previous),
                role="assistant",
                content=reply,
                created_at=_now(),
            )

    def _interview_reply(
        self,
        session_id: str,
        *,
        receipts: HarnessReceiptRecorder | None = None,
    ) -> str:
        if not self.client.configured:
            return _CANNED_FOLLOW_UP
        session = self.store.session(session_id)
        assert session is not None
        messages = [
            *self.harness.messages(session["project_id"], "interview"),
            *[
                {"role": row["role"], "content": row["content"]}
                for row in self.store.messages(session_id)
            ],
        ]
        try:
            self.client.ensure_model()
            completion = self._complete_with_receipt(
                messages,
                response_format=None,
                receipts=receipts,
                kind="interview",
                harness_mode="interview",
                output_contract="none",
                schema=None,
                history_message_count=len(self.store.messages(session_id)),
            )
            return completion.content.strip() or _CANNED_FOLLOW_UP
        except FactoryProviderError:
            if receipts is not None:
                raise
            return _CANNED_FOLLOW_UP

    def _complete_with_receipt(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None,
        receipts: HarnessReceiptRecorder | None,
        kind: InvocationKind,
        harness_mode: BuilderMode,
        output_contract: str,
        schema: dict[str, Any] | None,
        history_message_count: int,
        fallback_from: str | None = None,
        fallback_to: str | None = None,
        profile: ProviderCapabilityProfile | None = None,
    ) -> KimiCompletion:
        receipt_id: str | None = None
        if receipts is not None:
            receipt_id = receipts.begin(
                kind=kind,
                harness_mode=harness_mode,
                structured_mode=structured_mode_of(response_format),
                output_contract=output_contract,
                schema=schema,
                messages=messages,
                history_message_count=history_message_count,
                fallback_from=fallback_from,
                fallback_to=fallback_to,
                profile=profile,
            )
        try:
            plan_call = kind in {"semantic_plan", "semantic_plan_repair"}
            completion = self.client.complete(
                messages,
                response_format=response_format,
                **({"read_timeout": None} if plan_call else {}),
            )
        except FactoryProviderError as exc:
            if receipt_id is not None and receipts is not None:
                receipts.fail(receipt_id, exc)
            raise
        if receipt_id is not None and receipts is not None:
            receipts.succeed(receipt_id, provider_request_id=completion.request_id)
        return completion

    def _missing_capabilities(
        self, blueprint: AgentBlueprint, project_id: str
    ) -> list[dict[str, Any]]:
        missing: list[dict[str, Any]] = []
        project_resources = self._project_resource_list(project_id)
        project_components = {
            str(resource.get("reference")): resource
            for resource in project_resources
            if resource.get("kind") == "component"
            and resource.get("component_class") == "composite"
            and resource.get("scope") == "project"
        }
        for node in blueprint.nodes:
            if node.component_type is not ComponentType.CUSTOM_COMPONENT:
                continue
            resource = project_components.get(node.uses or "")
            if resource is None:
                missing.append(
                    _missing_item(
                        "component",
                        node.uses or "CustomComponent",
                        "resource is not a current Project component",
                    )
                )
            elif not is_pinned_project_component(resource):
                missing.append(
                    _missing_item(
                        "component",
                        node.uses or "CustomComponent",
                        "resource is not a ready, current Project pin",
                    )
                )
        components = {
            resource["name"]: resource
            for resource in self.catalog.resources(kind="component")["resources"]
        }
        for component_type in blueprint.required_capabilities.component_types:
            if component_type is ComponentType.CUSTOM_COMPONENT:
                continue
            resource = components.get(component_type.value)
            if resource is None or not resource["factory_selectable"]:
                missing.append(
                    _missing_item("component", component_type.value, "not selectable")
                )
        expected_kinds = {
            "tool": {"tool", "mcp_tool"},
            "skill": {"skill"},
            "policy": {"policy"},
        }
        grouped = (
            ("tool", blueprint.required_capabilities.tool_refs),
            ("skill", blueprint.required_capabilities.skill_refs),
            ("policy", blueprint.required_capabilities.policy_refs),
        )
        for kind, references in grouped:
            for reference in references:
                item = self._missing_reference(
                    kind, reference, expected_kinds[kind], project_resources
                )
                if item is not None:
                    missing.append(item)
        return missing

    def _missing_reference(
        self,
        kind: str,
        reference: str,
        expected_kinds: set[str],
        project_resources: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        try:
            resource = self.catalog.by_reference(reference)
        except ResourceCatalogError:
            project_resource = next(
                (
                    item
                    for item in project_resources
                    if item.get("reference") == reference
                    and item.get("kind") == "component"
                    and item.get("component_class") == "composite"
                    and item.get("scope") == "project"
                ),
                None,
            )
            if project_resource is not None and kind == "tool":
                if is_pinned_project_component(project_resource):
                    return None
                return _missing_item(kind, reference, "resource is not selectable")
            return _missing_item(kind, reference, "resource is not registered")
        if resource["kind"] not in expected_kinds:
            return _missing_item(kind, reference, "resource kind does not match")
        if (
            not resource["factory_selectable"]
            or resource["availability"] in _BLOCKED_AVAILABILITY
        ):
            return _missing_item(kind, reference, "resource is not selectable")
        return None

    def _secret_configured(self, secret_ref: str) -> bool:
        store = getattr(self.client, "_secret_store", None)
        return bool(resolve_secret(store, secret_ref, ""))

    def _project_context(self, project_id: str) -> BuilderProjectContext:
        project_resources = self._project_resource_list(project_id)
        summary = self.projects.project_summary(project_id)
        return builder_project_context(
            project_id=project_id,
            knowledge=list(summary.get("knowledge") or []),
            project_resources=project_resources,
            catalog_resources=list(self.catalog.resources().get("resources") or []),
        )

    def _project_resource_list(self, project_id: str) -> list[dict[str, Any]]:
        listed = self.project_resources.list(project_id)
        return list(listed.get("resources") or [])

    def _project_capability_catalog(self, project_id: str) -> list[dict[str, str]]:
        return project_capability_catalog(self._project_resource_list(project_id))

    def _run_availability(self, payload: dict[str, Any]) -> str:
        if payload.get("target_kind") == "workflow":
            return "requires_configuration"
        plan = payload.get("resource_plan")
        if isinstance(plan, list) and plan:
            return run_availability(plan)
        blueprint = payload.get("blueprint")
        if not isinstance(blueprint, dict):
            return "unavailable"
        try:
            parsed = AgentBlueprint.from_dict(blueprint)
        except (TypeError, ValueError, ContractValidationError):
            return "unavailable"
        return run_availability(resource_plan(parsed, self.catalog))

    def _row(self, project_id: str, session_id: str) -> Any:
        self._require_project(project_id)
        row = self.store.session(session_id, project_id)
        if row is None:
            raise FactoryError(
                "factory_session_not_found", "Factory session was not found"
            )
        return row

    def _set_state(self, session_id: str, state: str, **values: Any) -> None:
        if state not in _STATES:
            raise FactoryError("factory_state_invalid", "Factory state is invalid")
        with self.store.transaction() as connection:
            self.store.update_session(
                connection, session_id, state=state, updated_at=_now(), **values
            )

    def _require_project(self, project_id: str) -> None:
        if self.projects.repository.project(project_id) is None:
            raise FactoryError(
                "factory_project_not_found", "Factory project was not found"
            )


def _session_identity(row: Any) -> dict[str, str]:
    try:
        raw = row["identity_json"]
    except (KeyError, IndexError):
        raw = "{}"
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in parsed.items()
        if isinstance(key, str) and value is not None and str(value).strip()
    }


def _generation_record(row: Any) -> dict[str, Any]:
    record = _specification_record(row)
    raw_extras = record.get("extras")
    extras: dict[str, Any] = raw_extras if isinstance(raw_extras, dict) else {}
    compiled = extras.get("compiled_source") or record.get("compiled_source")
    workflow = extras.get("workflow") or record.get("workflow")
    companions = extras.get("companions") or record.get("companions")
    flow = extras.get("flow") or record.get("flow")
    required = extras.get("required_project_resources") or record.get(
        "required_project_resources"
    )
    snapshot = extras.get("resource_plan_snapshot") or record.get(
        "resource_plan_snapshot"
    )
    factory_plans = extras.get("resource_factory_plans") or record.get(
        "resource_factory_plans"
    )
    wrappers = extras.get("factory_wrappers") or record.get("factory_wrappers")
    return {
        "specification": record.get("specification"),
        "status": record.get("status"),
        "missing": record.get("missing") or [],
        "compiled_source": compiled if isinstance(compiled, dict) else None,
        "target_kind": extras.get("target_kind") or record.get("target_kind"),
        "execution_kind": extras.get("execution_kind") or record.get("execution_kind"),
        "workflow": workflow if isinstance(workflow, dict) else None,
        "companions": companions if isinstance(companions, list) else None,
        "flow": flow if isinstance(flow, list) else None,
        "required_project_resources": required if isinstance(required, list) else [],
        "resource_plan_snapshot": snapshot if isinstance(snapshot, dict) else None,
        "resource_factory_plans": (
            factory_plans if isinstance(factory_plans, list) else []
        ),
        "factory_wrappers": wrappers if isinstance(wrappers, dict) else {},
        "product_shape": extras.get("product_shape") or record.get("product_shape"),
        "task_structure": extras.get("task_structure") or record.get("task_structure"),
        "execution_plan": extras.get("execution_plan") or record.get("execution_plan"),
        "proposal_preview": extras.get("proposal_preview")
        or record.get("proposal_preview"),
        "blocked_reason": extras.get("blocked_reason") or record.get("blocked_reason"),
        "entity_schema": extras.get("entity_schema") or record.get("entity_schema"),
    }


def _model_setup_required(proposal_preview: Any) -> bool:
    if not isinstance(proposal_preview, dict):
        return False
    models = proposal_preview.get("models")
    if not isinstance(models, list):
        return False
    for item in models:
        if not isinstance(item, dict):
            continue
        if item.get("required") and item.get("status") in {
            "needs_setup",
            "missing_capability",
            "unsupported",
        }:
            return True
        issue = item.get("issue")
        if (
            item.get("optional")
            and isinstance(issue, dict)
            and issue.get("code") == "optional_model_capability_unavailable"
        ):
            # The current candidate still uses the optional model capability.
            # Runtime needs a profile or a separately compiled fallback first.
            return True
    return False


def _stored_specification(row: Any) -> dict[str, Any] | None:
    specification = _generation_record(row).get("specification")
    return specification if isinstance(specification, dict) else None


def _merge_resolver_plan(
    resolver_items: list[dict[str, Any]],
    component_plan: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = list(resolver_items)
    seen = {str(item.get("reference")) for item in merged if item.get("reference")}
    for item in component_plan:
        reference = str(item.get("reference") or "")
        if not reference or reference in seen:
            continue
        merged.append(item)
        seen.add(reference)
    return merged


def _annotate_factory_missing(
    plan_items: list[dict[str, Any]],
    factory_plans: list[ResourceFactoryPlan],
) -> list[dict[str, Any]]:
    by_cap = {item.capability: item for item in factory_plans}
    annotated: list[dict[str, Any]] = []
    for raw in plan_items:
        item = dict(raw)
        capability = str(item.get("capability") or "")
        planned = by_cap.get(capability)
        if item.get("bind_status") == "missing" and planned is not None:
            item["factory_status"] = planned.status
            item["factory_strategy"] = planned.strategy
            item["reason"] = planned.reason
            if planned.draft and isinstance(planned.draft, dict):
                item["name"] = str(planned.draft.get("name") or item.get("name") or "")
        annotated.append(item)
    return annotated


def _assert_snapshot_locks(source: AgentSource, plan: ResourcePlan) -> None:
    for item in (*plan.already_bound, *plan.will_bind, *plan.needs_configuration):
        digest = source.lock.get(item.reference)
        if digest != item.content_hash:
            raise FactoryError(
                "resource_identity_conflict",
                "Proposal resource snapshot no longer matches the compiled Agent lock",
            )


def _missing_item(kind: str, reference: str, reason: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "reference": reference,
        "reason": reason,
        "proposal": {"action": "quarantined_resource_draft", "executable": False},
    }


def _clean_text(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip()


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _prepare_blueprint_payload(parsed: Any) -> Any:
    """Fill only safe, contract-default verification keys omitted by MFJS $ref."""

    if not isinstance(parsed, dict):
        return parsed
    payload = deepcopy(parsed)
    verification = payload.get("verification")
    if (
        isinstance(verification, dict)
        and "required" not in verification
        and "checks" not in verification
    ):
        payload["verification"] = {"required": False, "checks": []}
    return payload


def _generation_failure(
    attempt: int,
    exc: BaseException,
    *,
    payload: dict[str, Any] | None = None,
    repair_notes: tuple[str, ...] = (),
) -> str:
    detail = " ".join(str(exc).split())[:180]
    name = type(exc).__name__
    category = classify_plan_error(exc)
    path = validation_error_path(exc)
    parts = [
        f"attempt {attempt}: invalid AgentSemanticPlan ({name}: {detail})"
        if detail
        else f"attempt {attempt}: invalid AgentSemanticPlan ({name})"
    ]
    parts.append(f"category={category}")
    parts.append(f"path={path}")
    if payload is not None:
        shape = json.dumps(
            semantic_plan_shape(payload), ensure_ascii=True, sort_keys=True
        )
        parts.append(f"shape={shape}")
    if repair_notes:
        parts.append("repair=" + ",".join(repair_notes[:8]))
    return " ".join(parts)


def _semantic_field_specs(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        f"{item['name']}:{item['type']}"
        for item in value
        if isinstance(item, Mapping)
        and isinstance(item.get("name"), str)
        and isinstance(item.get("type"), str)
    ][:16]


def _repair_prompt(
    diagnostics: list[str],
    *,
    input_fields: list[str],
    output_fields: list[str],
) -> str:
    input_contract = ", ".join(input_fields) if input_fields else "none"
    output_contract = ", ".join(output_fields) if output_fields else "none"
    return (
        "Repair only the invalid AgentSemanticPlanV1 fields. Keep the original "
        "user requirement. operation_kind must be exactly model, capability, "
        "transform, condition, approval, or verification. Human confirmation is "
        "approval. A later check is verification. A branch is condition. "
        "capability_requirement is only for capability steps and copies a "
        "Project-bound tool name or resource_id. For every condition, emit exactly "
        "two branches with semantic key and label. Put the executable predicate in "
        "condition_expression using a supported comparison over a declared Agent "
        "input; keep human intent in purpose. Never replace natural-language "
        "classification with a non-empty/default check. Every "
        "branch-local step must "
        "carry branch_condition and branch_key and depend only on its own branch. "
        "Declared Agent inputs: "
        + input_contract
        + ". Declared Agent outputs: "
        + output_contract
        + ". Step-level inputs and outputs declare typed data ports for model, "
        "transform, capability, and approval steps. depends_on is execution "
        "order; the server compiles data_edges from those ports. Transform "
        "output_mapping may reference declared Agent inputs or this step's "
        "input ports with {{port}} tokens. Only the last Model on each path to "
        "Output produces the declared Agent outputs. Earlier Models emit their "
        "own node output contract. Human confirmation uses approval ports "
        "approved and rejected; do not invent a decision input to re-test "
        "the same confirmation with a Condition. Preserve a genuine "
        "deterministic Transform. Do not emit node IDs, "
        "resource hashes, Knowledge UUIDs, canvas positions, source.lock, or "
        "permissions. Do not omit a user-required approval, condition, verification, "
        "capability, genuine deterministic transform, or distinct model duty. Do "
        "not copy policy sentences into capability_intents. "
        + RUNNABLE_AGENT_PRIMITIVES
        + " Diagnostics: "
        + "; ".join(diagnostics)
    )


def _planning_user_content(catalog: list[dict[str, str]]) -> str:
    if catalog:
        available = json.dumps(catalog, ensure_ascii=False)
        library = (
            "Project-bound capabilities to reuse by exact name or resource_id: "
            + available
            + ". Do not invent a duplicate. "
        )
    else:
        library = (
            "This Project has no bound tools. Leave capability_intents empty "
            "unless the user named an external tool that must be reported as "
            "missing. "
        )
    return (
        "Generate the AgentSemanticPlanV1 JSON for this requirement. "
        "Use step_intents for every real duty. operation_kind must be one of "
        "model, capability, transform, condition, approval, verification. "
        "Human confirmation is approval. A check after a result is "
        "verification. A branch is condition. Put tool policy in "
        "user_constraints, not capability_intents. "
        + library
        + "capability_requirement copies a bound tool name or resource_id when "
        "operation_kind is capability. For every condition, emit exactly two "
        "semantic branches. Put the executable predicate in condition_expression "
        "using a supported explicit comparison over a declared Agent input; keep "
        "human intent in purpose. Do not invent a non-empty/default test to stand "
        "in for semantic classification. Mark every branch-local "
        "duty with branch_condition and branch_key; never linearize sibling "
        "branches through depends_on. "
        "Use step-level inputs and outputs to declare typed data ports. "
        "depends_on orders steps; the server compiles data edges. Set "
        "branch_key to approved or rejected on duties after HumanApproval. "
        "Only the last "
        "Model on each path to Output produces the Agent's declared top-level "
        "outputs. Earlier Models emit their own node output contract. A "
        "deterministic Transform can map literals, declared Agent inputs, or this "
        "step's input ports to declared outputs. Use output_mapping when a real "
        "transform is needed. Do not emit node IDs, hashes, or versions. A simple "
        "one-duty Agent may use a single model step. Distinct duties must remain "
        "distinct step_intents." + RUNNABLE_AGENT_PRIMITIVES
    )


def _plan_response_format(profile: ProviderCapabilityProfile) -> dict[str, Any]:
    return structured_response_format(
        profile,
        name="agent_semantic_plan",
        schema=_plan_schema(),
    )


def _blueprint_response_format(profile: ProviderCapabilityProfile) -> dict[str, Any]:
    """Compatibility bridge: project a full AgentBlueprint schema for MFJS probes."""

    return structured_response_format(
        profile,
        name="agent_blueprint",
        schema=_generation_schema(),
    )


def _generation_schema() -> dict[str, Any]:
    schema = deepcopy(_blueprint_schema())
    capabilities = schema["$defs"]["required_capabilities"]
    capabilities["required"] = [
        "component_types",
        "tool_refs",
        "skill_refs",
        "policy_refs",
    ]
    schema["$defs"]["typed_fields"] = {
        "type": "object",
        "minProperties": 1,
        "propertyNames": {"$ref": "#/$defs/slug"},
        "additionalProperties": {
            "type": "string",
            "enum": [
                "string",
                "number",
                "integer",
                "boolean",
                "object",
                "array",
            ],
        },
        "description": (
            "Non-empty map from slug keys to type names. Keys must match "
            "[a-z][a-z0-9-]{0,62} and use hyphens, not underscores. Values are "
            "type names such as string. Artifact modalities are not generated "
            "through this compatibility schema."
        ),
    }
    schema["$defs"]["verification"]["description"] = (
        "Always include required as a boolean and checks as an array of "
        "strings. If required is true, checks must contain at least one item."
    )
    return schema


def _plan_schema() -> dict[str, Any]:
    current = Path(__file__).resolve()
    for parent in current.parents:
        path = parent / "contracts" / "schemas" / "agent-semantic-plan.schema.json"
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise FactoryError(
                    "factory_schema_unavailable",
                    "The AgentSemanticPlan schema is unavailable",
                ) from exc
            if not isinstance(loaded, dict):
                raise FactoryError(
                    "factory_schema_unavailable",
                    "The AgentSemanticPlan schema is unavailable",
                )
            return loaded
    raise FactoryError(
        "factory_schema_unavailable", "The AgentSemanticPlan schema is unavailable"
    )


def _blueprint_schema() -> dict[str, Any]:
    current = Path(__file__).resolve()
    for parent in current.parents:
        path = parent / "contracts" / "schemas" / "agent-blueprint.schema.json"
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise FactoryError(
                    "factory_schema_unavailable",
                    "The AgentBlueprint schema is unavailable",
                ) from exc
            if not isinstance(loaded, dict):
                raise FactoryError(
                    "factory_schema_unavailable",
                    "The AgentBlueprint schema is unavailable",
                )
            return loaded
    raise FactoryError(
        "factory_schema_unavailable", "The AgentBlueprint schema is unavailable"
    )
