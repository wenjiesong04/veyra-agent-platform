"""Authenticated account-profile behavior."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from ..storage.database import CommunityDatabase
from ..storage.identifiers import utc_now
from ..storage.schema import CommunityUser
from ..storage.user_repository import CommunityUserRepository
from .identifiers import normalize_display_name, normalize_handle


class ProfileUnavailableError(ValueError):
    """Raised when a requested public handle is unavailable."""


@dataclass(frozen=True)
class AccountProfile:
    """Private account projection returned only to the authenticated user."""

    id: str
    email: str
    handle: str
    display_name: str | None


class AccountProfileService:
    """Load and update an authenticated user's profile through its repository."""

    def __init__(self, database: CommunityDatabase) -> None:
        self._database = database
        self._users = CommunityUserRepository()

    def get(self, user_id: str) -> AccountProfile | None:
        with self._database.transaction() as session:
            user = self._users.find_by_id(session, user_id)
            return _to_profile(user) if user is not None else None

    def update(
        self,
        user_id: str,
        *,
        handle: str | None,
        display_name: str | None,
    ) -> AccountProfile | None:
        normalized_handle = normalize_handle(handle) if handle is not None else None
        normalized_display_name = (
            normalize_display_name(display_name) if display_name is not None else None
        )
        with self._database.transaction() as session:
            user = self._users.find_by_id(session, user_id)
            if user is None:
                return None
            if normalized_handle is not None and normalized_handle != user.handle:
                existing = self._users.find_by_handle(session, normalized_handle)
                if existing is not None and existing.id != user.id:
                    raise ProfileUnavailableError("requested handle is unavailable")
            try:
                updated = self._users.update_profile(
                    session,
                    user,
                    handle=normalized_handle,
                    display_name=normalized_display_name,
                    now=utc_now(),
                )
            except IntegrityError as error:
                raise ProfileUnavailableError(
                    "requested handle is unavailable"
                ) from error
            return _to_profile(updated)


def _to_profile(user: CommunityUser) -> AccountProfile:
    return AccountProfile(
        id=user.id,
        email=user.email_normalized,
        handle=user.handle,
        display_name=user.display_name,
    )
