"""Validated avatar lifecycle for authenticated Community accounts."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from ..storage.avatar_storage import AvatarStorage
from ..storage.database import CommunityDatabase
from ..storage.identifiers import utc_now
from ..storage.schema import CommunityAvatar

MAX_AVATAR_BYTES = 2 * 1024 * 1024
_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"RIFF", "image/webp"),
)


class InvalidAvatar(ValueError):
    """The uploaded body is not a permitted avatar image."""


@dataclass(frozen=True)
class StoredAvatar:
    user_id: str
    storage_id: str
    media_type: str
    byte_size: int
    etag: str


class AccountAvatarService:
    """Persist metadata transactionally while keeping bytes in object storage."""

    def __init__(self, database: CommunityDatabase, storage: AvatarStorage) -> None:
        self._database = database
        self._storage = storage

    def replace(
        self, user_id: str, content: bytes, claimed_media_type: str | None
    ) -> str:
        media_type = verify_avatar(content, claimed_media_type)
        storage_id = self._storage.put(content)
        try:
            with self._database.transaction() as session:
                previous = session.get(CommunityAvatar, user_id)
                old_storage_id = previous.storage_id if previous is not None else None
                now = utc_now()
                avatar = CommunityAvatar(
                    user_id=user_id,
                    storage_id=storage_id,
                    media_type=media_type,
                    byte_size=len(content),
                    etag=sha256(content).hexdigest(),
                    created_at=now,
                    updated_at=now,
                )
                if previous is None:
                    session.add(avatar)
                else:
                    previous.storage_id = avatar.storage_id
                    previous.media_type = avatar.media_type
                    previous.byte_size = avatar.byte_size
                    previous.etag = avatar.etag
                    previous.updated_at = now
            if old_storage_id is not None:
                self._storage.delete(old_storage_id)
        except BaseException:
            self._storage.delete(storage_id)
            raise
        return f"/api/v1/avatars/{user_id}"

    def get(self, user_id: str) -> tuple[StoredAvatar, bytes] | None:
        with self._database.transaction() as session:
            avatar = session.get(CommunityAvatar, user_id)
            if avatar is None:
                return None
            result = StoredAvatar(
                user_id=avatar.user_id,
                storage_id=avatar.storage_id,
                media_type=avatar.media_type,
                byte_size=avatar.byte_size,
                etag=avatar.etag,
            )
        content = self._storage.get(result.storage_id)
        return (result, content) if content is not None else None

    def delete(self, user_id: str) -> bool:
        with self._database.transaction() as session:
            avatar = session.get(CommunityAvatar, user_id)
            if avatar is None:
                return False
            storage_id = avatar.storage_id
            session.delete(avatar)
        self._storage.delete(storage_id)
        return True


def verify_avatar(content: bytes, claimed_media_type: str | None) -> str:
    """Accept only bounded PNG, JPEG, or WebP bodies identified by bytes."""

    if not content or len(content) > MAX_AVATAR_BYTES:
        raise InvalidAvatar("avatar size is invalid")
    media_type = _media_type(content)
    if media_type is None:
        raise InvalidAvatar("avatar signature is not allowed")
    if media_type == "image/webp" and content[8:12] != b"WEBP":
        raise InvalidAvatar("avatar signature is not allowed")
    claimed_base_type = (
        claimed_media_type.split(";", 1)[0].strip().lower()
        if claimed_media_type
        else None
    )
    if claimed_base_type is not None and claimed_base_type != media_type:
        raise InvalidAvatar("avatar content type does not match bytes")
    return media_type


def _media_type(content: bytes) -> str | None:
    for signature, media_type in _SIGNATURES:
        if content.startswith(signature):
            return media_type
    return None
