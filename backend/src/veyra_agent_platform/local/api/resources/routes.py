"""HTTP surface for immutable local Resource Catalog descriptors."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from fastapi import APIRouter, Request

from veyra_agent_platform.local.api.projects import TypedApiError
from veyra_agent_platform.local.resources import ResourceCatalog, ResourceCatalogError

_Result = TypeVar("_Result")


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/resources", tags=["resources"])

    @router.get("")
    def list_resources(
        request: Request,
        kind: str | None = None,
        availability: str | None = None,
    ) -> dict[str, Any]:
        return _translate(
            lambda: _catalog(request).resources(kind=kind, availability=availability)
        )

    @router.get("/{resource_id}/versions/{version}")
    def resource_detail(
        resource_id: str, version: str, request: Request
    ) -> dict[str, Any]:
        return _translate(lambda: _catalog(request).detail(resource_id, version))

    return router


def _catalog(request: Request) -> ResourceCatalog:
    return cast(ResourceCatalog, request.app.state.resource_catalog)


def _translate(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except ResourceCatalogError as exc:
        status_code = 404 if exc.code == "resource_not_found" else 400
        raise TypedApiError(status_code, exc.code, str(exc)) from exc
