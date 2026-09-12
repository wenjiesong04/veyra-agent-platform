"""Database queries for the Community Plugin Pack registry."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from .identifiers import new_uuid7
from .schema import (
    CommunityPlugin,
    CommunityPluginModeration,
    CommunityPluginVersion,
    CommunityUser,
)


class CommunityPluginRepository:
    """Keep Plugin Pack identity, version, and moderation queries separate."""

    def find_plugin(
        self, session: Session, *, owner_id: str, slug: str
    ) -> CommunityPlugin | None:
        return session.scalar(
            select(CommunityPlugin).where(
                CommunityPlugin.owner_id == owner_id,
                CommunityPlugin.slug == slug,
            )
        )

    def find_public_version(
        self,
        session: Session,
        *,
        owner_handle: str,
        slug: str,
        version: str | None = None,
    ) -> tuple[CommunityPlugin, CommunityPluginVersion, CommunityUser] | None:
        query = (
            select(CommunityPlugin, CommunityPluginVersion, CommunityUser)
            .join(
                CommunityPluginVersion,
                CommunityPluginVersion.plugin_id == CommunityPlugin.id,
            )
            .join(CommunityUser, CommunityUser.id == CommunityPlugin.owner_id)
            .where(
                CommunityUser.handle == owner_handle,
                CommunityPlugin.slug == slug,
                CommunityPluginVersion.status == "published",
            )
            .order_by(
                desc(CommunityPluginVersion.published_at),
                desc(CommunityPluginVersion.created_at),
            )
        )
        if version is not None:
            query = query.where(CommunityPluginVersion.version == version)
        return session.execute(query.limit(1)).tuples().first()

    def list_public(
        self, session: Session, *, query_text: str | None, limit: int
    ) -> list[tuple[CommunityPlugin, CommunityPluginVersion, CommunityUser]]:
        query = (
            select(CommunityPlugin, CommunityPluginVersion, CommunityUser)
            .join(
                CommunityPluginVersion,
                CommunityPluginVersion.plugin_id == CommunityPlugin.id,
            )
            .join(CommunityUser, CommunityUser.id == CommunityPlugin.owner_id)
            .where(CommunityPluginVersion.status == "published")
            .order_by(
                desc(CommunityPluginVersion.published_at),
                desc(CommunityPluginVersion.created_at),
            )
            .limit(limit)
        )
        if query_text:
            needle = f"%{query_text}%"
            query = query.where(
                or_(
                    CommunityPlugin.name.ilike(needle),
                    CommunityPlugin.slug.ilike(needle),
                    CommunityPlugin.description.ilike(needle),
                )
            )
        return list(session.execute(query).tuples().all())

    def list_public_versions(
        self, session: Session, *, owner_handle: str, slug: str
    ) -> list[tuple[CommunityPlugin, CommunityPluginVersion, CommunityUser]]:
        query = (
            select(CommunityPlugin, CommunityPluginVersion, CommunityUser)
            .join(
                CommunityPluginVersion,
                CommunityPluginVersion.plugin_id == CommunityPlugin.id,
            )
            .join(CommunityUser, CommunityUser.id == CommunityPlugin.owner_id)
            .where(
                CommunityUser.handle == owner_handle,
                CommunityPlugin.slug == slug,
                CommunityPluginVersion.status == "published",
            )
            .order_by(
                desc(CommunityPluginVersion.published_at),
                desc(CommunityPluginVersion.created_at),
            )
        )
        return list(session.execute(query).tuples().all())

    def list_moderation_queue(
        self, session: Session, *, limit: int
    ) -> list[tuple[CommunityPlugin, CommunityPluginVersion, CommunityUser]]:
        query = (
            select(CommunityPlugin, CommunityPluginVersion, CommunityUser)
            .join(
                CommunityPluginVersion,
                CommunityPluginVersion.plugin_id == CommunityPlugin.id,
            )
            .join(CommunityUser, CommunityUser.id == CommunityPlugin.owner_id)
            .where(CommunityPluginVersion.status == "quarantined")
            .order_by(CommunityPluginVersion.created_at.asc())
            .limit(limit)
        )
        return list(session.execute(query).tuples().all())

    def find_version(
        self, session: Session, *, plugin_id: str, version: str
    ) -> CommunityPluginVersion | None:
        return session.scalar(
            select(CommunityPluginVersion).where(
                CommunityPluginVersion.plugin_id == plugin_id,
                CommunityPluginVersion.version == version,
            )
        )

    def find_version_for_moderation(
        self,
        session: Session,
        *,
        owner_handle: str,
        slug: str,
        version: str,
    ) -> tuple[CommunityPlugin, CommunityPluginVersion, CommunityUser] | None:
        query = (
            select(CommunityPlugin, CommunityPluginVersion, CommunityUser)
            .join(
                CommunityPluginVersion,
                CommunityPluginVersion.plugin_id == CommunityPlugin.id,
            )
            .join(CommunityUser, CommunityUser.id == CommunityPlugin.owner_id)
            .where(
                CommunityUser.handle == owner_handle,
                CommunityPlugin.slug == slug,
                CommunityPluginVersion.version == version,
            )
        )
        return session.execute(query.limit(1)).tuples().first()

    def create_plugin(
        self,
        session: Session,
        *,
        owner_id: str,
        slug: str,
        name: str,
        description: str,
        now: datetime,
    ) -> CommunityPlugin:
        plugin = CommunityPlugin(
            id=new_uuid7(),
            owner_id=owner_id,
            slug=slug,
            name=name,
            description=description,
            created_at=now,
            updated_at=now,
        )
        session.add(plugin)
        session.flush()
        return plugin

    def create_version(
        self,
        session: Session,
        *,
        plugin_id: str,
        version: str,
        package_storage_id: str,
        package_hash: str,
        manifest_json: str,
        skill_count: int,
        mcp_count: int,
        status: str,
        published_at: datetime | None,
        now: datetime,
    ) -> CommunityPluginVersion:
        record = CommunityPluginVersion(
            id=new_uuid7(),
            plugin_id=plugin_id,
            version=version,
            package_storage_id=package_storage_id,
            package_hash=package_hash,
            manifest_json=manifest_json,
            skill_count=skill_count,
            mcp_count=mcp_count,
            status=status,
            created_at=now,
            published_at=published_at,
        )
        session.add(record)
        session.flush()
        return record

    @staticmethod
    def set_version_status(
        session: Session,
        record: CommunityPluginVersion,
        *,
        status: str,
        published_at: datetime | None,
    ) -> None:
        record.status = status
        record.published_at = published_at
        session.flush()

    def create_moderation(
        self,
        session: Session,
        *,
        version_id: str,
        moderator_id: str,
        action: str,
        reason: str,
        now: datetime,
    ) -> CommunityPluginModeration:
        record = CommunityPluginModeration(
            id=new_uuid7(),
            version_id=version_id,
            moderator_id=moderator_id,
            action=action,
            reason=reason,
            created_at=now,
        )
        session.add(record)
        session.flush()
        return record
