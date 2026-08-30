"""Project-scoped Factory conversations and bounded Blueprint generation."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from veyra_agent_platform.contracts.agent import AgentBlueprint
from veyra_agent_platform.contracts.common import ContractValidationError, new_uuid7
from veyra_agent_platform.local.projects.service import ProjectService
from veyra_agent_platform.local.resources import ResourceCatalog, ResourceCatalogError

from .client import FactoryProviderError, KimiClient
from .compiler import (
    BlueprintCompileError,
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
        self._writer_lock = threading.RLock()

    def status(self) -> dict[str, Any]:
        settings = self.client.settings
        return {
            "schema_version": "1.0",
            "configured": self.client.configured,
            "model_id": settings.model_id,
            "model_base_url": settings.model_base_url,
            "model_api_key_env": settings.model_api_key_env,
            "reasoning_effort": settings.reasoning_effort,
            "repair_attempts": settings.repair_attempts,
            "executes_drafts": False,
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

    def generate(self, project_id: str, session_id: str) -> dict[str, Any]:
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
                {"role": "system", "content": _generation_prompt(self.catalog)},
                *[
                    {"role": row["role"], "content": row["content"]}
                    for row in self.store.messages(session_id)
                ],
                {
                    "role": "user",
                    "content": "Generate the AgentBlueprint JSON for this requirement.",
                },
            ]
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "agent_blueprint",
                    "strict": True,
                    "schema": _generation_schema(),
                },
            }
            diagnostics: list[str] = []
            attempts = self.client.settings.repair_attempts
            for attempt in range(1, attempts + 1):
                self._set_state(session_id, "generating", diagnostics=diagnostics)
                try:
                    completion = self.client.complete(
                        messages, response_format=response_format
                    )
                except FactoryProviderError:
                    self._recover_generation(session_id)
                    raise
                try:
                    parsed = json.loads(completion.content)
                    blueprint = AgentBlueprint.from_dict(parsed)
                except (
                    json.JSONDecodeError,
                    TypeError,
                    ValueError,
                    ContractValidationError,
                ) as exc:
                    diagnostics.append(
                        f"attempt {attempt}: invalid AgentBlueprint "
                        f"({type(exc).__name__})"
                    )
                    messages.append(completion.assistant_message)
                    messages.append(
                        {"role": "user", "content": _repair_prompt(diagnostics)}
                    )
                    continue
                missing = self._missing_capabilities(blueprint)
                if missing:
                    self._set_state(
                        session_id,
                        "missing_capability",
                        blueprint=blueprint.to_dict(),
                        diagnostics=[],
                        missing_capabilities=missing,
                        resource_plan=resource_plan(blueprint, self.catalog),
                    )
                    return self.get_session(project_id, session_id)
                try:
                    compile_blueprint(blueprint, self.catalog)
                except BlueprintCompileError as exc:
                    diagnostics.extend(
                        f"attempt {attempt}: {item}" for item in exc.diagnostics
                    )
                    messages.append(completion.assistant_message)
                    messages.append(
                        {"role": "user", "content": _repair_prompt(diagnostics)}
                    )
                    continue
                self._set_state(
                    session_id,
                    "review",
                    ready=True,
                    next_prompt=(
                        "Review the Blueprint and Resource Plan. Apply it only "
                        "when you explicitly confirm. Factory will not run it."
                    ),
                    blueprint=blueprint.to_dict(),
                    diagnostics=[],
                    missing_capabilities=[],
                    resource_plan=resource_plan(blueprint, self.catalog),
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
                "Factory could not produce a valid Blueprint after three attempts",
            )

    def apply_draft(
        self,
        project_id: str,
        session_id: str,
        *,
        confirm: bool,
        name: str | None = None,
        description: str | None = None,
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
            try:
                source, _, _ = compile_blueprint(
                    blueprint, self.catalog, name=name, description=description
                )
            except BlueprintCompileError as exc:
                raise FactoryError(
                    "factory_generation_invalid",
                    "; ".join(exc.diagnostics),
                ) from exc
            agent = self.projects.create_agent_from_source(
                project_id=project_id, source=source
            )
            self._set_state(
                session_id,
                "completed",
                ready=True,
                next_prompt=(
                    "Agent Draft created. Open Studio to review it before running."
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
        messages = [
            {"role": "system", "content": _interview_prompt(self.catalog)},
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


def _repair_prompt(diagnostics: list[str]) -> str:
    return (
        "Repair only the invalid Blueprint fields. Do not add capabilities or "
        "permissions. Diagnostics: " + "; ".join(diagnostics)
    )


def _interview_prompt(catalog: ResourceCatalog) -> str:
    kinds = sorted({resource["kind"] for resource in catalog.factory_snapshot()})
    return (
        "You are the Veyra Factory interviewer. Ask one concise follow-up question "
        "at a time about goal, inputs, outputs, environment, risks, approvals, "
        "and success criteria. Never execute tools or invent resources. "
        "Available resource kinds: " + ", ".join(kinds)
    )


def _generation_prompt(catalog: ResourceCatalog) -> str:
    return (
        "You are the Veyra Factory planner. Return only an AgentBlueprint JSON "
        "object matching the supplied schema. Use only the registered Component, "
        "Tool, Skill, and Policy references in this catalog snapshot. Keep "
        "permissions minimal, require verification for consequential results, and "
        "never emit arbitrary code, secret values, or unknown resources. The "
        "server will validate every field and will not execute this Blueprint. "
        "Catalog snapshot:\n"
        + json.dumps(catalog.factory_snapshot(), ensure_ascii=False, sort_keys=True)
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
    return schema


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
