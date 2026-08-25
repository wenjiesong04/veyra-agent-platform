"""Health route for the Community service."""

from __future__ import annotations

from fastapi import APIRouter


def build_router(service_name: str) -> APIRouter:
    """Build the small system router for the Community service."""

    router = APIRouter()

    @router.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": service_name}

    return router
