"""SQLite repositories and content-addressed storage for the desktop app."""

from .bootstrap import migrate_local_database, require_schema_head
from .repositories import IdempotencyConflict, LocalRepository

__all__ = [
    "IdempotencyConflict",
    "LocalRepository",
    "migrate_local_database",
    "require_schema_head",
]
