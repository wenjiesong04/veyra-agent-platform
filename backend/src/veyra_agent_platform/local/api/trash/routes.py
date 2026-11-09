"""List, restore, and permanently delete recoverable local trash items."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, TypeVar, cast

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, StrictBool

from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.local.api.projects import TypedApiError
from veyra_agent_platform.local.builder.conversation_service import (
    BuilderConversationError,
)
from veyra_agent_platform.local.plugins import PluginError, PluginPackError
from veyra_agent_platform.local.projects.service import ProjectError
from veyra_agent_platform.local.trash import TRASH_KINDS, TrashService

_Result = TypeVar("_Result")
TrashKind = Literal[
    "project", "agent", "workflow", "knowledge", "conversation", "plugin"
]


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TrashConfirmRequest(_ClosedModel):
    confirm: StrictBool


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/trash", tags=["trash"])

    @router.get("")
    def list_trash(request: Request) -> dict[str, Any]:
        return _translate(lambda: _trash(request).list_items())

    @router.post("/{kind}/{item_id}/restore")
    def restore_trash(
        kind: TrashKind,
        item_id: str,
        payload: TrashConfirmRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _translate(
            lambda: _trash(request).restore(kind, item_id, confirm=payload.confirm)
        )

    @router.post("/{kind}/{item_id}/purge")
    def purge_trash(
        kind: TrashKind,
        item_id: str,
        payload: TrashConfirmRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _translate(
            lambda: _trash(request).purge(kind, item_id, confirm=payload.confirm)
        )

    return router


def _trash(request: Request) -> TrashService:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return cast(TrashService, request.app.state.trash)


def _translate(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except BuilderConversationError as exc:
        raise TypedApiError(exc.status_code, exc.code, str(exc)) from exc
    except PluginPackError as exc:
        raise TypedApiError(422, exc.code, str(exc)) from exc
    except PluginError as exc:
        status_code = 404 if exc.code == "plugin_not_found" else 422
        raise TypedApiError(status_code, exc.code, str(exc)) from exc
    except ProjectError as exc:
        status_code = (
            404
            if exc.code == "trash_not_found"
            else 409
            if exc.code == "trash_conflict"
            else 422
        )
        raise TypedApiError(status_code, exc.code, str(exc)) from exc
    except ContractValidationError as exc:
        raise TypedApiError(422, "project_invalid", str(exc)) from exc
    except TypedApiError:
        raise
    except Exception as exc:
        raise TypedApiError(
            500,
            "local_internal_error",
            str(exc) or "local service failed",
        ) from exc


# Keep the closed kind set aligned with the service.
assert set(TRASH_KINDS) == {
    "project",
    "agent",
    "workflow",
    "knowledge",
    "conversation",
    "plugin",
}
