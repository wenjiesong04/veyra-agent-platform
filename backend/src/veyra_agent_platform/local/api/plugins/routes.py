"""HTTP surface for safe Plugin Pack import and explicit activation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, TypeVar, cast

from fastapi import APIRouter, File, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, StrictBool

from veyra_agent_platform.local.api.projects import TypedApiError
from veyra_agent_platform.local.plugins import (
    PluginError,
    PluginPackError,
    PluginService,
)
from veyra_agent_platform.local.plugins.packaging import MAX_PLUGIN_ARCHIVE_BYTES

_Result = TypeVar("_Result")


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActivatePluginRequest(_ClosedModel):
    confirm: StrictBool


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/plugins", tags=["plugins"])

    @router.get("")
    def list_plugins(request: Request) -> dict[str, Any]:
        return _translate(lambda: _plugins(request).list_packs())

    @router.post("/import", status_code=status.HTTP_201_CREATED)
    def import_plugin(
        request: Request,
        file: Annotated[UploadFile, File()],
    ) -> dict[str, Any]:
        contents = file.file.read(MAX_PLUGIN_ARCHIVE_BYTES + 1)
        return _translate(
            lambda: _plugins(request).import_archive(
                filename=file.filename, contents=contents
            )
        )

    @router.post("/{plugin_id}/versions/{version}/activate")
    def activate_plugin(
        plugin_id: str,
        version: str,
        payload: ActivatePluginRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _translate(
            lambda: _plugins(request).activate(
                plugin_id, version, confirm=payload.confirm
            )
        )

    return router


def _plugins(request: Request) -> PluginService:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return cast(PluginService, request.app.state.plugins)


def _translate(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except PluginPackError as exc:
        raise TypedApiError(422, exc.code, str(exc)) from exc
    except PluginError as exc:
        status_code = 404 if exc.code == "plugin_not_found" else 422
        raise TypedApiError(status_code, exc.code, str(exc)) from exc
