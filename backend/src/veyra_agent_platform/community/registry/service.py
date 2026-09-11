"""Publish, browse, and download validated Agent packages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import yaml  # type: ignore[import-untyped]
from sqlalchemy.exc import IntegrityError

from veyra_agent_platform.contracts.agent import AgentSource

from ..accounts.profiles import AccountProfileService
from ..storage.database import CommunityDatabase
from ..storage.identifiers import utc_now
from ..storage.package_storage import LocalPackageStorage
from ..storage.registry_repository import CommunityRegistryRepository
from ..storage.schema import CommunityAgent, CommunityAgentVersion, CommunityUser

MAX_PACKAGE_BYTES = 1_000_000
_SLUG = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_FORBIDDEN_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "ghp_",
    "github_pat_",
    "AKIA",
)
_SEMVER = re.compile(
    r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CommunityRegistryError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CommunityForkOrigin:
    """The published version that a new Community version was forked from."""

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
    ) -> CommunityForkOrigin | None:
        fields = (owner_handle, slug, version, source_hash)
        if all(value is None for value in fields):
            return None
        if any(value is None or not value.strip() for value in fields):
            raise CommunityRegistryError(
                "registry_fork_invalid",
                "Fork origin fields must be provided together",
            )
        assert owner_handle is not None
        assert slug is not None
        assert version is not None
        assert source_hash is not None
        origin = cls(
            owner_handle=owner_handle.strip(),
            slug=slug.strip(),
            version=version.strip(),
            source_hash=source_hash.strip(),
        )
        if len(origin.owner_handle) > 32 or len(origin.slug) > 63:
            raise CommunityRegistryError(
                "registry_fork_invalid", "Fork origin identity is too long"
            )
        if not _SEMVER.fullmatch(origin.version) or len(origin.version) > 32:
            raise CommunityRegistryError(
                "registry_fork_invalid", "Fork origin version is invalid"
            )
        if not _SHA256.fullmatch(origin.source_hash):
            raise CommunityRegistryError(
                "registry_fork_invalid", "Fork origin source hash is invalid"
            )
        return origin


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
            entries = [
                _entry_payload(
                    *row,
                    fork_source=self.repository.fork_source(
                        session, target_version_id=row[1].id
                    ),
                    feedback=self.repository.feedback(session, version_id=row[1].id),
                )
                for row in rows
            ]
        return {
            "schema_version": "community.registry.v1",
            "entries": entries,
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
            fork_source = (
                self.repository.fork_source(session, target_version_id=row[1].id)
                if row is not None
                else None
            )
            feedback = (
                self.repository.feedback(session, version_id=row[1].id)
                if row is not None
                else None
            )
        if row is None:
            raise CommunityRegistryError(
                "registry_entry_not_found", "Published Agent was not found"
            )
        return _entry_payload(*row, fork_source=fork_source, feedback=feedback)

    def versions(self, *, owner_handle: str, slug: str) -> dict[str, Any]:
        with self.database.transaction() as session:
            rows = self.repository.list_public_versions(
                session, owner_handle=owner_handle, slug=slug
            )
            entries = [
                _entry_payload(
                    *row,
                    fork_source=self.repository.fork_source(
                        session, target_version_id=row[1].id
                    ),
                    feedback=self.repository.feedback(session, version_id=row[1].id),
                )
                for row in rows
            ]
        if not entries:
            raise CommunityRegistryError(
                "registry_entry_not_found", "Published Agent was not found"
            )
        return {
            "schema_version": "community.registry.v1",
            "owner_handle": owner_handle,
            "slug": slug,
            "versions": entries,
        }

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
            fork_source = (
                self.repository.fork_source(session, target_version_id=row[1].id)
                if row is not None
                else None
            )
            feedback = (
                self.repository.feedback(session, version_id=row[1].id)
                if row is not None
                else None
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
        return (
            _entry_payload(
                agent, record, user, fork_source=fork_source, feedback=feedback
            ),
            content,
        )

    def publish(
        self,
        *,
        user_id: str,
        filename: str | None,
        content: bytes,
        fork_origin: CommunityForkOrigin | None = None,
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
                source_fork = None
                if fork_origin is not None:
                    source_fork = self.repository.find_fork_source(
                        session,
                        owner_handle=fork_origin.owner_handle,
                        slug=fork_origin.slug,
                        version=fork_origin.version,
                    )
                    if (
                        source_fork is None
                        or source_fork[1].source_hash != fork_origin.source_hash
                    ):
                        raise CommunityRegistryError(
                            "registry_fork_source_not_found",
                            "Fork source version was not found or changed",
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
                if source_fork is not None:
                    self.repository.create_fork(
                        session,
                        source_version_id=source_fork[1].id,
                        target_version_id=record.id,
                        forked_by=user_id,
                        now=now,
                    )
                feedback = self.repository.feedback(session, version_id=record.id)
        except IntegrityError as exc:
            raise CommunityRegistryError(
                "registry_version_exists", "This Agent version is already published"
            ) from exc
        return _entry_payload(
            agent,
            record,
            profile,
            fork_source=source_fork,
            feedback=feedback,
        )

    def star(
        self, *, owner_handle: str, slug: str, version: str, user_id: str
    ) -> dict[str, Any]:
        with self.database.transaction() as session:
            record = self._public_record(
                session, owner_handle=owner_handle, slug=slug, version=version
            )
            if (
                self.repository.find_star(
                    session, version_id=record.id, user_id=user_id
                )
                is None
            ):
                self.repository.create_star(
                    session, version_id=record.id, user_id=user_id, now=utc_now()
                )
            feedback = self.repository.feedback(session, version_id=record.id)
        return {
            "schema_version": "community.feedback.v1",
            "starred": True,
            **feedback,
        }

    def star_status(
        self, *, owner_handle: str, slug: str, version: str, user_id: str
    ) -> dict[str, Any]:
        with self.database.transaction() as session:
            record = self._public_record(
                session, owner_handle=owner_handle, slug=slug, version=version
            )
            starred = (
                self.repository.find_star(
                    session, version_id=record.id, user_id=user_id
                )
                is not None
            )
            feedback = self.repository.feedback(session, version_id=record.id)
        return {
            "schema_version": "community.feedback.v1",
            "starred": starred,
            **feedback,
        }

    def unstar(
        self, *, owner_handle: str, slug: str, version: str, user_id: str
    ) -> dict[str, Any]:
        with self.database.transaction() as session:
            record = self._public_record(
                session, owner_handle=owner_handle, slug=slug, version=version
            )
            star = self.repository.find_star(
                session, version_id=record.id, user_id=user_id
            )
            if star is not None:
                self.repository.delete_star(session, star)
            feedback = self.repository.feedback(session, version_id=record.id)
        return {
            "schema_version": "community.feedback.v1",
            "starred": False,
            **feedback,
        }

    def reviews(self, *, owner_handle: str, slug: str, version: str) -> dict[str, Any]:
        with self.database.transaction() as session:
            record = self._public_record(
                session, owner_handle=owner_handle, slug=slug, version=version
            )
            reviews = [
                _review_payload(review, user)
                for review, user in self.repository.list_reviews(
                    session, version_id=record.id
                )
            ]
        return {
            "schema_version": "community.feedback.v1",
            "reviews": reviews,
        }

    def review(
        self,
        *,
        owner_handle: str,
        slug: str,
        version: str,
        user_id: str,
        rating: int,
        body: str,
    ) -> dict[str, Any]:
        if rating < 1 or rating > 5:
            raise CommunityRegistryError(
                "registry_rating_invalid", "Review rating must be between 1 and 5"
            )
        clean_body = body.strip()
        if not clean_body or len(clean_body) > 4_000:
            raise CommunityRegistryError(
                "registry_review_invalid",
                "Review text must contain 1 to 4000 characters",
            )
        with self.database.transaction() as session:
            record = self._public_record(
                session, owner_handle=owner_handle, slug=slug, version=version
            )
            review = self.repository.upsert_review(
                session,
                version_id=record.id,
                user_id=user_id,
                rating=rating,
                body=clean_body,
                now=utc_now(),
            )
            feedback = self.repository.feedback(session, version_id=record.id)
            author = session.get(CommunityUser, user_id)
        if author is None:
            raise CommunityRegistryError(
                "registry_account_not_found", "Reviewer account was not found"
            )
        return {
            "schema_version": "community.feedback.v1",
            "review": _review_payload(review, author),
            **feedback,
        }

    def report(
        self,
        *,
        owner_handle: str,
        slug: str,
        version: str,
        user_id: str,
        reason: str,
        details: str,
    ) -> dict[str, Any]:
        clean_reason = reason.strip()
        clean_details = details.strip()
        if not clean_reason or len(clean_reason) > 64:
            raise CommunityRegistryError(
                "registry_report_invalid", "Report reason is invalid"
            )
        if len(clean_details) > 4_000:
            raise CommunityRegistryError(
                "registry_report_invalid", "Report details are too long"
            )
        with self.database.transaction() as session:
            record = self._public_record(
                session, owner_handle=owner_handle, slug=slug, version=version
            )
            report = self.repository.find_report(
                session,
                version_id=record.id,
                reporter_id=user_id,
                reason=clean_reason,
            )
            if report is None:
                report = self.repository.create_report(
                    session,
                    version_id=record.id,
                    reporter_id=user_id,
                    reason=clean_reason,
                    details=clean_details,
                    now=utc_now(),
                )
        return {
            "schema_version": "community.feedback.v1",
            "report_id": report.id,
            "status": report.status,
        }

    def _public_record(
        self, session: Any, *, owner_handle: str, slug: str, version: str
    ) -> CommunityAgentVersion:
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
        return row[1]


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
    *,
    fork_source: tuple[CommunityAgent, CommunityAgentVersion, Any] | None = None,
    feedback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = feedback or {
        "star_count": 0,
        "review_count": 0,
        "average_rating": 0.0,
    }
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
        "fork_of": _fork_payload(fork_source),
        "star_count": int(summary["star_count"]),
        "review_count": int(summary["review_count"]),
        "average_rating": float(summary["average_rating"]),
    }


def _fork_payload(
    source: tuple[CommunityAgent, CommunityAgentVersion, Any] | None,
) -> dict[str, str] | None:
    if source is None:
        return None
    agent, record, user = source
    return {
        "owner_handle": user.handle,
        "slug": agent.slug,
        "version": record.version,
        "source_hash": record.source_hash,
    }


def _review_payload(review: Any, user: Any) -> dict[str, Any]:
    return {
        "id": review.id,
        "author_handle": user.handle,
        "author_display_name": user.display_name,
        "rating": review.rating,
        "body": review.body,
        "created_at": review.created_at.isoformat(),
        "updated_at": review.updated_at.isoformat(),
    }
