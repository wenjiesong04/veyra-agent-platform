"""Local execution and evidence endpoints."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from veyra_agent_platform.local.api.projects.routes import TypedApiError, _translate
from veyra_agent_platform.local.runtime.profiles import (
    RuntimeApiProfileInput,
    RuntimeProfileError,
    RuntimeProfileStore,
)
from veyra_agent_platform.local.runtime.service import RuntimeService

_ProfileResult = TypeVar("_ProfileResult")


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inputs: dict[str, Any]
    conversation_id: str | None = None


class CreateAgentConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = None


class RunCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str


class SetRuntimeApiProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: RuntimeApiProfileInput | None


class ValidateRuntimeProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: RuntimeApiProfileInput


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["runtime"])

    @router.get("/runtime/status")
    def runtime_status(request: Request) -> dict[str, Any]:
        return _runtime(request).status()

    @router.post("/runtime/profile/validate")
    def validate_runtime_profile(
        payload: ValidateRuntimeProfileRequest, request: Request
    ) -> dict[str, Any]:
        return _profile_translate(
            lambda: _runtime(request).validate_profile(payload.profile.profile())
        )

    @router.get("/projects/{project_id}/agents/{agent_id}/runtime-readiness")
    def runtime_readiness(
        project_id: str, agent_id: str, request: Request
    ) -> dict[str, Any]:
        return _translate(lambda: _runtime(request).readiness(project_id, agent_id))

    @router.get("/projects/{project_id}/runtime-profile")
    def get_project_profile(project_id: str, request: Request) -> dict[str, Any]:
        profiles = _profiles(request)
        profile = _profile_translate(lambda: profiles.get_project(project_id))
        settings = _runtime(request).model.settings
        return RuntimeProfileStore.payload(
            project_id,
            None,
            profile,
            source="project",
            allow_process_environment_key=settings.allow_process_environment_key,
            secret_store=_runtime(request).model.secret_store,
        )

    @router.patch("/projects/{project_id}/runtime-profile")
    def set_project_profile(
        project_id: str, payload: SetRuntimeApiProfileRequest, request: Request
    ) -> dict[str, Any]:
        profiles = _profiles(request)
        profile = _profile_translate(
            lambda: payload.profile.profile() if payload.profile else None
        )
        saved = _profile_translate(lambda: profiles.set_project(project_id, profile))
        settings = _runtime(request).model.settings
        return RuntimeProfileStore.payload(
            project_id,
            None,
            saved,
            source="project",
            allow_process_environment_key=settings.allow_process_environment_key,
            secret_store=_runtime(request).model.secret_store,
        )

    @router.get("/projects/{project_id}/agents/{agent_id}/runtime-profile")
    def get_agent_profile(
        project_id: str, agent_id: str, request: Request
    ) -> dict[str, Any]:
        profiles = _profiles(request)
        profile = _profile_translate(lambda: profiles.get_agent(project_id, agent_id))
        settings = _runtime(request).model.settings
        return RuntimeProfileStore.payload(
            project_id,
            agent_id,
            profile,
            source="agent",
            allow_process_environment_key=settings.allow_process_environment_key,
            secret_store=_runtime(request).model.secret_store,
        )

    @router.patch("/projects/{project_id}/agents/{agent_id}/runtime-profile")
    def set_agent_profile(
        project_id: str,
        agent_id: str,
        payload: SetRuntimeApiProfileRequest,
        request: Request,
    ) -> dict[str, Any]:
        profiles = _profiles(request)
        profile = _profile_translate(
            lambda: payload.profile.profile() if payload.profile else None
        )
        saved = _profile_translate(
            lambda: profiles.set_agent(project_id, agent_id, profile)
        )
        settings = _runtime(request).model.settings
        return RuntimeProfileStore.payload(
            project_id,
            agent_id,
            saved,
            source="agent",
            allow_process_environment_key=settings.allow_process_environment_key,
            secret_store=_runtime(request).model.secret_store,
        )

    @router.get("/components")
    def components(request: Request) -> dict[str, Any]:
        return _runtime(request).components()

    @router.post("/projects/{project_id}/agents/{agent_id}/run")
    def run(
        project_id: str,
        agent_id: str,
        payload: RunRequest,
        request: Request,
        idempotency_key: str = Header(),
    ) -> dict[str, Any]:
        return _translate(
            lambda: _runtime(request).run(
                project_id,
                agent_id,
                payload.inputs,
                idempotency_key,
                conversation_id=payload.conversation_id,
            )
        )

    @router.post(
        "/projects/{project_id}/agents/{agent_id}/conversations",
        status_code=status.HTTP_201_CREATED,
    )
    def create_conversation(
        project_id: str,
        agent_id: str,
        payload: CreateAgentConversationRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _translate(
            lambda: _conversations(request).create(project_id, agent_id, payload.title)
        )

    @router.get("/projects/{project_id}/agents/{agent_id}/conversations")
    def conversations(
        project_id: str, agent_id: str, request: Request
    ) -> dict[str, Any]:
        return _translate(lambda: _conversations(request).list(project_id, agent_id))

    @router.get(
        "/projects/{project_id}/agents/{agent_id}/conversations/{conversation_id}"
    )
    def conversation_detail(
        project_id: str,
        agent_id: str,
        conversation_id: str,
        request: Request,
    ) -> dict[str, Any]:
        return _translate(
            lambda: _conversations(request).detail(
                project_id, agent_id, conversation_id
            )
        )

    @router.get("/projects/{project_id}/agents/{agent_id}/runs")
    def runs(project_id: str, agent_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _runtime(request).runs(project_id, agent_id))

    @router.get("/projects/{project_id}/agents/{agent_id}/runs/{run_id}")
    def detail(
        project_id: str, agent_id: str, run_id: str, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _runtime(request).run_detail(project_id, agent_id, run_id)
        )

    @router.get("/projects/{project_id}/agents/{agent_id}/runs/{run_id}/events")
    def event_stream(
        project_id: str,
        agent_id: str,
        run_id: str,
        request: Request,
        after: int = Query(default=0, ge=0),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        start = after
        if last_event_id is not None and last_event_id.isdigit():
            start = max(start, int(last_event_id))
        runtime = _runtime(request)
        _translate(lambda: runtime.ensure_run(project_id, agent_id, run_id))
        return StreamingResponse(
            runtime.follow_events(run_id, start),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post("/projects/{project_id}/agents/{agent_id}/runs/{run_id}/commands")
    def command(
        project_id: str,
        agent_id: str,
        run_id: str,
        payload: RunCommandRequest,
        request: Request,
        idempotency_key: str = Header(),
    ) -> dict[str, Any]:
        return _translate(
            lambda: _runtime(request).command(
                project_id, agent_id, run_id, payload.command, idempotency_key
            )
        )

    return router


def _runtime(request: Request) -> RuntimeService:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return cast(RuntimeService, request.app.state.runtime)


def _profiles(request: Request) -> RuntimeProfileStore:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return cast(RuntimeProfileStore, request.app.state.runtime_profiles)


def _conversations(request: Request) -> Any:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return request.app.state.conversations


def _profile_translate(operation: Callable[[], _ProfileResult]) -> _ProfileResult:
    try:
        return operation()
    except RuntimeProfileError as exc:
        status_code = 404 if exc.code.endswith("_not_found") else 422
        raise TypedApiError(status_code, exc.code, str(exc)) from exc
