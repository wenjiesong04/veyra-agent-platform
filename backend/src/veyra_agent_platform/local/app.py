"""Composition root for the local desktop service."""

from __future__ import annotations

from fastapi import FastAPI

from .api.health import build_router
from .config import LocalSettings


def create_app(settings: LocalSettings | None = None) -> FastAPI:
    """Create the local service application without starting a server."""

    resolved_settings = settings or LocalSettings()
    application = FastAPI(
        title="Veyra Agent Platform Local",
        version="0.1.0",
    )
    application.state.settings = resolved_settings

    application.include_router(build_router(resolved_settings.service_name))

    return application


app = create_app()


def main() -> None:
    """Run the local service through the installed ASGI server."""

    import uvicorn

    settings = LocalSettings()
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )
