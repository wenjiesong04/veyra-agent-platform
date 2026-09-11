"""Database queries for the Community Agent registry."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from .schema import (
    CommunityAgent,
    CommunityAgentFork,
    CommunityAgentVersion,
    CommunityUser,
)


class CommunityRegistryRepository:
    """Keep registry queries separate from upload and auth workflows."""

    def find_agent(
        self, session: Session, *, owner_id: str, slug: str
    ) -> CommunityAgent | None:
        return session.scalar(
            select(CommunityAgent).where(
                CommunityAgent.owner_id == owner_id,
                CommunityAgent.slug == slug,
            )
        )

    def find_public_version(
        self,
        session: Session,
        *,
        owner_handle: str,
        slug: str,
        version: str | None = None,
    ) -> tuple[CommunityAgent, CommunityAgentVersion, CommunityUser] | None:
        query = (
            select(CommunityAgent, CommunityAgentVersion, CommunityUser)
            .join(
                CommunityAgentVersion,
                CommunityAgentVersion.agent_id == CommunityAgent.id,
            )
            .join(CommunityUser, CommunityUser.id == CommunityAgent.owner_id)
            .where(
                CommunityUser.handle == owner_handle,
                CommunityAgent.slug == slug,
                CommunityAgentVersion.status == "published",
            )
            .order_by(
                desc(CommunityAgentVersion.published_at),
                desc(CommunityAgentVersion.created_at),
            )
        )
        if version is not None:
            query = query.where(CommunityAgentVersion.version == version)
        row = session.execute(query.limit(1)).tuples().first()
        return row if row is not None else None

    def list_public(
        self, session: Session, *, query_text: str | None, limit: int
    ) -> list[tuple[CommunityAgent, CommunityAgentVersion, CommunityUser]]:
        query = (
            select(CommunityAgent, CommunityAgentVersion, CommunityUser)
            .join(
                CommunityAgentVersion,
                CommunityAgentVersion.agent_id == CommunityAgent.id,
            )
            .join(CommunityUser, CommunityUser.id == CommunityAgent.owner_id)
            .where(CommunityAgentVersion.status == "published")
            .order_by(
                desc(CommunityAgentVersion.published_at),
                desc(CommunityAgentVersion.created_at),
            )
            .limit(limit)
        )
        if query_text:
            needle = f"%{query_text}%"
            query = query.where(
                or_(
                    CommunityAgent.name.ilike(needle),
                    CommunityAgent.slug.ilike(needle),
                    CommunityAgent.description.ilike(needle),
                )
            )
        return list(session.execute(query).tuples().all())

    def create_agent(
        self,
        session: Session,
        *,
        owner_id: str,
        slug: str,
        name: str,
        description: str,
        now: datetime,
    ) -> CommunityAgent:
        agent = CommunityAgent(
            id=_uuid(),
            owner_id=owner_id,
            slug=slug,
            name=name,
            description=description,
            created_at=now,
            updated_at=now,
        )
        session.add(agent)
        session.flush()
        return agent

    def find_version(
        self, session: Session, *, agent_id: str, version: str
    ) -> CommunityAgentVersion | None:
        return session.scalar(
            select(CommunityAgentVersion).where(
                CommunityAgentVersion.agent_id == agent_id,
                CommunityAgentVersion.version == version,
            )
        )

    def create_version(
        self,
        session: Session,
        *,
        agent_id: str,
        version: str,
        source_storage_id: str,
        source_hash: str,
        behavior_hash: str,
        lock_hash: str,
        now: datetime,
    ) -> CommunityAgentVersion:
        record = CommunityAgentVersion(
            id=_uuid(),
            agent_id=agent_id,
            version=version,
            source_storage_id=source_storage_id,
            source_hash=source_hash,
            behavior_hash=behavior_hash,
            lock_hash=lock_hash,
            status="published",
            created_at=now,
            published_at=now,
        )
        session.add(record)
        session.flush()
        return record

    def find_fork_source(
        self,
        session: Session,
        *,
        owner_handle: str,
        slug: str,
        version: str,
    ) -> tuple[CommunityAgent, CommunityAgentVersion, CommunityUser] | None:
        return self.find_public_version(
            session,
            owner_handle=owner_handle,
            slug=slug,
            version=version,
        )

    def create_fork(
        self,
        session: Session,
        *,
        source_version_id: str,
        target_version_id: str,
        forked_by: str,
        now: datetime,
    ) -> CommunityAgentFork:
        fork = CommunityAgentFork(
            id=_uuid(),
            source_version_id=source_version_id,
            target_version_id=target_version_id,
            forked_by=forked_by,
            created_at=now,
        )
        session.add(fork)
        session.flush()
        return fork

    def fork_source(
        self, session: Session, *, target_version_id: str
    ) -> tuple[CommunityAgent, CommunityAgentVersion, CommunityUser] | None:
        query = (
            select(CommunityAgent, CommunityAgentVersion, CommunityUser)
            .select_from(CommunityAgentFork)
            .join(
                CommunityAgentVersion,
                CommunityAgentVersion.id == CommunityAgentFork.source_version_id,
            )
            .join(
                CommunityAgent,
                CommunityAgent.id == CommunityAgentVersion.agent_id,
            )
            .join(CommunityUser, CommunityUser.id == CommunityAgent.owner_id)
            .where(CommunityAgentFork.target_version_id == target_version_id)
        )
        return session.execute(query.limit(1)).tuples().first()


def _uuid() -> str:
    from .identifiers import new_uuid7

    return new_uuid7()
