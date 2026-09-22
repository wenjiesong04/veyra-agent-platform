"""Natural-language Builder resolution and durable Project conversations."""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Callable, Iterator
from typing import Any, cast

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.local.api.projects import TypedApiError
from veyra_agent_platform.local.builder.conversation_service import (
    BUILDER_ACTIVITY_MAX,
    BuilderConversationError,
    BuilderConversationService,
    ComponentProposalCommandRequest,
    RecordRequest,
    RenameRequest,
    TestRepairRequest,
    TestRunCommandRequest,
    TestRunRequest,
    TurnRequest,
)
from veyra_agent_platform.local.builder.resolution import (
    BuilderResolutionService,
    ResolveRequest,
)
from veyra_agent_platform.local.factory.client import FactoryProviderError
from veyra_agent_platform.local.factory.service import FactoryError
from veyra_agent_platform.local.library.service import DraftConflict
from veyra_agent_platform.local.projects.service import ProjectError

from .routes import _translate

_PROVIDER_UNAVAILABLE = {
    "factory_provider_not_configured",
    "factory_unavailable",
    "factory_timeout",
}


def build_router() -> APIRouter:
    router = APIRouter(tags=["builder"])

    @router.post("/api/v1/projects/{project_id}/builder/resolve")
    def resolve(
        project_id: str, payload: ResolveRequest, request: Request
    ) -> dict[str, Any]:
        if not bool(getattr(request.app.state, "database_ready", False)):
            raise TypedApiError(
                503, "database_unavailable", "local database is starting"
            )
        service = cast(BuilderResolutionService, request.app.state.builder)
        return _translate(lambda: service.resolve(project_id, payload))

    @router.post("/api/v1/projects/{project_id}/builder/turns")
    def turn(project_id: str, payload: TurnRequest, request: Request) -> Any:
        accept = (request.headers.get("accept") or "").casefold()
        if "text/event-stream" in accept:
            return _turn_stream(request, project_id, payload)
        return _conversation_translate(
            request, lambda: _conversations(request).turn(project_id, payload)
        )

    @router.get("/api/v1/projects/{project_id}/builder/conversations/{conversation_id}")
    def get_conversation(
        project_id: str, conversation_id: str, request: Request
    ) -> dict[str, Any]:
        return _conversation_translate(
            request, lambda: _conversations(request).get(project_id, conversation_id)
        )

    @router.patch(
        "/api/v1/projects/{project_id}/builder/conversations/{conversation_id}"
    )
    def rename_conversation(
        project_id: str,
        conversation_id: str,
        payload: RenameRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _conversation_translate(
            request,
            lambda: _conversations(request).rename(
                project_id, conversation_id, payload
            ),
        )

    @router.delete(
        "/api/v1/projects/{project_id}/builder/conversations/{conversation_id}"
    )
    def delete_conversation(
        project_id: str, conversation_id: str, request: Request
    ) -> dict[str, Any]:
        return _conversation_translate(
            request,
            lambda: _conversations(request).delete(project_id, conversation_id),
        )

    @router.post(
        "/api/v1/projects/{project_id}/builder/conversations/{conversation_id}/records"
    )
    def record(
        project_id: str,
        conversation_id: str,
        payload: RecordRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _conversation_translate(
            request,
            lambda: _conversations(request).record(
                project_id, conversation_id, payload
            ),
        )

    @router.get("/api/v1/projects/{project_id}/builder/activity")
    def activity(
        project_id: str,
        request: Request,
        limit: int | None = Query(default=None, ge=1, le=BUILDER_ACTIVITY_MAX),
    ) -> dict[str, Any]:
        return _conversation_translate(
            request, lambda: _conversations(request).activity(project_id, limit=limit)
        )

    @router.get("/api/v1/builder/activity")
    def workspace_activity(
        request: Request,
        limit: int | None = Query(default=None, ge=1, le=BUILDER_ACTIVITY_MAX),
    ) -> dict[str, Any]:
        return _conversation_translate(
            request, lambda: _conversations(request).activity(limit=limit)
        )

    @router.get(
        "/api/v1/projects/{project_id}/builder/conversations/{conversation_id}"
        "/operations/{operation_id}/receipts"
    )
    def operation_receipts(
        project_id: str,
        conversation_id: str,
        operation_id: str,
        request: Request,
    ) -> dict[str, Any]:
        return _conversation_translate(
            request,
            lambda: _conversations(request).receipts(
                project_id, conversation_id, operation_id
            ),
        )

    @router.post(
        "/api/v1/projects/{project_id}/builder/conversations/{conversation_id}/test-runs"
    )
    def start_test_run(
        project_id: str,
        conversation_id: str,
        payload: TestRunRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _conversation_translate(
            request,
            lambda: _conversations(request).start_test_run(
                project_id, conversation_id, payload
            ),
        )

    @router.post(
        "/api/v1/projects/{project_id}/builder/conversations/{conversation_id}"
        "/operations/{operation_id}/test-commands"
    )
    def command_test_run(
        project_id: str,
        conversation_id: str,
        operation_id: str,
        payload: TestRunCommandRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _conversation_translate(
            request,
            lambda: _conversations(request).command_test_run(
                project_id, conversation_id, operation_id, payload
            ),
        )

    @router.post(
        "/api/v1/projects/{project_id}/builder/conversations/{conversation_id}"
        "/operations/{operation_id}/component-proposals/{proposal_id}/commands"
    )
    def command_component_proposal(
        project_id: str,
        conversation_id: str,
        operation_id: str,
        proposal_id: str,
        payload: ComponentProposalCommandRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _conversation_translate(
            request,
            lambda: _conversations(request).command_component_proposal(
                project_id,
                conversation_id,
                operation_id,
                proposal_id,
                payload.command,
                confirm=payload.confirm,
                locale=payload.locale,
            ),
        )

    @router.post(
        "/api/v1/projects/{project_id}/builder/conversations/{conversation_id}"
        "/operations/{operation_id}/test-repair"
    )
    def propose_test_repair(
        project_id: str,
        conversation_id: str,
        operation_id: str,
        payload: TestRepairRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _conversation_translate(
            request,
            lambda: _conversations(request).propose_test_repair(
                project_id, conversation_id, operation_id, payload
            ),
        )

    return router


def _conversations(request: Request) -> BuilderConversationService:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return cast(BuilderConversationService, request.app.state.builder_conversations)


def _conversation_translate(
    request: Request, operation: Callable[[], dict[str, Any]]
) -> dict[str, Any]:
    _ = request
    try:
        return operation()
    except BuilderConversationError as exc:
        raise TypedApiError(exc.status_code, exc.code, str(exc)) from exc
    except FactoryProviderError as exc:
        status_code = 503 if exc.code in _PROVIDER_UNAVAILABLE else 502
        raise TypedApiError(
            status_code, exc.code, str(exc), details=exc.details or None
        ) from exc
    except FactoryError as exc:
        raise TypedApiError(422, exc.code, str(exc)) from exc
    except DraftConflict as exc:
        raise TypedApiError(409, "draft_conflict", str(exc)) from exc
    except ProjectError as exc:
        raise TypedApiError(422, exc.code, str(exc)) from exc
    except ContractValidationError as exc:
        raise TypedApiError(422, "contract_invalid", str(exc)) from exc
    except TypedApiError:
        raise


def _turn_stream(
    request: Request, project_id: str, payload: TurnRequest
) -> StreamingResponse:
    outgoing: queue.Queue[tuple[str, Any] | None] = queue.Queue()

    def emit(event: dict[str, Any]) -> None:
        outgoing.put(("event", event))

    def worker() -> None:
        try:
            snapshot = _conversations(request).turn(project_id, payload, on_event=emit)
            outgoing.put(("snapshot", snapshot))
        except Exception as exc:
            outgoing.put(("error", exc))
        finally:
            outgoing.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def frames() -> Iterator[str]:
        while True:
            item = outgoing.get()
            if item is None:
                break
            kind, data = item
            if kind == "event":
                yield _sse_frame("builder.event", data, str(data.get("event_id") or ""))
            elif kind == "snapshot":
                yield _sse_frame("builder.snapshot", data)
            else:
                yield _sse_frame("builder.error", _stream_error(data))

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _stream_error(exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, BuilderConversationError):
        return {"code": exc.code, "message": str(exc), "status": exc.status_code}
    if isinstance(exc, FactoryProviderError):
        status_code = 503 if exc.code in _PROVIDER_UNAVAILABLE else 502
        return {
            "code": exc.code,
            "message": str(exc),
            "status": status_code,
            "details": exc.details or {},
        }
    if isinstance(exc, FactoryError):
        return {"code": exc.code, "message": str(exc), "status": 422}
    if isinstance(exc, DraftConflict):
        return {"code": "draft_conflict", "message": str(exc), "status": 409}
    if isinstance(exc, ProjectError):
        return {"code": exc.code, "message": str(exc), "status": 422}
    if isinstance(exc, ContractValidationError):
        return {"code": "contract_invalid", "message": str(exc), "status": 422}
    if isinstance(exc, TypedApiError):
        return {
            "code": getattr(exc, "code", "http_error"),
            "message": str(exc),
            "status": getattr(exc, "status_code", 500),
        }
    return {
        "code": "builder_operation_failed",
        "message": "Builder could not finish this operation.",
        "status": 500,
    }


def _sse_frame(event: str, data: dict[str, Any], event_id: str = "") -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {payload}")
    return "\n".join(lines) + "\n\n"
