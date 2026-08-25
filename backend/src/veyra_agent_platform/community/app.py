"""Composition root for the separate Community service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from .accounts.profiles import AccountProfileService
from .api.account.routes import build_router as build_account_router
from .api.auth.routes import build_router as build_auth_router
from .api.health import build_router
from .auth.workflows import CommunityAuthWorkflows
from .config import CommunitySettings
from .mail.config import MailSettings
from .mail.outbox import MailOutboxDispatcher
from .mail.provider import MailProvider
from .mail.smtp import QQSmtpMailProvider
from .storage.database import CommunityDatabase

COMMUNITY_DATABASE_HEAD = "community_0002_accounts_auth_mail"


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
    return revisions[0]


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
