"""Health route for the local service."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Stable liveness response shared by the local route only."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["health.v1"] = "health.v1"
    status: Literal["ok"] = "ok"
    service: str
    app_version: str
    build_sha: str
    database_revision: str | None = None
    database_ready: bool = False


def build_router(service_name: str, app_version: str, build_sha: str) -> APIRouter:
    """Build the small system router for the local service."""

    router = APIRouter()

    @router.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(
            service=service_name,
            app_version=app_version,
            build_sha=build_sha,
        )

    return router
