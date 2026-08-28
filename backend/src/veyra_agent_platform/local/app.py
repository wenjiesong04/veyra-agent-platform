"""Composition root for the local desktop service."""

from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from .api.health import build_router
from .api.projects import (
    TypedApiError,
    typed_error_response,
)
from .api.projects import (
    build_router as build_projects_router,
)
from .api.runtime import build_router as build_runtime_router
from .api.system import build_router as build_system_router
from .config import LocalSettings
from .library import LibraryService
from .projects import ProjectService
from .runtime import RuntimeService
from .storage import LocalRepository, migrate_local_database
from .system import DirectoryPicker, MacOSDirectoryPicker


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
    if raw_path == ":memory:":
        return Path(tempfile.mkdtemp(prefix="veyra-local-db-")) / "app.sqlite3"
    return Path(raw_path)


def create_app(
    settings: LocalSettings | None = None,
    *,
    directory_picker: DirectoryPicker | None = None,
) -> FastAPI:
    """Create the local service application without starting a server."""

    resolved_settings = settings or LocalSettings()
    resolved_directory_picker = directory_picker or MacOSDirectoryPicker()
    database_path = _sqlite_database_path(resolved_settings.database_url)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        migrate_local_database(database_path)
        repository = LocalRepository(database_path)
        object_root = database_path.parent.parent / "objects"
        projects = ProjectService(
            repository,
            object_root,
            project_storage_root=resolved_settings.project_storage_root,
        )
        application.state.repository = repository
        application.state.projects = projects
        application.state.library = LibraryService(repository, projects)
        application.state.runtime = RuntimeService(
            repository, projects, application.state.library
        )
        application.state.database_revision = "local_0006_runtime_runs"
        application.state.database_ready = True
        try:
            yield
        finally:
            application.state.database_ready = False

    application = FastAPI(
        title="Veyra Agent Platform Local",
        version=resolved_settings.app_version,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.database_ready = False
    application.state.database_revision = None
    application.add_exception_handler(TypedApiError, typed_error_response)

    application.include_router(
        build_router(
            service_name=resolved_settings.service_name,
            app_version=resolved_settings.app_version,
            build_sha=resolved_settings.build_sha,
        )
    )
    application.include_router(build_projects_router())
    application.include_router(build_system_router(resolved_directory_picker))
    application.include_router(build_runtime_router())

    return application


# Factory construction only defines routes and a lifespan; it performs no
# filesystem or database work until the ASGI server enters that lifespan.
app = create_app()


def main() -> None:
    """Run the local service through the installed ASGI server."""

    import uvicorn

    settings = LocalSettings()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )
