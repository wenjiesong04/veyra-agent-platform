"""Publish, browse, and download declarative Plugin Packs."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.exc import IntegrityError

from veyra_agent_platform.local.plugins.packaging import (
    PluginPack,
    PluginPackError,
    unpack_plugin_archive,
)

from ..accounts.profiles import AccountProfile, AccountProfileService
from ..storage.database import CommunityDatabase
from ..storage.identifiers import utc_now
from ..storage.package_storage import PackageStorage
from ..storage.plugin_repository import CommunityPluginRepository
from ..storage.schema import CommunityPlugin, CommunityPluginVersion, CommunityUser
from .license_scan import scan_license

MAX_PLUGIN_PACKAGE_BYTES = 5_000_000
_SLUG = re.compile(r"^[a-z][a-z0-9-]{0,62}$")


class CommunityPluginRegistryError(ValueError):
    """A Plugin Pack cannot be published or found in Community."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CommunityPluginRegistryService:
    """Own the public Plugin Pack registry; Community never executes packs."""

    def __init__(
        self,
        database: CommunityDatabase,
        storage: PackageStorage,
        profiles: AccountProfileService,
        *,
        require_moderation: bool = False,
    ) -> None:
        self.database = database
        self.storage = storage
        self.profiles = profiles
        self.require_moderation = require_moderation
        self.repository = CommunityPluginRepository()

    def list_entries(
        self, *, query: str | None = None, limit: int = 50
    ) -> dict[str, Any]:
        clean_query = query.strip()[:120] if query else None
        clean_limit = min(max(limit, 1), 100)
        with self.database.transaction() as session:
            rows = self.repository.list_public(
                session, query_text=clean_query, limit=clean_limit
            )
            entries = [self._entry_payload(*row) for row in rows]
        return {"schema_version": "community.plugin.registry.v1", "entries": entries}

    def entry(
        self, *, owner_handle: str, slug: str, version: str | None = None
    ) -> dict[str, Any]:
        with self.database.transaction() as session:
            row = self.repository.find_public_version(
                session, owner_handle=owner_handle, slug=slug, version=version
            )
        if row is None:
            raise CommunityPluginRegistryError(
                "plugin_entry_not_found", "Published Plugin Pack was not found"
            )
        return self._entry_payload(*row)

    def versions(self, *, owner_handle: str, slug: str) -> dict[str, Any]:
        with self.database.transaction() as session:
            rows = self.repository.list_public_versions(
                session, owner_handle=owner_handle, slug=slug
            )
            entries = [self._entry_payload(*row) for row in rows]
        if not entries:
            raise CommunityPluginRegistryError(
                "plugin_entry_not_found", "Published Plugin Pack was not found"
            )
        return {
            "schema_version": "community.plugin.registry.v1",
            "owner_handle": owner_handle,
            "slug": slug,
            "versions": entries,
        }

    def download(
        self, *, owner_handle: str, slug: str, version: str | None = None
    ) -> tuple[dict[str, Any], bytes]:
        with self.database.transaction() as session:
            row = self.repository.find_public_version(
                session, owner_handle=owner_handle, slug=slug, version=version
            )
        if row is None:
            raise CommunityPluginRegistryError(
                "plugin_entry_not_found", "Published Plugin Pack was not found"
            )
        plugin, record, user = row
        content = self.storage.get(record.package_storage_id)
        if content is None:
            raise CommunityPluginRegistryError(
                "plugin_package_missing", "Published Plugin Pack is unavailable"
            )
        if len(content) > MAX_PLUGIN_PACKAGE_BYTES:
            raise CommunityPluginRegistryError(
                "plugin_package_invalid", "Published Plugin Pack exceeds the size limit"
            )
        return self._entry_payload(plugin, record, user), content

    def publish(
        self, *, user_id: str, filename: str | None, content: bytes
    ) -> dict[str, Any]:
        if not isinstance(content, bytes) or len(content) > MAX_PLUGIN_PACKAGE_BYTES:
            raise CommunityPluginRegistryError(
                "plugin_package_too_large", "Plugin Pack exceeds the 5 MiB limit"
            )
        if filename and not filename.lower().endswith((".zip", ".vplugin.zip")):
            raise CommunityPluginRegistryError(
                "plugin_package_type_invalid", "Plugin Pack must be a zip archive"
            )
        try:
            pack = unpack_plugin_archive(filename, content)
        except PluginPackError as exc:
            raise CommunityPluginRegistryError(
                "plugin_package_invalid", str(exc)
            ) from exc
        suffix = pack.plugin_id.removeprefix("veyra.plugin.")
        if not _SLUG.fullmatch(suffix):
            raise CommunityPluginRegistryError(
                "plugin_slug_invalid",
                "Community Plugin Pack ids must use lowercase hyphen slugs",
            )
        profile = self.profiles.get(user_id)
        if profile is None:
            raise CommunityPluginRegistryError(
                "plugin_account_not_found", "Publisher account was not found"
            )
        storage_id = self.storage.put(content)
        manifest_json = json.dumps(
            _public_manifest(pack), ensure_ascii=False, sort_keys=True
        )
        now = utc_now()
        status = "quarantined" if self.require_moderation else "published"
        try:
            with self.database.transaction() as session:
                plugin = self.repository.find_plugin(
                    session, owner_id=user_id, slug=suffix
                )
                if plugin is None:
                    plugin = self.repository.create_plugin(
                        session,
                        owner_id=user_id,
                        slug=suffix,
                        name=pack.name,
                        description=pack.description,
                        now=now,
                    )
                else:
                    plugin.name = pack.name
                    plugin.description = pack.description
                    plugin.updated_at = now
                    session.flush()
                if (
                    self.repository.find_version(
                        session, plugin_id=plugin.id, version=pack.version
                    )
                    is not None
                ):
                    raise CommunityPluginRegistryError(
                        "plugin_version_exists",
                        "This Plugin Pack version is already published",
                    )
                record = self.repository.create_version(
                    session,
                    plugin_id=plugin.id,
                    version=pack.version,
                    package_storage_id=storage_id,
                    package_hash=pack.content_hash,
                    manifest_json=manifest_json,
                    skill_count=len(pack.skills),
                    mcp_count=len(pack.mcp_servers),
                    status=status,
                    published_at=now if status == "published" else None,
                    now=now,
                )
        except IntegrityError as exc:
            raise CommunityPluginRegistryError(
                "plugin_version_exists", "This Plugin Pack version is already published"
            ) from exc
        return self._entry_payload(plugin, record, profile)

    def moderation_queue(self, *, limit: int = 50) -> dict[str, Any]:
        clean_limit = min(max(limit, 1), 100)
        with self.database.transaction() as session:
            rows = self.repository.list_moderation_queue(session, limit=clean_limit)
            entries = [self._entry_payload(*row) for row in rows]
        return {"schema_version": "community.plugin.moderation.v1", "entries": entries}

    def moderate(
        self,
        *,
        owner_handle: str,
        slug: str,
        version: str,
        moderator_id: str,
        action: str,
        reason: str,
    ) -> dict[str, Any]:
        if action not in {"publish", "reject"}:
            raise CommunityPluginRegistryError(
                "plugin_moderation_action_invalid",
                "Moderation action must publish or reject",
            )
        clean_reason = reason.strip()
        if not clean_reason or len(clean_reason) > 4_000:
            raise CommunityPluginRegistryError(
                "plugin_moderation_reason_invalid",
                "Moderation reason must contain 1 to 4000 characters",
            )
        with self.database.transaction() as session:
            row = self.repository.find_version_for_moderation(
                session,
                owner_handle=owner_handle,
                slug=slug,
                version=version,
            )
            if row is None:
                raise CommunityPluginRegistryError(
                    "plugin_version_not_found", "Plugin Pack version was not found"
                )
            plugin, record, user = row
            if record.status != "quarantined":
                raise CommunityPluginRegistryError(
                    "plugin_moderation_not_pending",
                    "Only quarantined Plugin Pack versions can be moderated",
                )
            next_status = "published" if action == "publish" else "rejected"
            self.repository.set_version_status(
                session,
                record,
                status=next_status,
                published_at=utc_now() if next_status == "published" else None,
            )
            self.repository.create_moderation(
                session,
                version_id=record.id,
                moderator_id=moderator_id,
                action=action,
                reason=clean_reason,
                now=utc_now(),
            )
        return self._entry_payload(plugin, record, user)

    @staticmethod
    def _entry_payload(
        plugin: CommunityPlugin,
        record: CommunityPluginVersion,
        user: AccountProfile | CommunityUser,
    ) -> dict[str, Any]:
        try:
            manifest = json.loads(record.manifest_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            manifest = {}
        return {
            "schema_version": "community.plugin.registry.v1",
            "owner_handle": user.handle,
            "owner_display_name": user.display_name,
            "plugin_id": manifest.get("plugin_id", f"veyra.plugin.{plugin.slug}"),
            "slug": plugin.slug,
            "name": plugin.name,
            "description": plugin.description,
            "version": record.version,
            "package_hash": record.package_hash,
            "status": record.status,
            "skill_count": record.skill_count,
            "mcp_count": record.mcp_count,
            "skills": manifest.get("skills", []),
            "mcp_servers": manifest.get("mcp_servers", []),
            "license": manifest.get("license"),
            "license_scan": manifest.get("license_scan"),
            "created_at": record.created_at.isoformat(),
            "published_at": record.published_at.isoformat()
            if record.published_at
            else None,
        }


def _public_manifest(pack: PluginPack) -> dict[str, Any]:
    return {
        "plugin_id": pack.plugin_id,
        "license": pack.license,
        "license_scan": scan_license(pack.license),
        "skills": [
            {
                "path": skill.path,
                "reference": skill.reference,
                "name": skill.name,
                "description": skill.description,
            }
            for skill in pack.skills
        ],
        "mcp_servers": [
            {
                "name": server["name"],
                "transport": server["transport"],
                "url": server["url"],
            }
            for server in pack.mcp_servers
        ],
    }
