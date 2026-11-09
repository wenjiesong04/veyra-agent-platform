"""HTTP surface for immutable local Resource Catalog descriptors."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from veyra_agent_platform.local.api.projects import TypedApiError
from veyra_agent_platform.local.resources import (
    ResourceCatalog,
    ResourceCatalogError,
    ResourceWorkshop,
    ResourceWorkshopError,
)
from veyra_agent_platform.local.resources.readiness import ResourceReadiness

_Result = TypeVar("_Result")


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateResourceDraftRequest(_ClosedModel):
    confirm: StrictBool
    kind: str = Field(min_length=1, max_length=32)
    requested_reference: str = Field(min_length=3, max_length=200)
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    instruction: str | None = Field(default=None, max_length=20_000)


class ApproveResourceDraftRequest(_ClosedModel):
    instruction: str | None = Field(default=None, max_length=20_000)


class EnableResourceRequest(_ClosedModel):
    enabled: StrictBool


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/resources", tags=["resources"])

    @router.get("")
    def list_resources(
        request: Request,
        kind: str | None = None,
        availability: str | None = None,
    ) -> dict[str, Any]:
        return _translate(
            lambda: _readiness(request).resources(kind=kind, availability=availability)
        )

    @router.post("/drafts", status_code=status.HTTP_201_CREATED)
    def create_draft(
        payload: CreateResourceDraftRequest, request: Request
    ) -> dict[str, Any]:
        return _readiness(request).response(
            _workshop_translate(
                lambda: _workshop(request).create_draft(
                    confirm=payload.confirm,
                    kind=payload.kind,
                    requested_reference=payload.requested_reference,
                    name=payload.name,
                    description=payload.description,
                    instruction=payload.instruction,
                )
            )
        )

    @router.post("/{resource_id}/versions/{version}/approve")
    def approve_skill(
        resource_id: str,
        version: str,
        payload: ApproveResourceDraftRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _readiness(request).response(
            _workshop_translate(
                lambda: _workshop(request).approve_skill(
                    resource_id, version, payload.instruction
                )
            )
        )

    @router.post("/{resource_id}/versions/{version}/enable")
    def enable_resource(
        resource_id: str,
        version: str,
        payload: EnableResourceRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _readiness(request).response(
            _workshop_translate(
                lambda: _workshop(request).set_enabled(
                    resource_id, version, enabled=payload.enabled
                )
            )
        )

    @router.get("/{resource_id}/versions/{version}")
    def resource_detail(
        resource_id: str, version: str, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _readiness(request).project(
                _catalog(request).detail(resource_id, version)
            )
        )

    return router


def _catalog(request: Request) -> ResourceCatalog:
    return cast(ResourceCatalog, request.app.state.resource_catalog)


def _readiness(request: Request) -> ResourceReadiness:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return cast(ResourceReadiness, request.app.state.resource_readiness)


def _workshop(request: Request) -> ResourceWorkshop:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    workshop = getattr(request.app.state, "workshop", None)
    if workshop is None:
        raise TypedApiError(
            503, "workshop_unavailable", "Resource Workshop is starting"
        )
    return cast(ResourceWorkshop, workshop)


def _translate(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except ResourceCatalogError as exc:
        status_code = 404 if exc.code == "resource_not_found" else 400
        raise TypedApiError(status_code, exc.code, str(exc)) from exc


def _workshop_translate(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except ResourceWorkshopError as exc:
        raise TypedApiError(422, exc.code, str(exc)) from exc
