"""Health route for the Community service."""

from __future__ import annotations

from typing import Literal, Protocol, cast

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict
from starlette.responses import JSONResponse


class HealthResponse(BaseModel):
    """Stable liveness response shared by the Community route only."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["health.v1"] = "health.v1"
    status: Literal["ok", "starting"] = "ok"
    service: str
    app_version: str
    build_sha: str
    database_revision: str | None = None
    database_ready: bool = False


class ReadinessResponse(BaseModel):
    """Dependency readiness response used by deployment health checks."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["readiness.v1"] = "readiness.v1"
    status: Literal["ready", "starting"] = "starting"
    ready: bool = False
    service: str
    app_version: str
    build_sha: str
    database_revision: str | None = None
    database_ready: bool = False
    object_storage_ready: bool = False


class _ReadinessStorage(Protocol):
    def check_ready(self) -> bool: ...


def _object_storage_ready(request: Request) -> bool:
    """Check both Community object-storage boundaries and fail closed."""

    try:
        package_storage = cast(_ReadinessStorage, request.app.state.package_storage)
        avatar_storage = cast(_ReadinessStorage, request.app.state.avatar_storage)
        return package_storage.check_ready() and avatar_storage.check_ready()
    except Exception:
        return False


def build_router(service_name: str, app_version: str, build_sha: str) -> APIRouter:
    """Build the small system router for the Community service."""

    router = APIRouter()

    @router.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
    def health(request: Request) -> HealthResponse:
        ready = bool(getattr(request.app.state, "database_ready", False))
        return HealthResponse(
            status="ok" if ready else "starting",
            service=service_name,
            app_version=app_version,
            build_sha=build_sha,
            database_revision=getattr(request.app.state, "database_revision", None),
            database_ready=ready,
        )

    @router.get("/api/v1/ready", response_model=ReadinessResponse, tags=["system"])
    def ready(request: Request) -> JSONResponse:
        database_ready = bool(getattr(request.app.state, "database_ready", False))
        object_storage_ready = _object_storage_ready(request)
        is_ready = database_ready and object_storage_ready
        payload = ReadinessResponse(
            status="ready" if is_ready else "starting",
            ready=is_ready,
            service=service_name,
            app_version=app_version,
            build_sha=build_sha,
            database_revision=getattr(request.app.state, "database_revision", None),
            database_ready=database_ready,
            object_storage_ready=object_storage_ready,
        )
        return JSONResponse(
            status_code=200 if is_ready else 503,
            content=payload.model_dump(),
        )

    return router
