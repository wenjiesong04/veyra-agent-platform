"""Validated avatar lifecycle for authenticated Community accounts."""

from __future__ import annotations

import warnings
from contextlib import suppress
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from ..storage.avatar_storage import AvatarStorage
from ..storage.database import CommunityDatabase
from ..storage.identifiers import utc_now
from ..storage.schema import CommunityAvatar

MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_AVATAR_DIMENSION = 2048
MAX_AVATAR_PIXELS = 4_000_000
_FORMAT_MEDIA_TYPES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}


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
        except BaseException:
            self._storage.delete(storage_id)
            raise
        if old_storage_id is not None:
            # The replacement is committed. Retaining a stale object is safer
            # than deleting the newly referenced object after a cleanup fault.
            with suppress(Exception):
                self._storage.delete(old_storage_id)
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
    """Decode and constrain a single PNG, JPEG, or WebP avatar image."""

    if not content or len(content) > MAX_AVATAR_BYTES:
        raise InvalidAvatar("avatar size is invalid")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as verified:
                verified.verify()
            with Image.open(BytesIO(content)) as decoded:
                media_type = _FORMAT_MEDIA_TYPES.get(decoded.format or "")
                if media_type is None:
                    raise InvalidAvatar("avatar format is not allowed")
                width, height = decoded.size
                if (
                    width > MAX_AVATAR_DIMENSION
                    or height > MAX_AVATAR_DIMENSION
                    or width * height > MAX_AVATAR_PIXELS
                ):
                    raise InvalidAvatar("avatar dimensions are too large")
                if getattr(decoded, "n_frames", 1) != 1:
                    raise InvalidAvatar("animated avatars are not allowed")
                decoded.load()
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        SyntaxError,
        UnidentifiedImageError,
    ) as error:
        raise InvalidAvatar("avatar image data is invalid") from error
    claimed_base_type = (
        claimed_media_type.split(";", 1)[0].strip().lower()
        if claimed_media_type
        else None
    )
    if claimed_base_type is not None and claimed_base_type != media_type:
        raise InvalidAvatar("avatar content type does not match bytes")
    return media_type
