"""Authenticated account-profile behavior."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from ..storage.database import CommunityDatabase
from ..storage.identifiers import utc_now
from ..storage.schema import CommunityAvatar, CommunityUser
from ..storage.user_repository import CommunityUserRepository
from .identifiers import normalize_display_name, normalize_handle


class ProfileUnavailableError(ValueError):
    """Raised when a requested public handle is unavailable."""


@dataclass(frozen=True)
class AccountProfile:
    """Private account projection with a Community-relative avatar route.

    Community clients resolve ``avatar_url`` against their configured Community
    API base; it is deliberately not a Desktop (port 5173) same-origin URL.
    """

    id: str
    email: str
    handle: str
    display_name: str | None
    avatar_url: str | None = None


class AccountProfileService:
    """Load and update an authenticated user's profile through its repository."""

    def __init__(self, database: CommunityDatabase) -> None:
        self._database = database
        self._users = CommunityUserRepository()

    def get(self, user_id: str) -> AccountProfile | None:
        with self._database.transaction() as session:
            user = self._users.find_by_id(session, user_id)
            avatar = session.get(CommunityAvatar, user_id)
            return _to_profile(user, avatar) if user is not None else None

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
            avatar = session.get(CommunityAvatar, user_id)
            return _to_profile(updated, avatar)


def _to_profile(user: CommunityUser, avatar: CommunityAvatar | None) -> AccountProfile:
    return AccountProfile(
        id=user.id,
        email=user.email_normalized,
        handle=user.handle,
        display_name=user.display_name,
        avatar_url=(
            f"/api/v1/avatars/{user.id}?v={avatar.etag}" if avatar is not None else None
        ),
    )
