"""Timezone-aware UTC persistence that remains correct on SQLite and PostgreSQL."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """Require aware datetimes and restore UTC tzinfo when SQLite strips it."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, _dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Community timestamps must be timezone-aware UTC")
        return value.astimezone(UTC)

    def process_result_value(
        self, value: datetime | None, _dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        return (
            value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        )
