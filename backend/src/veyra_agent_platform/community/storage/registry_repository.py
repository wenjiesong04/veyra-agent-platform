"""Database queries for the Community Agent registry."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from .schema import (
    CommunityAgent,
    CommunityAgentFork,
    CommunityAgentModeration,
    CommunityAgentReport,
    CommunityAgentReview,
    CommunityAgentStar,
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

    def list_public_versions(
        self,
        session: Session,
        *,
        owner_handle: str,
        slug: str,
    ) -> list[tuple[CommunityAgent, CommunityAgentVersion, CommunityUser]]:
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
        return list(session.execute(query).tuples().all())

    def list_moderation_queue(
        self, session: Session, *, limit: int
    ) -> list[tuple[CommunityAgent, CommunityAgentVersion, CommunityUser]]:
        query = (
            select(CommunityAgent, CommunityAgentVersion, CommunityUser)
            .join(
                CommunityAgentVersion,
                CommunityAgentVersion.agent_id == CommunityAgent.id,
            )
            .join(CommunityUser, CommunityUser.id == CommunityAgent.owner_id)
            .where(CommunityAgentVersion.status == "quarantined")
            .order_by(CommunityAgentVersion.created_at.asc())
            .limit(limit)
        )
        return list(session.execute(query).tuples().all())

    def find_version_for_moderation(
        self,
        session: Session,
        *,
        owner_handle: str,
        slug: str,
        version: str,
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
                CommunityAgentVersion.version == version,
            )
        )
        return session.execute(query.limit(1)).tuples().first()

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
        scan_json: str,
        status: str,
        published_at: datetime | None,
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
            status=status,
            scan_json=scan_json,
            created_at=now,
            published_at=published_at,
        )
        session.add(record)
        session.flush()
        return record

    @staticmethod
    def set_version_status(
        session: Session,
        record: CommunityAgentVersion,
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
    ) -> CommunityAgentModeration:
        record = CommunityAgentModeration(
            id=_uuid(),
            version_id=version_id,
            moderator_id=moderator_id,
            action=action,
            reason=reason,
            created_at=now,
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

    @staticmethod
    def feedback(session: Session, *, version_id: str) -> dict[str, Any]:
        star_count = session.scalar(
            select(func.count(CommunityAgentStar.id)).where(
                CommunityAgentStar.version_id == version_id
            )
        )
        review_count = session.scalar(
            select(func.count(CommunityAgentReview.id)).where(
                CommunityAgentReview.version_id == version_id
            )
        )
        average = session.scalar(
            select(func.avg(CommunityAgentReview.rating)).where(
                CommunityAgentReview.version_id == version_id
            )
        )
        return {
            "star_count": int(star_count or 0),
            "review_count": int(review_count or 0),
            "average_rating": round(float(average or 0), 2),
        }

    @staticmethod
    def find_star(
        session: Session, *, version_id: str, user_id: str
    ) -> CommunityAgentStar | None:
        return session.scalar(
            select(CommunityAgentStar).where(
                CommunityAgentStar.version_id == version_id,
                CommunityAgentStar.user_id == user_id,
            )
        )

    @staticmethod
    def create_star(
        session: Session, *, version_id: str, user_id: str, now: datetime
    ) -> CommunityAgentStar:
        star = CommunityAgentStar(
            id=_uuid(), version_id=version_id, user_id=user_id, created_at=now
        )
        session.add(star)
        session.flush()
        return star

    @staticmethod
    def delete_star(session: Session, star: CommunityAgentStar) -> None:
        session.delete(star)
        session.flush()

    @staticmethod
    def list_reviews(
        session: Session, *, version_id: str
    ) -> list[tuple[CommunityAgentReview, CommunityUser]]:
        query = (
            select(CommunityAgentReview, CommunityUser)
            .join(CommunityUser, CommunityUser.id == CommunityAgentReview.user_id)
            .where(CommunityAgentReview.version_id == version_id)
            .order_by(
                desc(CommunityAgentReview.updated_at),
                desc(CommunityAgentReview.id),
            )
        )
        return list(session.execute(query).tuples().all())

    @staticmethod
    def find_review(
        session: Session, *, version_id: str, user_id: str
    ) -> CommunityAgentReview | None:
        return session.scalar(
            select(CommunityAgentReview).where(
                CommunityAgentReview.version_id == version_id,
                CommunityAgentReview.user_id == user_id,
            )
        )

    @staticmethod
    def upsert_review(
        session: Session,
        *,
        version_id: str,
        user_id: str,
        rating: int,
        body: str,
        now: datetime,
    ) -> CommunityAgentReview:
        review = CommunityRegistryRepository.find_review(
            session, version_id=version_id, user_id=user_id
        )
        if review is None:
            review = CommunityAgentReview(
                id=_uuid(),
                version_id=version_id,
                user_id=user_id,
                rating=rating,
                body=body,
                created_at=now,
                updated_at=now,
            )
            session.add(review)
        else:
            review.rating = rating
            review.body = body
            review.updated_at = now
        session.flush()
        return review

    @staticmethod
    def find_report(
        session: Session, *, version_id: str, reporter_id: str, reason: str
    ) -> CommunityAgentReport | None:
        return session.scalar(
            select(CommunityAgentReport).where(
                CommunityAgentReport.version_id == version_id,
                CommunityAgentReport.reporter_id == reporter_id,
                CommunityAgentReport.reason == reason,
            )
        )

    @staticmethod
    def create_report(
        session: Session,
        *,
        version_id: str,
        reporter_id: str,
        reason: str,
        details: str,
        now: datetime,
    ) -> CommunityAgentReport:
        report = CommunityAgentReport(
            id=_uuid(),
            version_id=version_id,
            reporter_id=reporter_id,
            reason=reason,
            details=details,
            status="open",
            created_at=now,
        )
        session.add(report)
        session.flush()
        return report


def _uuid() -> str:
    from .identifiers import new_uuid7

    return new_uuid7()
