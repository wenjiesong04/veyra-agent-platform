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
    host_type: Literal["community", "cloud"] | None = None
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
    host_type: Literal["community", "cloud"] | None = None
    app_version: str
    build_sha: str
    database_revision: str | None = None
    database_ready: bool = False
    object_storage_ready: bool = False
    credential_cipher_ready: bool = True


class _ReadinessStorage(Protocol):
    def check_ready(self) -> bool: ...


def _object_storage_ready(request: Request) -> bool:
    """Check both Community object-storage boundaries and fail closed."""

    try:
        package_storage = cast(_ReadinessStorage, request.app.state.package_storage)
        avatar_storage = cast(_ReadinessStorage, request.app.state.avatar_storage)
        stores = [package_storage, avatar_storage]
        cloud_file_store = getattr(request.app.state, "cloud_file_store", None)
        if cloud_file_store is not None:
            stores.append(cast(_ReadinessStorage, cloud_file_store))
        return all(store.check_ready() for store in stores)
    except Exception:
        return False


def build_router(
    service_name: str,
    app_version: str,
    build_sha: str,
    *,
    host_type: Literal["community", "cloud"] | None = None,
) -> APIRouter:
    """Build the small system router for the Community service."""

    router = APIRouter()

    @router.get(
        "/api/v1/health",
        response_model=HealthResponse,
        tags=["system"],
    )
    def health(request: Request) -> JSONResponse:
        ready = bool(getattr(request.app.state, "database_ready", False))
        payload = HealthResponse(
            status="ok" if ready else "starting",
            service=service_name,
            host_type=host_type,
            app_version=app_version,
            build_sha=build_sha,
            database_revision=getattr(request.app.state, "database_revision", None),
            database_ready=ready,
        ).model_dump()
        if host_type is None:
            payload.pop("host_type", None)
        return JSONResponse(
            status_code=200,
            content=payload,
        )

    @router.get(
        "/api/v1/ready",
        response_model=ReadinessResponse,
        tags=["system"],
    )
    def ready(request: Request) -> JSONResponse:
        database_ready = bool(getattr(request.app.state, "database_ready", False))
        object_storage_ready = _object_storage_ready(request)
        credential_cipher_ready = bool(
            getattr(request.app.state, "credential_cipher_ready", True)
        )
        is_ready = database_ready and object_storage_ready and credential_cipher_ready
        readiness = ReadinessResponse(
            status="ready" if is_ready else "starting",
            ready=is_ready,
            service=service_name,
            host_type=host_type,
            app_version=app_version,
            build_sha=build_sha,
            database_revision=getattr(request.app.state, "database_revision", None),
            database_ready=database_ready,
            object_storage_ready=object_storage_ready,
            credential_cipher_ready=credential_cipher_ready,
        )
        payload = readiness.model_dump()
        if host_type is None:
            payload.pop("host_type", None)
            payload.pop("credential_cipher_ready", None)
        return JSONResponse(
            status_code=200 if is_ready else 503,
            content=payload,
        )

    return router
