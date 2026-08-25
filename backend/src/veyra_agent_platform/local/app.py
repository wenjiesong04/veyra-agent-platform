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
        version=resolved_settings.app_version,
    )
    application.state.settings = resolved_settings

    application.include_router(
        build_router(
            service_name=resolved_settings.service_name,
            app_version=resolved_settings.app_version,
            build_sha=resolved_settings.build_sha,
        )
    )

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
