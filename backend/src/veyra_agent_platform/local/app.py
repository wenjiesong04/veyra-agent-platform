"""Composition root for the local desktop service."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI

from .api.health import build_router
from .api.projects import build_router as build_projects_router
from .config import LocalSettings
from .library import LibraryService
from .projects import ProjectService
from .storage import LocalRepository


def _sqlite_database_path(database_url: str) -> Path:
    """Resolve only the local SQLite URLs supported by this desktop sidecar."""
    prefix = "sqlite+aiosqlite:///"
    plain_prefix = "sqlite:///"
    if database_url.startswith(prefix):
        raw_path = database_url.removeprefix(prefix)
    elif database_url.startswith(plain_prefix):
        raw_path = database_url.removeprefix(plain_prefix)
    else:
        raise ValueError("local Project persistence requires a SQLite database URL")
    return Path(raw_path)


def create_app(settings: LocalSettings | None = None) -> FastAPI:
    """Create the local service application without starting a server."""

    resolved_settings = settings or LocalSettings()
    application = FastAPI(
        title="Veyra Agent Platform Local",
        version=resolved_settings.app_version,
    )
    application.state.settings = resolved_settings
    database_path = _sqlite_database_path(resolved_settings.database_url)
    repository = LocalRepository(database_path)
    object_root = (
        database_path.parent.parent / "objects"
        if database_path != Path(":memory:")
        else Path(tempfile.mkdtemp(prefix="veyra-local-objects-"))
    )
    projects = ProjectService(repository, object_root)
    application.state.repository = repository
    application.state.projects = projects
    application.state.library = LibraryService(repository, projects)

    application.include_router(
        build_router(
            service_name=resolved_settings.service_name,
            app_version=resolved_settings.app_version,
            build_sha=resolved_settings.build_sha,
        )
    )
    application.include_router(
        build_projects_router(projects, application.state.library)
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
