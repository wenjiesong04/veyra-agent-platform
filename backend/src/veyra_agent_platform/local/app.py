"""Composition root for the local desktop service."""

from __future__ import annotations

import sys
import tempfile
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI

from .api.factory import build_router as build_factory_router
from .api.health import build_router
from .api.mcp import build_router as build_mcp_router
from .api.orchestrator import build_router as build_orchestrator_router
from .api.projects import TypedApiError, typed_error_response
from .api.projects import build_router as build_projects_router
from .api.resources import build_router as build_resources_router
from .api.runtime import build_router as build_runtime_router
from .api.secrets import build_router as build_secrets_router
from .api.system import build_router as build_system_router
from .api.workflows import build_router as build_workflow_router
from .config import LocalSettings
from .factory import FactoryService, FactorySettings, KimiClient
from .factory.client import KimiTransport
from .factory.store import FactorySessionRepository
from .host_env import load_host_process_env
from .library import LibraryService
from .mcp import McpServerStore, McpService
from .mcp.transport import TransportFactory
from .orchestrator import OrchestratorService, OrchestratorStore
from .projects import ProjectService
from .resources import ResourceCatalog, ResourceWorkshop
from .resources.project import ProjectResourceService
from .runtime import (
    RuntimeModelClient,
    RuntimeProfileStore,
    RuntimeService,
    RuntimeSettings,
    ToolAdapter,
    ToolRuntime,
)
from .runtime.client import RuntimeModelTransport
from .runtime.conversations import AgentConversationService
from .runtime.workflow_service import WorkflowRuntimeService
from .secrets import MacOSKeychainSecretStore, SecretStore
from .storage import LocalRepository, migrate_local_database
from .storage.bootstrap import HEAD_REVISION
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
    factory_transport: KimiTransport | None = None,
    factory_settings: FactorySettings | None = None,
    runtime_transport: RuntimeModelTransport | None = None,
    runtime_settings: RuntimeSettings | None = None,
    mcp_transport_factory: TransportFactory | None = None,
    mcp_http_client: httpx.Client | None = None,
    tool_adapters: Mapping[str, ToolAdapter] | None = None,
    secret_store: SecretStore | None = None,
) -> FastAPI:
    """Create the local service application without starting a server."""

    resolved_settings = settings or LocalSettings()
    resolved_directory_picker = directory_picker or MacOSDirectoryPicker()
    resolved_factory_settings = factory_settings or FactorySettings()
    host_key_allowed = resolved_settings.mode not in {"production", "release"}
    resolved_runtime_settings = runtime_settings or RuntimeSettings(
        allow_process_environment_key=host_key_allowed
    )
    if not host_key_allowed and resolved_runtime_settings.allow_process_environment_key:
        resolved_runtime_settings = resolved_runtime_settings.model_copy(
            update={"allow_process_environment_key": False}
        )
    database_path = _sqlite_database_path(resolved_settings.database_url)
    overlay_root = database_path.parent / "overlays"
    catalog = ResourceCatalog(overlay_root=overlay_root)
    resolved_secret_store = secret_store or MacOSKeychainSecretStore()
    runtime_client = RuntimeModelClient(
        resolved_runtime_settings,
        runtime_transport,
        secret_store=resolved_secret_store,
    )

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
        application.state.project_resources = ProjectResourceService(projects, catalog)
        application.state.library = LibraryService(repository, projects, catalog)
        application.state.conversations = AgentConversationService(
            repository, application.state.library
        )
        runtime_profiles = RuntimeProfileStore(repository)
        application.state.runtime_profiles = runtime_profiles
        application.state.factory = FactoryService(
            FactorySessionRepository(database_path),
            projects,
            catalog,
            KimiClient(
                resolved_factory_settings,
                factory_transport,
                secret_store=resolved_secret_store,
            ),
        )
        mcp = McpService(
            McpServerStore(database_path),
            overlay_root,
            catalog,
            mcp_transport_factory,
            secret_store=application.state.secrets,
            http_client=mcp_http_client,
        )
        application.state.mcp = mcp
        application.state.workshop = ResourceWorkshop(overlay_root, catalog)
        application.state.runtime = RuntimeService(
            repository,
            projects,
            application.state.library,
            runtime_client,
            ToolRuntime(
                catalog,
                mcp=mcp,
                adapters=tool_adapters,
                secret_store=application.state.secrets,
            ),
            runtime_profiles,
            application.state.conversations,
        )
        application.state.workflow_runtime = WorkflowRuntimeService(
            application.state.runtime
        )
        application.state.orchestrator = OrchestratorService(
            OrchestratorStore(database_path),
            projects,
            application.state.runtime,
        )
        application.state.database_revision = HEAD_REVISION
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
    application.state.resource_catalog = catalog
    application.state.secrets = resolved_secret_store
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
    application.include_router(build_workflow_router())
    application.include_router(build_factory_router())
    application.include_router(build_resources_router())
    application.include_router(build_secrets_router())
    application.include_router(build_mcp_router())
    application.include_router(build_orchestrator_router())

    return application


# Factory construction only defines routes and a lifespan; it performs no
# filesystem or database work until the ASGI server enters that lifespan.
if "pytest" not in sys.modules:
    load_host_process_env()
app = create_app()


def main() -> None:
    """Run the local service through the installed ASGI server."""

    import uvicorn

    load_host_process_env()
    settings = LocalSettings()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
