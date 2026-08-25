"""Composition root for the separate Community service."""

from __future__ import annotations

from fastapi import FastAPI

from .api.health import build_router
from .config import CommunitySettings


def create_app(settings: CommunitySettings | None = None) -> FastAPI:
    """Create the Community application without starting a server."""

    resolved_settings = settings or CommunitySettings()
    application = FastAPI(
        title="Veyra Agent Platform Community",
        version="0.1.0",
    )
    application.state.settings = resolved_settings

    application.include_router(build_router(resolved_settings.service_name))

    return application


app = create_app()


def main() -> None:
    """Run the Community service through the installed ASGI server."""

    import uvicorn

    settings = CommunitySettings()
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )
