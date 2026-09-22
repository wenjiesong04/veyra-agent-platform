"""Composition root for the local desktop service."""

from __future__ import annotations

import sys
import tempfile
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI

from .agent_imports import AgentImportService
from .api.agent_imports import build_router as build_agent_import_router
from .api.artifacts import build_router as build_artifacts_router
from .api.factory import build_router as build_factory_router
from .api.factory.builder_routes import build_router as build_builder_router
from .api.factory.edit_routes import build_router as build_edit_proposals_router
from .api.health import build_router
from .api.mcp import build_router as build_mcp_router
from .api.orchestrator import build_router as build_orchestrator_router
from .api.plugins import build_router as build_plugins_router
from .api.projects import TypedApiError, typed_error_response
from .api.projects import build_router as build_projects_router
from .api.resources import build_router as build_resources_router
from .api.runtime import build_router as build_runtime_router
from .api.secrets import build_router as build_secrets_router
from .api.system import build_router as build_system_router
from .api.trash import build_router as build_trash_router
from .api.workflows import build_router as build_workflow_router
from .artifacts import ArtifactService
from .builder.conversation_service import BuilderConversationService
from .builder.conversation_store import BuilderConversationStore
from .builder.resolution import BuilderResolutionService
from .config import LocalSettings
from .factory import FactoryService, FactorySettings, KimiClient
from .factory.client import KimiTransport
from .factory.edit_service import EditProposalService
from .factory.edit_store import EditProposalStore
from .factory.store import FactorySessionRepository
from .host_env import load_host_process_env
from .library import LibraryService
from .mcp import McpServerStore, McpService
from .mcp.transport import TransportFactory
from .orchestrator import OrchestratorService, OrchestratorStore
from .plugins import PluginService
from .projects import ProjectService
from .projects.custom_components import CustomComponentService
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
from .trash import TrashService


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
        application.state.artifacts = ArtifactService(repository, object_root)
        application.state.agent_imports = AgentImportService(
            database_path.parent / "agent-imports", projects, catalog
        )
        custom_components = CustomComponentService(projects, catalog)
        application.state.custom_components = custom_components
        application.state.project_resources = ProjectResourceService(
            projects, catalog, custom_components
        )
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
            project_resources=application.state.project_resources,
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
        workshop = ResourceWorkshop(overlay_root, catalog)
        application.state.workshop = workshop
        application.state.plugins = PluginService(
            database_path.parent / "plugins", catalog, workshop, mcp
        )
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
            project_resources=application.state.project_resources,
            artifacts=application.state.artifacts,
            custom_components=custom_components,
        )
        application.state.workflow_runtime = WorkflowRuntimeService(
            application.state.runtime
        )
        application.state.resource_readiness = (
            application.state.runtime.resource_readiness
        )
        application.state.edit_proposals = EditProposalService(
            EditProposalStore(repository),
            application.state.library,
            catalog,
            application.state.factory.client,
            project_resources=application.state.project_resources,
            resource_readiness=application.state.resource_readiness,
            custom_components=custom_components,
        )
        application.state.builder = BuilderResolutionService(
            application.state.edit_proposals
        )
        application.state.builder_conversations = BuilderConversationService(
            BuilderConversationStore(repository),
            projects,
            application.state.builder,
            application.state.factory,
            runtime=application.state.runtime,
            edits=application.state.edit_proposals,
        )
        application.state.trash = TrashService(
            projects,
            application.state.plugins,
            application.state.builder_conversations,
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
    application.include_router(build_artifacts_router())
    application.include_router(build_agent_import_router())
    application.include_router(build_system_router(resolved_directory_picker))
    application.include_router(build_runtime_router())
    application.include_router(build_workflow_router())
    application.include_router(build_factory_router())
    application.include_router(build_edit_proposals_router())
    application.include_router(build_builder_router())
    application.include_router(build_resources_router())
    application.include_router(build_secrets_router())
    application.include_router(build_mcp_router())
    application.include_router(build_plugins_router())
    application.include_router(build_trash_router())
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
