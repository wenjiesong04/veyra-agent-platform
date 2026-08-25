"""Repository for private Community account records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .identifiers import new_uuid7
from .schema import CommunityUser


class CommunityUserRepository:
    """Keep account SQL operations separate from authentication workflows."""

    def find_by_email(
        self, session: Session, email_normalized: str
    ) -> CommunityUser | None:
        return session.scalar(
            select(CommunityUser).where(
                CommunityUser.email_normalized == email_normalized
            )
        )

    def find_by_handle(self, session: Session, handle: str) -> CommunityUser | None:
        return session.scalar(
            select(CommunityUser).where(CommunityUser.handle == handle)
        )

    def find_by_id(self, session: Session, user_id: str) -> CommunityUser | None:
        return session.get(CommunityUser, user_id)

    def create(
        self,
        session: Session,
        *,
        email_normalized: str,
        handle: str,
        password_hash: str,
        display_name: str | None,
        now: datetime,
    ) -> CommunityUser:
        user = CommunityUser(
            id=new_uuid7(),
            email_normalized=email_normalized,
            handle=handle,
            display_name=display_name,
            password_hash=password_hash,
            email_verified_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        session.flush()
        return user

    def update_profile(
        self,
        session: Session,
        user: CommunityUser,
        *,
        handle: str | None,
        display_name: str | None,
        now: datetime,
    ) -> CommunityUser:
        if handle is not None:
            user.handle = handle
        if display_name is not None:
            user.display_name = display_name
        user.updated_at = now
        session.flush()
        return user

    def update_password(
        self,
        session: Session,
        user: CommunityUser,
        *,
        password_hash: str,
        now: datetime,
    ) -> None:
        user.password_hash = password_hash
        user.updated_at = now
        session.flush()
