"""Health route for the Community service."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict


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

    return router
