"""Project-scoped Factory conversations and bounded Blueprint generation."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from veyra_agent_platform.contracts.agent import AgentBlueprint, ComponentType
from veyra_agent_platform.contracts.common import ContractValidationError, new_uuid7
from veyra_agent_platform.contracts.semantic_plan import AgentSemanticPlanV1
from veyra_agent_platform.local.builder.harness import BuilderHarness, BuilderMode
from veyra_agent_platform.local.builder.operation_events import (
    CAPABILITIES_RESOLVED,
    CAPABILITIES_STARTED,
    COMPILE_COMPLETED,
    COMPILE_STARTED,
    SEMANTIC_PLAN_COMPLETED,
    SEMANTIC_PLAN_STARTED,
    VALIDATION_COMPLETED,
    VALIDATION_STARTED,
)
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
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService
from veyra_agent_platform.local.resources import ResourceCatalog, ResourceCatalogError
from veyra_agent_platform.local.resources.project import ProjectResourceService

from .capability_probe import probe_provider_capabilities
from .capability_profile import (
    ProviderCapabilityProfile,
    allows_json_object_generate_fallback,
    derive_provider_capability_profile,
    generate_structured_output,
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
    bounded_repair_semantic_plan,
    classify_plan_error,
    graph_obligations,
    reject_silent_v1_degradation,
    semantic_plan_shape,
    validation_error_path,
)
from .store import FactorySessionRepository

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
    ) -> None:
        self.store = store
        self.projects = projects
        self.catalog = catalog
        self.client = client
        self.project_resources = project_resources or ProjectResourceService(
            projects, catalog
        )
        self.profiles = profiles or ProviderCapabilityStore(store.database_path)
        self.harness = BuilderHarness(projects, catalog)
        self._writer_lock = threading.RLock()

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
        payload["run_availability"] = self._run_availability(payload)
        payload["executes_drafts"] = False
        return payload

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
            if not self.client.configured:
                raise FactoryProviderError(
                    "factory_provider_not_configured",
                    "Factory model provider is not configured",
                )
            try:
                self.client.ensure_model()
            except FactoryProviderError:
                self._recover_generation(session_id)
                raise
            messages: list[dict[str, Any]] = [
                *self.harness.messages(project_id, "create_agent"),
                *[
                    {"role": row["role"], "content": row["content"]}
                    for row in self.store.messages(session_id)
                ],
                {
                    "role": "user",
                    "content": _planning_user_content(
                        self._project_capability_catalog(project_id)
                    ),
                },
            ]
            profile = self._capability_profile()
            if generate_structured_output(profile) is None:
                raise FactoryProviderError(
                    "factory_structured_output_unsupported",
                    "Factory model does not support structured output",
                    details={"error_class": "structured_output_unsupported"},
                )
            response_format: dict[str, Any] = _plan_response_format(profile)
            plan_schema = _plan_schema()
            history_count = len(self.store.messages(session_id))
            used_object_fallback = False
            diagnostics: list[str] = []
            observed_kinds: set[str] = set()
            attempts = self.client.settings.repair_attempts
            attempt = 1
            stage(SEMANTIC_PLAN_STARTED)
            while attempt <= attempts:
                self._set_state(session_id, "generating", diagnostics=diagnostics)
                mode = structured_mode_of(response_format)
                kind: InvocationKind = (
                    "semantic_plan" if attempt == 1 else "semantic_plan_repair"
                )
                fallback_from = (
                    "strict_json_schema"
                    if used_object_fallback and mode == "json_object"
                    else None
                )
                fallback_to = "json_object" if fallback_from else None
                try:
                    completion = self._complete_with_receipt(
                        messages,
                        response_format=response_format,
                        receipts=receipts,
                        kind=kind,
                        harness_mode="create_agent",
                        output_contract="AgentSemanticPlanV1",
                        schema=plan_schema,
                        history_message_count=history_count,
                        fallback_from=fallback_from,
                        fallback_to=fallback_to,
                        profile=profile,
                    )
                except FactoryProviderError as exc:
                    if (
                        not used_object_fallback
                        and allows_json_object_generate_fallback(
                            profile,
                            code=exc.code,
                            message=str(exc),
                            details=exc.details,
                        )
                    ):
                        used_object_fallback = True
                        response_format = {"type": "json_object"}
                        diagnostics.append(
                            f"attempt {attempt}: semantic plan schema rejected; "
                            "retrying as json_object"
                        )
                        continue
                    self._recover_generation(session_id)
                    raise
                parsed: dict[str, Any] | None = None
                repair_notes: tuple[str, ...] = ()
                try:
                    loaded = json.loads(completion.content)
                    if not isinstance(loaded, dict):
                        raise ContractValidationError("semantic plan must be an object")
                    parsed = loaded
                    observed_kinds |= graph_obligations(parsed)
                    repaired, repair_notes = bounded_repair_semantic_plan(parsed)
                    plan = AgentSemanticPlanV1.from_dict(repaired)
                    reject_silent_v1_degradation(
                        obligations=frozenset(observed_kinds),
                        operation_kinds=tuple(
                            step.operation_kind for step in plan.step_intents
                        ),
                        approval_points=plan.approval_points,
                        reusable_capability=any(
                            step.reusable_capability for step in plan.step_intents
                        ),
                        branch_intent=any(
                            step.branches or step.branch_condition
                            for step in plan.step_intents
                        ),
                    )
                    self._set_state(
                        session_id,
                        "generating",
                        semantic_plan=plan.to_dict(),
                        diagnostics=diagnostics,
                    )
                except (
                    json.JSONDecodeError,
                    TypeError,
                    ValueError,
                    ContractValidationError,
                ) as exc:
                    diagnostics.append(
                        _generation_failure(
                            attempt,
                            exc,
                            payload=parsed,
                            repair_notes=repair_notes,
                        )
                    )
                    messages.append(completion.assistant_message)
                    messages.append(
                        {
                            "role": "user",
                            "content": _repair_prompt(diagnostics, schema=plan_schema),
                        }
                    )
                    attempt += 1
                    continue
                display, slug = agent_candidate_identity(plan.suggested_name)
                self._set_state(
                    session_id,
                    "generating",
                    identity={"name": display, "slug": slug},
                    diagnostics=diagnostics,
                )
                stage(
                    SEMANTIC_PLAN_COMPLETED,
                    {
                        "suggested_name": display,
                        "suggested_slug": slug,
                        "input_count": str(len(plan.inputs)),
                        "output_count": str(len(plan.outputs)),
                    },
                )
                stage(CAPABILITIES_STARTED)
                compiled = compile_semantic_plan(
                    plan, self._project_context(project_id)
                )
                if compiled.status == "compile_error":
                    diagnostic = "semantic_compile_failed: " + (
                        compiled.error or "canonical graph could not be represented"
                    )
                    diagnostics.append(f"attempt {attempt}: {diagnostic}")
                    messages.append(completion.assistant_message)
                    messages.append(
                        {
                            "role": "user",
                            "content": _repair_prompt(diagnostics, schema=plan_schema),
                        }
                    )
                    attempt += 1
                    continue
                if compiled.status == "clarification":
                    self._set_state(
                        session_id,
                        "ready",
                        ready=True,
                        next_prompt=compiled.question or _READY_PROMPT,
                        diagnostics=[],
                        missing_capabilities=[],
                        identity={"name": display, "slug": slug},
                    )
                    return self.get_session(project_id, session_id)
                stage(
                    CAPABILITIES_RESOLVED,
                    {
                        "tool_count": str(len(compiled.tools)),
                        "knowledge_count": str(len(compiled.documents)),
                        "missing_count": str(len(compiled.missing)),
                        "extra_permission_count": str(
                            len(compiled.blueprint.requested_permissions.tools)
                            if compiled.blueprint is not None
                            else 0
                        ),
                    },
                )
                if compiled.status == "missing_capability":
                    self._set_state(
                        session_id,
                        "missing_capability",
                        diagnostics=[],
                        missing_capabilities=list(compiled.missing),
                        resource_plan=[],
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
                    diagnostics.extend(
                        f"attempt {attempt}: {item}" for item in exc.diagnostics
                    )
                    messages.append(completion.assistant_message)
                    messages.append(
                        {
                            "role": "user",
                            "content": _repair_prompt(diagnostics, schema=plan_schema),
                        }
                    )
                    attempt += 1
                    continue
                stage(VALIDATION_COMPLETED)
                self._set_state(
                    session_id,
                    "review",
                    ready=True,
                    next_prompt=(
                        "Review the compiled Blueprint and Resource Plan. Apply "
                        "it only when you explicitly confirm. Factory will not run it."
                    ),
                    blueprint=blueprint.to_dict(),
                    diagnostics=[],
                    missing_capabilities=[],
                    resource_plan=resource_plan(
                        blueprint,
                        self.catalog,
                        project_resources=self._project_resource_list(project_id),
                    ),
                    identity={"name": display, "slug": slug},
                )
                return self.get_session(project_id, session_id)
            self._set_state(
                session_id,
                "ready",
                ready=True,
                diagnostics=diagnostics,
                next_prompt=_READY_PROMPT,
            )
            raise FactoryError(
                "factory_generation_invalid",
                "Factory could not produce a valid Semantic Plan after three attempts",
            )

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
            identity = _session_identity(session)
            applied_name = (name or "").strip() or identity.get("name")
            applied_slug = identity.get("slug")
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
                agent = self.projects.create_agent_from_source(
                    project_id=project_id,
                    source=source,
                    parent_agent_id=parent_agent_id,
                )
            except ProjectError as exc:
                raise FactoryError("factory_apply_failed", str(exc)) from exc
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
            completion = self.client.complete(messages, response_format=response_format)
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

    def _recover_generation(self, session_id: str) -> None:
        self._set_state(
            session_id,
            "ready",
            ready=True,
            next_prompt=_READY_PROMPT,
            diagnostics=[],
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


def _repair_prompt(
    diagnostics: list[str], *, schema: Mapping[str, Any] | None = None
) -> str:
    excerpt = ""
    if isinstance(schema, Mapping):
        properties = schema.get("properties")
        if isinstance(properties, dict) and "step_intents" in properties:
            excerpt = json.dumps(
                {"step_intents": properties["step_intents"]},
                ensure_ascii=True,
                sort_keys=True,
            )[:1_200]
    return (
        "Repair only the invalid AgentSemanticPlanV1 fields. Keep the original "
        "user requirement. operation_kind must be exactly model, capability, "
        "transform, condition, approval, or verification. Human confirmation is "
        "approval. A later check is verification. A branch is condition. "
        "capability_requirement is only for capability steps and copies a "
        "Project-bound tool name or resource_id. For every condition, emit exactly "
        "two branches with semantic key and label. Every branch-local step must "
        "carry branch_condition and branch_key and depend only on its own branch. "
        "For deterministic transforms, output_mapping may map declared output "
        "field names to literals or {{input_field}} references. Do not emit node IDs, "
        "resource hashes, Knowledge UUIDs, canvas positions, source.lock, or "
        "permissions. Do not omit approval, condition, verification, transform, "
        "capability, or multiple model step_intents once they were required. Do "
        "not copy policy sentences into capability_intents. "
        + (f"step_intents schema: {excerpt}. " if excerpt else "")
        + "Diagnostics: "
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
        "semantic branches. Mark every branch-local duty with branch_condition "
        "and branch_key; never linearize sibling branches through depends_on. "
        "Use output_mapping on deterministic transforms when multiple declared "
        "output fields must be assembled. Do not emit node IDs, hashes, or "
        "versions. A simple one-duty Agent may use a single model step. Distinct "
        "duties must remain distinct step_intents."
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
