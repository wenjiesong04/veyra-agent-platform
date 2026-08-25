"""Health route for the local service."""

from __future__ import annotations

from fastapi import APIRouter


def build_router(service_name: str) -> APIRouter:
    """Build the small system router for the local service."""

    router = APIRouter()

    @router.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": service_name}

    return router
