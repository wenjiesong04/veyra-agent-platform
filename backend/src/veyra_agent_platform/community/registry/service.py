"""Publish, browse, and download validated Agent packages."""

from __future__ import annotations

import re
from typing import Any

import yaml  # type: ignore[import-untyped]
from sqlalchemy.exc import IntegrityError

from veyra_agent_platform.contracts.agent import AgentSource

from ..accounts.profiles import AccountProfileService
from ..storage.database import CommunityDatabase
from ..storage.identifiers import utc_now
from ..storage.package_storage import LocalPackageStorage
from ..storage.registry_repository import CommunityRegistryRepository
from ..storage.schema import CommunityAgent, CommunityAgentVersion

MAX_PACKAGE_BYTES = 1_000_000
_SLUG = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_FORBIDDEN_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "ghp_",
    "github_pat_",
    "AKIA",
)


class CommunityRegistryError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CommunityRegistryService:
    """Own the validated package boundary; Community never executes Agents."""

    def __init__(
        self,
        database: CommunityDatabase,
        storage: LocalPackageStorage,
        profiles: AccountProfileService,
    ) -> None:
        self.database = database
        self.storage = storage
        self.profiles = profiles
        self.repository = CommunityRegistryRepository()

    def list_entries(
        self, *, query: str | None = None, limit: int = 50
    ) -> dict[str, Any]:
        clean_query = query.strip()[:120] if query else None
        clean_limit = min(max(limit, 1), 100)
        with self.database.transaction() as session:
            rows = self.repository.list_public(
                session, query_text=clean_query, limit=clean_limit
            )
        return {
            "schema_version": "community.registry.v1",
            "entries": [_entry_payload(*row) for row in rows],
        }

    def entry(
        self,
        *,
        owner_handle: str,
        slug: str,
        version: str | None = None,
    ) -> dict[str, Any]:
        with self.database.transaction() as session:
            row = self.repository.find_public_version(
                session,
                owner_handle=owner_handle,
                slug=slug,
                version=version,
            )
        if row is None:
            raise CommunityRegistryError(
                "registry_entry_not_found", "Published Agent was not found"
            )
        return _entry_payload(*row)

    def download(
        self, *, owner_handle: str, slug: str, version: str | None = None
    ) -> tuple[dict[str, Any], bytes]:
        with self.database.transaction() as session:
            row = self.repository.find_public_version(
                session,
                owner_handle=owner_handle,
                slug=slug,
                version=version,
            )
        if row is None:
            raise CommunityRegistryError(
                "registry_entry_not_found", "Published Agent was not found"
            )
        agent, record, user = row
        content = self.storage.get(record.source_storage_id)
        if content is None:
            raise CommunityRegistryError(
                "registry_package_missing", "Published Agent package is unavailable"
            )
        return _entry_payload(agent, record, user), content

    def publish(
        self, *, user_id: str, filename: str | None, content: bytes
    ) -> dict[str, Any]:
        if len(content) > MAX_PACKAGE_BYTES:
            raise CommunityRegistryError(
                "registry_package_too_large", "Agent package exceeds the 1 MiB limit"
            )
        if filename and not filename.lower().endswith((".yaml", ".yml")):
            raise CommunityRegistryError(
                "registry_package_type_invalid", "Agent package must be YAML"
            )
        try:
            source_text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CommunityRegistryError(
                "registry_package_invalid", "Agent package must be UTF-8"
            ) from exc
        _scan_source(source_text)
        try:
            payload = yaml.safe_load(source_text)
            source = AgentSource.from_dict(payload)
        except (yaml.YAMLError, TypeError, ValueError) as exc:
            raise CommunityRegistryError(
                "registry_package_invalid", "Agent package is not a valid Agent source"
            ) from exc
        if not _SLUG.fullmatch(source.slug):
            raise CommunityRegistryError(
                "registry_slug_invalid", "Agent slug is not publishable"
            )
        profile = self.profiles.get(user_id)
        if profile is None:
            raise CommunityRegistryError(
                "registry_account_not_found", "Publisher account was not found"
            )
        canonical_text = yaml.safe_dump(
            source.to_dict(), sort_keys=False, allow_unicode=True
        )
        canonical_bytes = canonical_text.encode("utf-8")
        storage_id = self.storage.put(canonical_bytes)
        now = utc_now()
        try:
            with self.database.transaction() as session:
                agent = self.repository.find_agent(
                    session, owner_id=user_id, slug=source.slug
                )
                if agent is None:
                    agent = self.repository.create_agent(
                        session,
                        owner_id=user_id,
                        slug=source.slug,
                        name=source.name,
                        description=source.description,
                        now=now,
                    )
                else:
                    agent.name = source.name
                    agent.description = source.description
                    agent.updated_at = now
                    session.flush()
                if (
                    self.repository.find_version(
                        session, agent_id=agent.id, version=source.version
                    )
                    is not None
                ):
                    raise CommunityRegistryError(
                        "registry_version_exists",
                        "This Agent version is already published",
                    )
                record = self.repository.create_version(
                    session,
                    agent_id=agent.id,
                    version=source.version,
                    source_storage_id=storage_id,
                    source_hash=source.source_hash,
                    behavior_hash=source.behavior_hash,
                    lock_hash=source.lock_hash,
                    now=now,
                )
        except IntegrityError as exc:
            raise CommunityRegistryError(
                "registry_version_exists", "This Agent version is already published"
            ) from exc
        return _entry_payload(agent, record, profile)


def _scan_source(source_text: str) -> None:
    for marker in _FORBIDDEN_MARKERS:
        if marker in source_text:
            raise CommunityRegistryError(
                "registry_secret_detected", "Agent package contains a credential marker"
            )


def _entry_payload(
    agent: CommunityAgent,
    record: CommunityAgentVersion,
    user: Any,
) -> dict[str, Any]:
    return {
        "schema_version": "community.registry.v1",
        "owner_handle": user.handle,
        "owner_display_name": user.display_name,
        "slug": agent.slug,
        "name": agent.name,
        "description": agent.description,
        "version": record.version,
        "source_hash": record.source_hash,
        "behavior_hash": record.behavior_hash,
        "lock_hash": record.lock_hash,
        "status": record.status,
        "created_at": record.created_at.isoformat(),
        "published_at": record.published_at.isoformat()
        if record.published_at
        else None,
    }
