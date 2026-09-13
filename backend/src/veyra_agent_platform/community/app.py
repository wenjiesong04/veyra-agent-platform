"""Composition root for the separate Community service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from .accounts.avatars import AccountAvatarService
from .accounts.profiles import AccountProfileService
from .api.account.routes import (
    build_avatar_router,
)
from .api.account.routes import (
    build_router as build_account_router,
)
from .api.auth.routes import build_router as build_auth_router
from .api.health import build_router
from .api.registry import build_router as build_registry_router
from .api.registry.plugin_routes import build_router as build_plugin_registry_router
from .auth.workflows import CommunityAuthWorkflows
from .config import CommunitySettings
from .mail.config import MailSettings
from .mail.outbox import MailOutboxDispatcher
from .mail.provider import MailProvider
from .mail.smtp import QQSmtpMailProvider
from .registry import CommunityPluginRegistryService, CommunityRegistryService
from .storage.avatar_storage import AvatarStorage, LocalAvatarStorage
from .storage.database import CommunityDatabase
from .storage.package_storage import LocalPackageStorage, PackageStorage
from .storage.s3_storage import (
    S3AvatarStorage,
    S3PackageStorage,
    S3StorageConfig,
)

COMMUNITY_DATABASE_HEAD = "community_0008_plugin_registry"


def _database_revision(database: CommunityDatabase) -> str | None:
    """Read the single Alembic revision without modifying database state."""

    try:
        with database.engine.connect() as connection:
            if not inspect(connection).has_table("alembic_version"):
                return None
            revisions = tuple(
                connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalars()
            )
    except SQLAlchemyError:
        return None
    if len(revisions) != 1:
        return None
    revision = revisions[0]
    return revision if isinstance(revision, str) else None


def _s3_config(settings: CommunitySettings, *, prefix: str) -> S3StorageConfig:
    config = S3StorageConfig(
        endpoint_url=settings.s3_endpoint_url or "",
        bucket=settings.s3_bucket or "",
        region=settings.s3_region,
        access_key_id=(
            settings.s3_access_key_id.get_secret_value()
            if settings.s3_access_key_id
            else ""
        ),
        secret_access_key=(
            settings.s3_secret_access_key.get_secret_value()
            if settings.s3_secret_access_key
            else ""
        ),
        key_prefix=prefix,
    )
    return config


def _package_storage(settings: CommunitySettings) -> PackageStorage:
    if settings.object_storage_backend == "local":
        return LocalPackageStorage(settings.registry_storage_root)
    return S3PackageStorage(_s3_config(settings, prefix="packages"))


def _avatar_storage(settings: CommunitySettings) -> AvatarStorage:
    if settings.object_storage_backend == "local":
        return LocalAvatarStorage(settings.avatar_storage_root)
    return S3AvatarStorage(_s3_config(settings, prefix="avatars"))


def create_app(
    settings: CommunitySettings | None = None,
    *,
    database: CommunityDatabase | None = None,
    mail_provider: MailProvider | None = None,
) -> FastAPI:
    """Create the Community application without starting a server."""

    resolved_settings = settings or CommunitySettings()
    resolved_database = database or CommunityDatabase(resolved_settings.database_url)
    resolved_mail_provider = mail_provider or QQSmtpMailProvider(MailSettings())
    mail_dispatcher = MailOutboxDispatcher(resolved_database, resolved_mail_provider)
    auth_workflows = CommunityAuthWorkflows(
        resolved_database,
        auth_hmac_secret=resolved_settings.auth_hmac_secret.get_secret_value(),
        mail_dispatcher=mail_dispatcher,
        session_ttl=timedelta(minutes=resolved_settings.session_ttl_minutes),
        refresh_ttl=timedelta(days=resolved_settings.refresh_ttl_days),
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        revision = _database_revision(resolved_database)
        application.state.database_revision = revision
        application.state.database_ready = revision == COMMUNITY_DATABASE_HEAD
        try:
            yield
        finally:
            application.state.database_ready = False

    application = FastAPI(
        title="Veyra Agent Platform Community",
        version=resolved_settings.app_version,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.community_database = resolved_database
    application.state.auth_workflows = auth_workflows
    application.state.account_profiles = AccountProfileService(resolved_database)
    application.state.account_avatars = AccountAvatarService(
        resolved_database,
        _avatar_storage(resolved_settings),
    )
    application.state.community_registry = CommunityRegistryService(
        resolved_database,
        _package_storage(resolved_settings),
        application.state.account_profiles,
        require_moderation=resolved_settings.require_moderation,
    )
    application.state.community_plugin_registry = CommunityPluginRegistryService(
        resolved_database,
        _package_storage(resolved_settings),
        application.state.account_profiles,
        require_moderation=resolved_settings.require_moderation,
    )
    application.state.database_revision = None
    application.state.database_ready = False

    application.include_router(
        build_router(
            service_name=resolved_settings.service_name,
            app_version=resolved_settings.app_version,
            build_sha=resolved_settings.build_sha,
        )
    )
    application.include_router(build_auth_router())
    application.include_router(build_account_router())
    application.include_router(build_avatar_router())
    application.include_router(build_registry_router())
    application.include_router(build_plugin_registry_router())

    return application


app = create_app()


def main() -> None:
    """Run the Community service through the installed ASGI server."""

    import uvicorn

    settings = CommunitySettings()
    application = create_app(settings)
    uvicorn.run(
        application,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )
