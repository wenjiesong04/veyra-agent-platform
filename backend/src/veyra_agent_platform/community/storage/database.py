"""Synchronous SQLAlchemy engine and transaction factory for Community."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from sqlite3 import Connection as SqliteConnection

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .schema import CommunityBase


class CommunityDatabase:
    """Own a Community SQLAlchemy engine and explicit transactional sessions."""

    def __init__(self, database_url: str) -> None:
        self.engine = self._create_engine(database_url)
        self._session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )

    @staticmethod
    def _create_engine(database_url: str) -> Engine:
        parsed_url: URL = make_url(database_url)
        if parsed_url.get_backend_name() != "sqlite":
            return create_engine(database_url, future=True, pool_pre_ping=True)

        if parsed_url.database == ":memory:":
            engine = create_engine(
                database_url,
                connect_args={"check_same_thread": False},
                future=True,
                poolclass=StaticPool,
            )
        else:
            engine = create_engine(
                database_url,
                connect_args={"check_same_thread": False},
                future=True,
            )

        @event.listens_for(engine, "connect")
        def _configure_sqlite_connection(
            connection: SqliteConnection, _: object
        ) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        """Yield a session that commits atomically or rolls back on failure."""

        session = self._session_factory()
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()

    def create_schema_for_testing(self) -> None:
        """Create mapped tables for isolated test databases only."""

        CommunityBase.metadata.create_all(self.engine)

    def dispose(self) -> None:
        """Close pooled database resources."""

        self.engine.dispose()
