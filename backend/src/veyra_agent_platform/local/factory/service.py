"""Project-scoped Factory conversations and bounded Blueprint generation."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from veyra_agent_platform.contracts.agent import AgentBlueprint
from veyra_agent_platform.contracts.common import ContractValidationError, new_uuid7
from veyra_agent_platform.contracts.semantic_plan import AgentSemanticPlanV1
from veyra_agent_platform.local.builder.harness import BuilderHarness
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
from veyra_agent_platform.local.builder.semantic_compiler import (
    BuilderProjectContext,
    builder_project_context,
    compile_semantic_plan,
    finalize_compiled_source,
)
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService
from veyra_agent_platform.local.resources import ResourceCatalog, ResourceCatalogError
from veyra_agent_platform.local.resources.project import ProjectResourceService

from .capability_profile import ProviderCapabilityProfile, structured_response_format
from .client import FactoryProviderError, KimiClient
from .compiler import (
    BlueprintCompileError,
    agent_candidate_identity,
    compile_blueprint,
    resource_plan,
    run_availability,
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
    ) -> None:
        self.store = store
        self.projects = projects
        self.catalog = catalog
        self.client = client
        self.harness = BuilderHarness(projects, catalog)
        self._writer_lock = threading.RLock()

    def status(self) -> dict[str, Any]:
        settings = self.client.settings
        profile = self.client.capability_profile()
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

    def create_session(
        self, project_id: str, goal: str | None = None
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
            self._append_interview(session_id)
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
                    "content": (
                        "Generate the AgentSemanticPlanV1 JSON for this requirement."
                    ),
                },
            ]
            response_format: dict[str, Any] = _plan_response_format(
                self.client.capability_profile()
            )
            used_object_fallback = False
            diagnostics: list[str] = []
            attempts = self.client.settings.repair_attempts
            attempt = 1
            stage(SEMANTIC_PLAN_STARTED)
            while attempt <= attempts:
                self._set_state(session_id, "generating", diagnostics=diagnostics)
                try:
                    completion = self.client.complete(
                        messages, response_format=response_format
                    )
                except FactoryProviderError as exc:
                    if (
                        not used_object_fallback
                        and self.client.capability_profile().json_object_fallback
                        and _schema_compatibility_failure(exc)
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
                try:
                    parsed = json.loads(completion.content)
                    plan = AgentSemanticPlanV1.from_dict(parsed)
                except (
                    json.JSONDecodeError,
                    TypeError,
                    ValueError,
                    ContractValidationError,
                ) as exc:
                    diagnostics.append(_generation_failure(attempt, exc))
                    messages.append(completion.assistant_message)
                    messages.append(
                        {"role": "user", "content": _repair_prompt(diagnostics)}
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
                missing = self._missing_capabilities(blueprint)
                if missing:
                    self._set_state(
                        session_id,
                        "missing_capability",
                        blueprint=blueprint.to_dict(),
                        diagnostics=[],
                        missing_capabilities=missing,
                        resource_plan=resource_plan(blueprint, self.catalog),
                        identity={"name": display, "slug": slug},
                    )
                    return self.get_session(project_id, session_id)
                stage(COMPILE_STARTED)
                stage(COMPILE_COMPLETED)
                stage(VALIDATION_STARTED)
                try:
                    compile_blueprint(blueprint, self.catalog, name=display, slug=slug)
                except BlueprintCompileError as exc:
                    diagnostics.extend(
                        f"attempt {attempt}: {item}" for item in exc.diagnostics
                    )
                    messages.append(completion.assistant_message)
                    messages.append(
                        {"role": "user", "content": _repair_prompt(diagnostics)}
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
                    resource_plan=resource_plan(blueprint, self.catalog),
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
            if self._missing_capabilities(blueprint):
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

    def _append_interview(self, session_id: str) -> None:
        previous = self.store.messages(session_id)
        reply = self._interview_reply(session_id)
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

    def _interview_reply(self, session_id: str) -> str:
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
            return self.client.complete(messages).content.strip() or _CANNED_FOLLOW_UP
        except FactoryProviderError:
            return _CANNED_FOLLOW_UP

    def _missing_capabilities(self, blueprint: AgentBlueprint) -> list[dict[str, Any]]:
        missing: list[dict[str, Any]] = []
        components = {
            resource["name"]: resource
            for resource in self.catalog.resources(kind="component")["resources"]
        }
        for component_type in blueprint.required_capabilities.component_types:
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
                item = self._missing_reference(kind, reference, expected_kinds[kind])
                if item is not None:
                    missing.append(item)
        return missing

    def _missing_reference(
        self, kind: str, reference: str, expected_kinds: set[str]
    ) -> dict[str, Any] | None:
        try:
            resource = self.catalog.by_reference(reference)
        except ResourceCatalogError:
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
        listed = ProjectResourceService(self.projects, self.catalog).list(project_id)
        summary = self.projects.project_summary(project_id)
        return builder_project_context(
            project_id=project_id,
            knowledge=list(summary.get("knowledge") or []),
            project_resources=list(listed.get("resources") or []),
            catalog_resources=list(self.catalog.resources().get("resources") or []),
        )

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


def _generation_failure(attempt: int, exc: BaseException) -> str:
    detail = " ".join(str(exc).split())[:180]
    name = type(exc).__name__
    if detail:
        return f"attempt {attempt}: invalid AgentSemanticPlan ({name}: {detail})"
    return f"attempt {attempt}: invalid AgentSemanticPlan ({name})"


def _repair_prompt(diagnostics: list[str]) -> str:
    return (
        "Repair only the invalid AgentSemanticPlanV1 fields. Do not add resource "
        "hashes, Knowledge UUIDs, node IDs, canvas positions, source.lock, or "
        "permissions. Diagnostics: " + "; ".join(diagnostics)
    )


def _schema_compatibility_failure(exc: FactoryProviderError) -> bool:
    if exc.code != "factory_request_invalid":
        return False
    details = exc.details or {}
    blob = " ".join(
        [
            str(exc),
            str(details.get("rejected_field") or ""),
            str(details.get("bounded_message") or ""),
            str(details.get("provider_error_type") or ""),
        ]
    ).casefold()
    return any(
        hint in blob
        for hint in (
            "json_schema",
            "flavored json schema",
            "response_format",
            "moonshot flavored",
            "mfjs",
        )
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
    schema["$defs"]["typed_fields"]["description"] = (
        "Non-empty map from slug keys to type names. Keys must match "
        "[a-z][a-z0-9-]{0,62} and use hyphens, not underscores. Values are "
        "type names such as string."
    )
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
