"""Project-scoped Factory conversations and bounded Blueprint generation."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from veyra_agent_platform.contracts.agent import AgentBlueprint
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService
from veyra_agent_platform.local.resources import ResourceCatalog

from .client import FactoryProviderError, KimiClient
from .compiler import compile_blueprint
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
_INITIAL_PROMPT = (
    "Tell me what this Agent should accomplish, what it receives, and what a "
    "successful result looks like."
)
_READY_PROMPT = (
    "The requirement is ready for a Blueprint. Review the resource plan, then "
    "generate a Draft when you are ready."
)


class FactoryError(ProjectError):
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
        return self.store.payload(row, self.store.messages(session_id))

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
            if not self.client.configured:
                raise FactoryProviderError(
                    "factory_provider_not_configured",
                    "Factory model provider is not configured",
                )
            reply = self._interview_reply(project_id, session_id)
            with self.store.transaction() as connection:
                self.store.append_message(
                    connection,
                    message_id=new_uuid7(),
                    session_id=session_id,
                    sequence=len(previous) + 1,
                    role="assistant",
                    content=reply,
                    created_at=_now(),
                )
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
                messages: list[dict[str, Any]] = [
                    {"role": "system", "content": _generation_prompt(self.catalog)},
                    *[
                        {"role": row["role"], "content": row["content"]}
                        for row in self.store.messages(session_id)
                    ],
                    {
                        "role": "user",
                        "content": (
                            "Generate the AgentBlueprint JSON for this requirement."
                        ),
                    },
                ]
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "agent_blueprint",
                        "strict": True,
                        "schema": _blueprint_schema(),
                    },
                }
                diagnostics: list[str] = []
                blueprint: AgentBlueprint | None = None
                for attempt in range(1, 4):
                    self._set_state(session_id, "generating", diagnostics=diagnostics)
                    completion = self.client.complete(
                        messages, response_format=response_format
                    )
                    try:
                        parsed = json.loads(completion.content)
                        blueprint = AgentBlueprint.from_dict(parsed)
                    except (json.JSONDecodeError, TypeError, ValueError) as exc:
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
                        payload = blueprint.to_dict()
                        self._set_state(
                            session_id,
                            "missing_capability",
                            blueprint=payload,
                            diagnostics=[],
                            missing_capabilities=missing,
                            resource_plan=self._resource_plan(blueprint),
                        )
                        return self.get_session(project_id, session_id)
                    self._set_state(
                        session_id,
                        "review",
                        ready=True,
                        next_prompt=(
                            "Review the Blueprint and Resource Plan. Apply it only "
                            "when you explicitly confirm."
                        ),
                        blueprint=blueprint.to_dict(),
                        diagnostics=[],
                        missing_capabilities=[],
                        resource_plan=self._resource_plan(blueprint),
                    )
                    return self.get_session(project_id, session_id)
            except FactoryProviderError:
                self._set_state(
                    session_id,
                    "ready",
                    ready=True,
                    next_prompt=_READY_PROMPT,
                    diagnostics=[],
                )
                raise
            self._set_state(session_id, "review", ready=False, diagnostics=diagnostics)
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
            missing = self._missing_capabilities(blueprint)
            if missing:
                raise FactoryError(
                    "factory_missing_capability",
                    "The Blueprint references resources that are not available",
                )
            source = compile_blueprint(
                blueprint, self.catalog, name=name, description=description
            )
            agent = self.projects.create_agent_from_source(
                project_id=project_id,
                source=source,
                name=name,
                description=description,
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

    def _interview_reply(self, project_id: str, session_id: str) -> str:
        messages = [
            {"role": "system", "content": _interview_prompt(self.catalog)},
            *[
                {"role": row["role"], "content": row["content"]}
                for row in self.store.messages(session_id)
            ],
        ]
        self.client.ensure_model()
        return self.client.complete(messages).content.strip()

    def _missing_capabilities(self, blueprint: AgentBlueprint) -> list[dict[str, Any]]:
        resources = self.catalog.resources()["resources"]
        components = {
            resource["name"]: resource
            for resource in resources
            if resource["kind"] == "component"
        }
        missing: list[dict[str, Any]] = []
        for component_type in blueprint.required_capabilities.component_types:
            resource = components.get(component_type.value)
            if resource is None or not resource["factory_selectable"]:
                missing.append(
                    {
                        "kind": "component",
                        "reference": component_type.value,
                        "reason": "component is not selectable",
                    }
                )
        for tool_ref in blueprint.required_capabilities.tool_refs:
            resource_id, version = tool_ref.rsplit("@", 1)
            try:
                resource = self.catalog.detail(resource_id, version)
            except ValueError:
                missing.append(
                    {
                        "kind": "tool",
                        "reference": tool_ref,
                        "reason": "resource is not registered",
                    }
                )
                continue
            if (
                resource["kind"] not in {"tool", "mcp_tool"}
                or not resource["factory_selectable"]
                or resource["availability"] != "ready"
            ):
                missing.append(
                    {
                        "kind": resource["kind"],
                        "reference": tool_ref,
                        "reason": "resource is not ready",
                    }
                )
        return missing

    def _resource_plan(self, blueprint: AgentBlueprint) -> list[dict[str, Any]]:
        resources = self.catalog.resources()["resources"]
        components = {
            resource["name"]: resource
            for resource in resources
            if resource["kind"] == "component"
        }
        plan: list[dict[str, Any]] = []
        for component_type in blueprint.required_capabilities.component_types:
            resource = components.get(component_type.value)
            if resource:
                plan.append(
                    {
                        "reference": resource["reference"],
                        "kind": resource["kind"],
                        "availability": resource["availability"],
                    }
                )
        for tool_ref in blueprint.required_capabilities.tool_refs:
            resource_id, version = tool_ref.rsplit("@", 1)
            try:
                resource = self.catalog.detail(resource_id, version)
            except ValueError:
                continue
            plan.append(
                {
                    "reference": resource["reference"],
                    "kind": resource["kind"],
                    "availability": resource["availability"],
                }
            )
        return plan

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
            raise ProjectError("unknown Project")


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
    return (
        "You are the Veyra Factory interviewer. Ask one concise follow-up question "
        "at a time about goal, inputs, outputs, environment, risks, approvals, "
        "and success criteria. Never execute tools or invent resources. "
        "Available resource kinds: "
        + ", ".join(
            sorted({resource["kind"] for resource in catalog.resources()["resources"]})
        )
    )


def _generation_prompt(catalog: ResourceCatalog) -> str:
    resources = catalog.resources()["resources"]
    return (
        "You are the Veyra Factory planner. Return only an AgentBlueprint JSON "
        "object matching the supplied schema. Use only the registered Component "
        "and Tool references in this catalog snapshot. Keep permissions minimal, "
        "require verification for consequential results, and never emit arbitrary "
        "code, secret values, or unknown resources. The server will validate every "
        "field and will not execute this Blueprint. Catalog snapshot:\n"
        + json.dumps(resources, ensure_ascii=False, sort_keys=True)
    )


def _blueprint_schema() -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parents[5]
        / "contracts"
        / "schemas"
        / "agent-blueprint.schema.json"
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise FactoryError(
                "factory_schema_unavailable", "The AgentBlueprint schema is invalid"
            )
        return cast(dict[str, Any], payload)
    except (OSError, json.JSONDecodeError) as exc:
        raise FactoryError(
            "factory_schema_unavailable", "The AgentBlueprint schema is unavailable"
        ) from exc
