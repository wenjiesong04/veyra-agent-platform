"""Local-only Project directory and Agent library HTTP surface."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Annotated, Any, Literal, TypeVar, cast

from fastapi import (
    APIRouter,
    File,
    Form,
    Header,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from veyra_agent_platform.contracts.common import ContractValidationError, new_uuid7
from veyra_agent_platform.local.library.service import DraftConflict, LibraryService
from veyra_agent_platform.local.projects.origins import CommunityAgentOrigin
from veyra_agent_platform.local.projects.packaging import MAX_PROJECT_ARCHIVE_BYTES
from veyra_agent_platform.local.projects.service import (
    MAX_AGENT_IMPORT_BYTES,
    ProjectError,
    ProjectService,
)
from veyra_agent_platform.local.resources.project import (
    ProjectResourceError,
    ProjectResourceService,
)
from veyra_agent_platform.local.runtime.profiles import (
    RuntimeApiProfile,
    RuntimeApiProfileInput,
    RuntimeProfileError,
    RuntimeProfileStore,
)
from veyra_agent_platform.local.storage import IdempotencyConflict

_Result = TypeVar("_Result")


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateProjectRequest(_ClosedModel):
    name: str | None = None
    description: str = ""
    agents: list[dict[str, Any]] = Field(default_factory=list)
    templates: list[dict[str, str]] = Field(default_factory=list)
    runtime_profile: RuntimeApiProfileInput | None = None


class OpenProjectRequest(_ClosedModel):
    root_path: str = Field(min_length=1)


class ImportProjectPathRequest(_ClosedModel):
    path: str = Field(min_length=1)


class AddProjectResourceRequest(_ClosedModel):
    reference: str = Field(min_length=3, max_length=200)
    source: Literal["manual", "factory", "imported", "reconciled"] = "manual"


class UpdateProjectRequest(_ClosedModel):
    name: str | None = None
    description: str | None = None
    pinned: StrictBool | None = None
    runtime_profile: RuntimeApiProfileInput | None = None

    @model_validator(mode="after")
    def require_update(self) -> UpdateProjectRequest:
        if not self.model_fields_set:
            raise ValueError("at least one Project field is required")
        return self


class ReplaceDraftRequest(_ClosedModel):
    source: dict[str, Any]
    expected_revision: int = Field(ge=0)


class CommitAgentRequest(_ClosedModel):
    expected_revision: int = Field(ge=0)


class CreateAgentRequest(_ClosedModel):
    mode: Literal["blank", "template"]
    template_id: str | None = None
    name: str | None = None
    description: str | None = None
    parent_agent_id: str | None = None
    runtime_profile: RuntimeApiProfileInput | None = None

    @model_validator(mode="after")
    def require_template_for_template_mode(self) -> CreateAgentRequest:
        if self.mode == "template" and self.template_id is None:
            raise ValueError("template_id is required for template mode")
        if self.mode == "blank" and self.template_id is not None:
            raise ValueError("template_id is only valid for template mode")
        return self


class CreateWorkflowRequest(_ClosedModel):
    name: str | None = None
    description: str | None = None


class CreateKnowledgeRequest(_ClosedModel):
    name: str | None = None
    description: str | None = None
    text: str | None = None


class UpdateKnowledgeRequest(_ClosedModel):
    name: str | None = None
    description: str | None = None
    text: str | None = None

    @model_validator(mode="after")
    def require_update(self) -> UpdateKnowledgeRequest:
        if not self.model_fields_set:
            raise ValueError("at least one Knowledge field is required")
        return self


class UpdateAgentRequest(_ClosedModel):
    pinned: Literal[True] | None = None
    runtime_profile: RuntimeApiProfileInput | None = None

    @model_validator(mode="after")
    def require_update(self) -> UpdateAgentRequest:
        if not self.model_fields_set:
            raise ValueError("at least one Agent field is required")
        return self


class TypedApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


def typed_error_response(_: Request, error: Exception) -> JSONResponse:
    typed_error = cast(TypedApiError, error)
    return JSONResponse(
        status_code=typed_error.status_code,
        content={
            "schema_version": "1.0",
            "code": typed_error.code,
            "message": typed_error.message,
            "request_id": new_uuid7(),
        },
    )


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

    @router.get("")
    def list_projects(request: Request) -> dict[str, Any]:
        projects, _ = _services(request)
        projects.reconcile_managed_storage()
        return {
            "schema_version": "1.0",
            "projects": [
                _project_response(request, projects.project_summary(row["project_id"]))
                for row in projects.repository.projects()
            ],
        }

    @router.post("", status_code=status.HTTP_201_CREATED)
    def create_project(
        payload: CreateProjectRequest, request: Request
    ) -> dict[str, Any]:
        projects, _ = _services(request)

        def operation() -> dict[str, Any]:
            project = projects.create_managed(
                name=payload.name,
                description=payload.description,
                sources=payload.agents,
                template_selections=payload.templates,
            )
            if payload.runtime_profile is not None:
                _profiles(request).set_project(
                    project["project_id"], payload.runtime_profile.profile()
                )
            return _project_response(request, project)

        return _translate(operation)

    @router.post("/open")
    def open_project(payload: OpenProjectRequest, request: Request) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(
            lambda: _project_response(request, projects.index(payload.root_path))
        )

    @router.post("/import", status_code=status.HTTP_201_CREATED)
    def import_project(
        request: Request,
        file: Annotated[UploadFile, File()],
    ) -> dict[str, Any]:
        projects, _ = _services(request)
        contents = file.file.read(MAX_PROJECT_ARCHIVE_BYTES + 1)
        return _translate(
            lambda: _project_response(
                request,
                projects.import_archive(filename=file.filename, contents=contents),
            )
        )

    @router.post("/import-path", status_code=status.HTTP_201_CREATED)
    def import_project_from_path(
        payload: ImportProjectPathRequest, request: Request
    ) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(
            lambda: _project_response(
                request, projects.import_archive_from_path(payload.path)
            )
        )

    @router.get("/{project_id}/resources")
    def list_project_resources(project_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _project_resources(request).list(project_id))

    @router.post("/{project_id}/resources", status_code=status.HTTP_201_CREATED)
    def add_project_resource(
        project_id: str, payload: AddProjectResourceRequest, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _project_resources(request).add(
                project_id, payload.reference, source=payload.source
            )
        )

    @router.delete("/{project_id}/resources/{resource_id}/versions/{version}")
    def remove_project_resource(
        project_id: str, resource_id: str, version: str, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _project_resources(request).remove(
                project_id, f"{resource_id}@{version}"
            )
        )

    @router.get("/{project_id}")
    def get_project(project_id: str, request: Request) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(
            lambda: _project_response(request, projects.project_summary(project_id))
        )

    @router.patch("/{project_id}")
    def update_project(
        project_id: str, payload: UpdateProjectRequest, request: Request
    ) -> dict[str, Any]:
        projects, _ = _services(request)

        def operation() -> dict[str, Any]:
            has_metadata = bool(
                {"name", "description", "pinned"} & payload.model_fields_set
            )
            project = (
                projects.edit(
                    project_id,
                    name=payload.name if "name" in payload.model_fields_set else None,
                    description=(
                        payload.description
                        if "description" in payload.model_fields_set
                        else None
                    ),
                    pinned=payload.pinned
                    if "pinned" in payload.model_fields_set
                    else None,
                )
                if has_metadata
                else projects.project_summary(project_id)
            )
            if "runtime_profile" in payload.model_fields_set:
                _profiles(request).set_project(
                    project_id,
                    payload.runtime_profile.profile()
                    if payload.runtime_profile is not None
                    else None,
                )
            return _project_response(request, project)

        return _translate(operation)

    @router.delete("/{project_id}")
    def delete_project(project_id: str, request: Request) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(lambda: projects.remove(project_id))

    @router.get("/{project_id}/export")
    def export_project(project_id: str, request: Request) -> Response:
        projects, _ = _services(request)

        def operation() -> Response:
            payload, filename = projects.export_archive(project_id)
            return Response(
                content=payload,
                media_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "X-Content-Type-Options": "nosniff",
                },
            )

        return _translate(operation)

    @router.get("/{project_id}/files/content")
    def get_project_file(
        project_id: str,
        request: Request,
        path: Annotated[str, Query(min_length=1)],
    ) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(lambda: projects.file_content(project_id, path))

    @router.get("/{project_id}/files")
    def list_project_files(project_id: str, request: Request) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(lambda: projects.list_files(project_id))

    @router.get("/{project_id}/agent-templates")
    def list_agent_templates(project_id: str, request: Request) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(
            lambda: {
                "schema_version": "1.0",
                "project_id": projects.project_summary(project_id)["project_id"],
                "templates": projects.template_metadata(),
            }
        )

    @router.post("/{project_id}/agents", status_code=status.HTTP_201_CREATED)
    def create_agent(
        project_id: str, payload: CreateAgentRequest, request: Request
    ) -> dict[str, Any]:
        projects, _ = _services(request)

        def operation() -> dict[str, Any]:
            agent_payload = payload.model_dump(
                exclude={"runtime_profile"}, exclude_none=True
            )
            agent = projects.create_agent(project_id=project_id, **agent_payload)
            if "runtime_profile" in payload.model_fields_set:
                _profiles(request).set_agent(
                    project_id,
                    agent["agent_id"],
                    payload.runtime_profile.profile()
                    if payload.runtime_profile is not None
                    else None,
                )
            return _agent_response(request, agent)

        return _translate(operation)

    @router.post("/{project_id}/agents/import", status_code=status.HTTP_201_CREATED)
    def import_agent(
        project_id: str,
        request: Request,
        file: Annotated[UploadFile, File()],
        name: Annotated[str | None, Form()] = None,
        description: Annotated[str | None, Form()] = None,
        parent_agent_id: Annotated[str | None, Form()] = None,
        community_owner_handle: Annotated[str | None, Form()] = None,
        community_slug: Annotated[str | None, Form()] = None,
        community_version: Annotated[str | None, Form()] = None,
        community_source_hash: Annotated[str | None, Form()] = None,
    ) -> dict[str, Any]:
        projects, _ = _services(request)
        contents = file.file.read(MAX_AGENT_IMPORT_BYTES + 1)
        return _translate(
            lambda: _import_agent(
                projects,
                project_id=project_id,
                filename=file.filename,
                contents=contents,
                name=name,
                description=description,
                parent_agent_id=parent_agent_id,
                community_owner_handle=community_owner_handle,
                community_slug=community_slug,
                community_version=community_version,
                community_source_hash=community_source_hash,
            )
        )

    @router.get("/{project_id}/agents")
    def list_agents(project_id: str, request: Request) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(
            lambda: {
                "schema_version": "1.0",
                "agents": _project_response(
                    request, projects.project_summary(project_id)
                )["agents"],
            }
        )

    @router.patch("/{project_id}/agents/{agent_id}")
    def update_agent(
        project_id: str,
        agent_id: str,
        payload: UpdateAgentRequest,
        request: Request,
    ) -> dict[str, Any]:
        projects, _ = _services(request)

        def operation() -> dict[str, Any]:
            if payload.pinned is True:
                project = projects.pin_agent(project_id, agent_id)
            else:
                project = projects.project_summary(project_id)
            if "runtime_profile" in payload.model_fields_set:
                _profiles(request).set_agent(
                    project_id,
                    agent_id,
                    payload.runtime_profile.profile()
                    if payload.runtime_profile is not None
                    else None,
                )
            return _project_response(request, project)

        return _translate(operation)

    @router.delete("/{project_id}/agents/{agent_id}")
    def delete_agent(
        project_id: str, agent_id: str, request: Request
    ) -> dict[str, Any]:
        projects, _ = _services(request)

        def operation() -> dict[str, Any]:
            result = projects.remove_agent(project_id, agent_id)
            result["project"] = _project_response(request, result["project"])
            return result

        return _translate(operation)

    @router.get("/{project_id}/agents/{agent_id}/draft")
    def get_draft(
        project_id: str, agent_id: str, response: Response, request: Request
    ) -> dict[str, Any]:
        _, library = _services(request)
        result = _translate(lambda: library.draft(project_id, agent_id))
        response.headers["ETag"] = result["etag"]
        return result

    @router.patch("/{project_id}/agents/{agent_id}/draft")
    def patch_draft(
        project_id: str,
        agent_id: str,
        payload: ReplaceDraftRequest,
        response: Response,
        request: Request,
        if_match: str = Header(),
        idempotency_key: str = Header(),
    ) -> dict[str, Any]:
        _, library = _services(request)
        result = _translate(
            lambda: library.replace_draft(
                project_id=project_id,
                agent_id=agent_id,
                expected_etag=if_match,
                idempotency_key=idempotency_key,
                **payload.model_dump(),
            )
        )
        response.headers["ETag"] = result["etag"]
        return result

    @router.post("/{project_id}/agents/{agent_id}/validate")
    def validate_agent(
        project_id: str, agent_id: str, request: Request
    ) -> dict[str, Any]:
        _, library = _services(request)
        return _translate(lambda: library.validate(project_id, agent_id))

    @router.post("/{project_id}/agents/{agent_id}/commit")
    def commit_agent(
        project_id: str,
        agent_id: str,
        payload: CommitAgentRequest,
        request: Request,
        if_match: str = Header(),
        idempotency_key: str = Header(),
    ) -> dict[str, Any]:
        _, library = _services(request)
        return _translate(
            lambda: library.commit(
                project_id=project_id,
                agent_id=agent_id,
                expected_revision=payload.expected_revision,
                expected_etag=if_match,
                idempotency_key=idempotency_key,
            )
        )

    @router.post("/{project_id}/agents/{agent_id}/draft/reload")
    def reload_draft(
        project_id: str, agent_id: str, response: Response, request: Request
    ) -> dict[str, Any]:
        _, library = _services(request)
        result = _translate(lambda: library.reload_from_disk(project_id, agent_id))
        response.headers["ETag"] = result["etag"]
        return result

    @router.get("/{project_id}/agents/{agent_id}/versions")
    def agent_versions(
        project_id: str, agent_id: str, request: Request
    ) -> dict[str, Any]:
        _, library = _services(request)
        return _translate(lambda: library.versions(project_id, agent_id))

    @router.get("/{project_id}/workflows/{workflow_id}/versions")
    def workflow_versions(
        project_id: str, workflow_id: str, request: Request
    ) -> dict[str, Any]:
        _, library = _services(request)
        return _translate(lambda: library.workflow_versions(project_id, workflow_id))

    @router.get("/{project_id}/agents/{agent_id}/export")
    def export_agent(
        project_id: str, agent_id: str, request: Request
    ) -> dict[str, Any]:
        _, library = _services(request)
        return _translate(lambda: library.export(project_id, agent_id))

    @router.get("/{project_id}/workflows")
    def list_workflows(project_id: str, request: Request) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(
            lambda: {
                "schema_version": "1.0",
                "workflows": projects.project_summary(project_id)["workflows"],
            }
        )

    @router.post("/{project_id}/workflows", status_code=status.HTTP_201_CREATED)
    def create_workflow(
        project_id: str, payload: CreateWorkflowRequest, request: Request
    ) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(
            lambda: projects.create_workflow(
                project_id=project_id,
                name=payload.name,
                description=payload.description,
            )
        )

    @router.delete("/{project_id}/workflows/{workflow_id}")
    def delete_workflow(
        project_id: str, workflow_id: str, request: Request
    ) -> dict[str, Any]:
        projects, _ = _services(request)

        def operation() -> dict[str, Any]:
            result = projects.remove_workflow(project_id, workflow_id)
            result["project"] = _project_response(request, result["project"])
            return result

        return _translate(operation)

    @router.get("/{project_id}/workflows/{workflow_id}/draft")
    def get_workflow_draft(
        project_id: str, workflow_id: str, response: Response, request: Request
    ) -> dict[str, Any]:
        _, library = _services(request)
        result = _translate(lambda: library.workflow_draft(project_id, workflow_id))
        response.headers["ETag"] = result["etag"]
        return result

    @router.patch("/{project_id}/workflows/{workflow_id}/draft")
    def patch_workflow_draft(
        project_id: str,
        workflow_id: str,
        payload: ReplaceDraftRequest,
        response: Response,
        request: Request,
        if_match: str = Header(),
        idempotency_key: str = Header(),
    ) -> dict[str, Any]:
        _, library = _services(request)
        result = _translate(
            lambda: library.replace_workflow_draft(
                project_id=project_id,
                workflow_id=workflow_id,
                expected_etag=if_match,
                idempotency_key=idempotency_key,
                **payload.model_dump(),
            )
        )
        response.headers["ETag"] = result["etag"]
        return result

    @router.post("/{project_id}/workflows/{workflow_id}/draft/reload")
    def reload_workflow_draft(
        project_id: str, workflow_id: str, response: Response, request: Request
    ) -> dict[str, Any]:
        _, library = _services(request)
        result = _translate(
            lambda: library.reload_workflow_from_disk(project_id, workflow_id)
        )
        response.headers["ETag"] = result["etag"]
        return result

    @router.post("/{project_id}/workflows/{workflow_id}/validate")
    def validate_workflow(
        project_id: str, workflow_id: str, request: Request
    ) -> dict[str, Any]:
        _, library = _services(request)
        return _translate(lambda: library.validate_workflow(project_id, workflow_id))

    @router.post("/{project_id}/workflows/{workflow_id}/commit")
    def commit_workflow(
        project_id: str,
        workflow_id: str,
        payload: CommitAgentRequest,
        request: Request,
        if_match: str = Header(),
        idempotency_key: str = Header(),
    ) -> dict[str, Any]:
        _, library = _services(request)
        return _translate(
            lambda: library.commit_workflow(
                project_id=project_id,
                workflow_id=workflow_id,
                expected_revision=payload.expected_revision,
                expected_etag=if_match,
                idempotency_key=idempotency_key,
            )
        )

    @router.get("/{project_id}/knowledge")
    def list_knowledge(project_id: str, request: Request) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(
            lambda: {
                "schema_version": "1.0",
                "knowledge": projects.project_summary(project_id)["knowledge"],
            }
        )

    @router.post("/{project_id}/knowledge", status_code=status.HTTP_201_CREATED)
    def create_knowledge(
        project_id: str, payload: CreateKnowledgeRequest, request: Request
    ) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(
            lambda: projects.create_knowledge(
                project_id=project_id,
                name=payload.name,
                description=payload.description,
                text=payload.text,
            )
        )

    @router.get("/{project_id}/knowledge/{knowledge_id}")
    def get_knowledge(
        project_id: str, knowledge_id: str, request: Request
    ) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(lambda: projects.knowledge_summary(project_id, knowledge_id))

    @router.patch("/{project_id}/knowledge/{knowledge_id}")
    def patch_knowledge(
        project_id: str,
        knowledge_id: str,
        payload: UpdateKnowledgeRequest,
        request: Request,
    ) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(
            lambda: projects.replace_knowledge(
                project_id=project_id,
                knowledge_id=knowledge_id,
                name=payload.name,
                description=payload.description,
                text=payload.text,
            )
        )

    @router.delete("/{project_id}/knowledge/{knowledge_id}")
    def delete_knowledge(
        project_id: str, knowledge_id: str, request: Request
    ) -> dict[str, Any]:
        projects, _ = _services(request)

        def operation() -> dict[str, Any]:
            result = projects.remove_knowledge(project_id, knowledge_id)
            result["project"] = _project_response(request, result["project"])
            return result

        return _translate(operation)

    return router


def _services(request: Request) -> tuple[ProjectService, LibraryService]:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return request.app.state.projects, request.app.state.library


def _import_agent(
    projects: ProjectService,
    *,
    project_id: str,
    filename: str | None,
    contents: bytes,
    name: str | None,
    description: str | None,
    parent_agent_id: str | None,
    community_owner_handle: str | None,
    community_slug: str | None,
    community_version: str | None,
    community_source_hash: str | None,
) -> dict[str, Any]:
    try:
        community_origin = CommunityAgentOrigin.from_optional_fields(
            owner_handle=community_owner_handle,
            slug=community_slug,
            version=community_version,
            source_hash=community_source_hash,
        )
    except ValueError as exc:
        raise ProjectError(str(exc), "community_origin_invalid") from exc
    return projects.import_agent(
        project_id=project_id,
        filename=filename,
        contents=contents,
        name=name,
        description=description,
        parent_agent_id=parent_agent_id,
        community_origin=community_origin,
    )


def _profiles(request: Request) -> RuntimeProfileStore:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return cast(RuntimeProfileStore, request.app.state.runtime_profiles)


def _project_resources(request: Request) -> ProjectResourceService:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return cast(ProjectResourceService, request.app.state.project_resources)


def _profile_summary(
    request: Request, profile: RuntimeApiProfile | None
) -> dict[str, Any] | None:
    if profile is None:
        return None
    settings = request.app.state.runtime.model.settings
    return profile.to_dict(
        configured=bool(
            settings.allow_process_environment_key
            and os.environ.get(profile.api_key_env, "").strip()
        )
    )


def _project_response(request: Request, project: dict[str, Any]) -> dict[str, Any]:
    result = dict(project)
    profiles = _profiles(request)
    result["runtime_profile"] = _profile_summary(
        request, profiles.get_project(project["project_id"])
    )
    result["agents"] = [
        {
            **agent,
            "runtime_profile": _profile_summary(
                request, profiles.get_agent(project["project_id"], agent["agent_id"])
            ),
        }
        for agent in project["agents"]
    ]
    return result


def _agent_response(request: Request, agent: dict[str, Any]) -> dict[str, Any]:
    result = dict(agent)
    result["runtime_profile"] = _profile_summary(
        request, _profiles(request).get_agent(agent["project_id"], agent["agent_id"])
    )
    return result


def _translate(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except DraftConflict as exc:
        raise TypedApiError(409, "draft_conflict", str(exc)) from exc
    except IdempotencyConflict as exc:
        raise TypedApiError(409, "idempotency_conflict", str(exc)) from exc
    except RuntimeProfileError as exc:
        status_code = 404 if exc.code.endswith("_not_found") else 422
        raise TypedApiError(status_code, exc.code, str(exc)) from exc
    except ProjectError as exc:
        code = getattr(exc, "code", "project_invalid")
        if code != "project_invalid":
            raise TypedApiError(422, code, str(exc)) from exc
        raise TypedApiError(422, "project_invalid", str(exc)) from exc
    except ProjectResourceError as exc:
        status_code = 409 if exc.code == "resource_in_use" else 422
        raise TypedApiError(status_code, exc.code, str(exc)) from exc
    except ContractValidationError as exc:
        raise TypedApiError(422, "contract_invalid", str(exc)) from exc
    except TypedApiError:
        raise
    except Exception as exc:
        raise TypedApiError(
            500,
            "local_internal_error",
            str(exc) or "local service failed",
        ) from exc
