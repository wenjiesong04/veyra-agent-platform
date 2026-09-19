"""Review stored source proposals before explicitly changing a Draft."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from veyra_agent_platform.local.api.projects import TypedApiError
from veyra_agent_platform.local.factory.edit_service import (
    EditCommand,
    EditProposalService,
    KnowledgeBindingUnresolved,
    ResourceBindingUnresolved,
    TargetKind,
)

from .routes import _translate


class CreateEditProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_kind: TargetKind
    target_id: str = Field(min_length=1, max_length=64)
    instruction: str = Field(min_length=1, max_length=10_000)
    expected_revision: int = Field(ge=0, strict=True)
    expected_etag: str = Field(min_length=1, max_length=200)


class CreateKnowledgeBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1, max_length=64)
    instruction: str = Field(min_length=1, max_length=10_000)
    expected_revision: int = Field(ge=0, strict=True)
    expected_etag: str = Field(min_length=1, max_length=200)


class CreateResourceBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1, max_length=64)
    instruction: str = Field(min_length=1, max_length=10_000)
    expected_revision: int = Field(ge=0, strict=True)
    expected_etag: str = Field(min_length=1, max_length=200)


class CreateValidationRepairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1, max_length=64)
    reference: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=0, strict=True)
    expected_etag: str = Field(min_length=1, max_length=200)


class EditProposalCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: EditCommand
    confirm: StrictBool


def build_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}/edit-proposals", tags=["factory"]
    )

    @router.post("", status_code=status.HTTP_201_CREATED)
    def create(
        project_id: str, payload: CreateEditProposalRequest, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _service(request).create(
                project_id,
                payload.target_kind,
                payload.target_id,
                payload.instruction,
                payload.expected_revision,
                payload.expected_etag,
            )
        )

    @router.post("/knowledge-binding", status_code=status.HTTP_201_CREATED)
    def create_knowledge_binding(
        project_id: str, payload: CreateKnowledgeBindingRequest, request: Request
    ) -> dict[str, Any]:
        service = _service(request)

        def operation() -> dict[str, Any]:
            try:
                return service.create_knowledge_binding(
                    project_id,
                    payload.agent_id,
                    payload.instruction,
                    payload.expected_revision,
                    payload.expected_etag,
                )
            except KnowledgeBindingUnresolved as exc:
                raise TypedApiError(
                    422,
                    f"knowledge_mention_{exc.status}",
                    "No single Project Knowledge document matched this request.",
                    details={
                        "candidates": ", ".join(
                            f"{item['name']} ({item['knowledge_id']}@{item['version']})"
                            for item in exc.candidates
                        )
                    },
                ) from exc

        return _translate(operation)

    @router.post("/resource-binding", status_code=status.HTTP_201_CREATED)
    def create_resource_binding(
        project_id: str, payload: CreateResourceBindingRequest, request: Request
    ) -> dict[str, Any]:
        service = _service(request)

        def operation() -> dict[str, Any]:
            try:
                return service.create_resource_binding(
                    project_id,
                    payload.agent_id,
                    payload.instruction,
                    payload.expected_revision,
                    payload.expected_etag,
                )
            except ResourceBindingUnresolved as exc:
                if exc.status == "unbound":
                    message = (
                        "filesystem.read is available in the Catalog but has not "
                        "been added to this Project."
                    )
                elif exc.status == "ambiguous":
                    message = (
                        "Multiple Project Resources match; choose an exact version."
                    )
                else:
                    message = "No supported Project Resource matched this request."
                raise TypedApiError(
                    422,
                    f"resource_mention_{exc.status}",
                    message,
                    details={
                        "candidates": ", ".join(
                            f"{item['name']} ({item['reference']})"
                            for item in exc.candidates
                        )
                    },
                ) from exc

        return _translate(operation)

    @router.post("/validation-repair", status_code=status.HTTP_201_CREATED)
    def create_validation_repair(
        project_id: str, payload: CreateValidationRepairRequest, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _service(request).create_validation_repair(
                project_id,
                payload.agent_id,
                payload.reference,
                payload.code,
                payload.expected_revision,
                payload.expected_etag,
            )
        )

    @router.get("")
    def list_proposals(
        project_id: str, target_kind: TargetKind, target_id: str, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _service(request).list(project_id, target_kind, target_id)
        )

    @router.get("/{proposal_id}")
    def get(project_id: str, proposal_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _service(request).get(project_id, proposal_id))

    @router.post("/{proposal_id}/commands")
    def command(
        project_id: str,
        proposal_id: str,
        payload: EditProposalCommandRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _translate(
            lambda: _service(request).command(
                project_id, proposal_id, payload.command, confirm=payload.confirm
            )
        )

    return router


def _service(request: Request) -> EditProposalService:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return cast(EditProposalService, request.app.state.edit_proposals)
