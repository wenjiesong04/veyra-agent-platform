"""Natural-language entry to the shared Builder Harness; no write authority."""

from typing import Any, cast

from fastapi import APIRouter, Request

from veyra_agent_platform.local.api.projects import TypedApiError
from veyra_agent_platform.local.builder.resolution import (
    BuilderResolutionService,
    ResolveRequest,
)

from .routes import _translate


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

    return router
