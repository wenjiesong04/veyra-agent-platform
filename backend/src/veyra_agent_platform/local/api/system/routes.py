"""Explicitly authorized local desktop system routes."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict

from veyra_agent_platform.local.api.projects.routes import TypedApiError
from veyra_agent_platform.local.system import DirectoryPicker, DirectorySelection
from veyra_agent_platform.local.system.directory_picker import (
    DirectoryPickerError,
    DirectoryPickerUnsupportedError,
)

_DESKTOP_INTENT_HEADER = "X-Veyra-Desktop-Intent"
_DESKTOP_INTENT_VALUE = "select-directory"
_LOOPBACK_ORIGIN_HOSTS = {"127.0.0.1", "localhost"}


class SelectedDirectoryResponse(BaseModel):
    """Typed response for a native directory-selection request."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    status: Literal["selected"]
    root_path: str


class CancelledDirectoryResponse(BaseModel):
    """Typed response for a cancelled native directory-selection request."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    status: Literal["cancelled"]
    root_path: None = None


DirectorySelectionResponse = SelectedDirectoryResponse | CancelledDirectoryResponse


def build_router(picker: DirectoryPicker) -> APIRouter:
    router = APIRouter(prefix="/api/v1/system", tags=["system"])

    @router.post(
        "/select-directory",
        response_model=DirectorySelectionResponse,
        status_code=status.HTTP_200_OK,
    )
    def select_directory(request: Request) -> DirectorySelectionResponse:
        _require_explicit_desktop_intent(request)
        try:
            selection = picker.select_directory()
        except DirectoryPickerUnsupportedError as exc:
            raise TypedApiError(501, "directory_picker_unsupported", str(exc)) from exc
        except DirectoryPickerError as exc:
            raise TypedApiError(500, "directory_picker_failed", str(exc)) from exc
        try:
            return _response(selection)
        except DirectoryPickerError as exc:
            raise TypedApiError(500, "directory_picker_failed", str(exc)) from exc

    return router


def _require_explicit_desktop_intent(request: Request) -> None:
    if request.headers.get(_DESKTOP_INTENT_HEADER) != _DESKTOP_INTENT_VALUE:
        raise TypedApiError(
            403, "desktop_intent_required", "desktop intent is required"
        )
    origin = request.headers.get("origin")
    if origin is not None and not _is_trusted_loopback_origin(origin):
        raise TypedApiError(
            403, "origin_not_allowed", "origin is not a trusted loopback origin"
        )


def _is_trusted_loopback_origin(origin: str) -> bool:
    parsed = urlsplit(origin)
    return (
        parsed.scheme == "http"
        and parsed.hostname in _LOOPBACK_ORIGIN_HOSTS
        and not parsed.username
        and not parsed.password
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )


def _response(selection: DirectorySelection) -> DirectorySelectionResponse:
    if not selection.selected:
        return CancelledDirectoryResponse(status="cancelled")
    if selection.path is None:
        raise DirectoryPickerError("selected directory is absent")
    return SelectedDirectoryResponse(
        status="selected",
        root_path=str(selection.path),
    )
