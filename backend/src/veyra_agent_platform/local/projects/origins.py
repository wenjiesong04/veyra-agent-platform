"""Portable origin metadata retained for locally imported Community Agents."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(
    r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)


@dataclass(frozen=True)
class CommunityAgentOrigin:
    """Identify the immutable Community version used for a local import."""

    owner_handle: str
    slug: str
    version: str
    source_hash: str

    @classmethod
    def from_optional_fields(
        cls,
        *,
        owner_handle: str | None,
        slug: str | None,
        version: str | None,
        source_hash: str | None,
    ) -> CommunityAgentOrigin | None:
        fields = (owner_handle, slug, version, source_hash)
        if all(value is None for value in fields):
            return None
        if any(value is None or not value.strip() for value in fields):
            raise ValueError("Community Agent origin fields must be provided together")
        assert owner_handle is not None
        assert slug is not None
        assert version is not None
        assert source_hash is not None
        normalized = cls(
            owner_handle=owner_handle.strip(),
            slug=slug.strip(),
            version=version.strip(),
            source_hash=source_hash.strip(),
        )
        if len(normalized.owner_handle) > 32 or len(normalized.slug) > 63:
            raise ValueError("Community Agent origin text is too long")
        if len(normalized.version) > 32 or not _VERSION.fullmatch(normalized.version):
            raise ValueError("Community Agent origin version is invalid")
        if not _SHA256.fullmatch(normalized.source_hash):
            raise ValueError("Community Agent origin source hash is invalid")
        return normalized

    def to_dict(self) -> dict[str, str]:
        return {
            "owner_handle": self.owner_handle,
            "slug": self.slug,
            "version": self.version,
            "source_hash": self.source_hash,
        }
