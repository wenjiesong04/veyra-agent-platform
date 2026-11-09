"""Pydantic contracts for authenticated Community account management."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from ...auth.sessions import DeviceSession
from ..auth.schemas import AccountResponse


class AccountApiModel(BaseModel):
    """Forbid unrecognized fields at account-management boundaries."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MeResponse(AccountApiModel):
    schema_version: Literal["community.account.v1"] = "community.account.v1"
    account: AccountResponse


class ProfileUpdateRequest(AccountApiModel):
    handle: str | None = None
    display_name: str | None = None

    @model_validator(mode="after")
    def _require_change(self) -> ProfileUpdateRequest:
        if self.handle is None and self.display_name is None:
            raise ValueError("at least one profile field is required")
        return self


class DeviceSessionResponse(AccountApiModel):
    id: str
    device_name: str | None
    user_agent: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    current: bool

    @classmethod
    def from_session(cls, session: DeviceSession) -> DeviceSessionResponse:
        return cls(
            id=session.id,
            device_name=session.device_name,
            user_agent=session.user_agent,
            created_at=session.created_at,
            last_seen_at=session.last_seen_at,
            expires_at=session.expires_at,
            current=session.current,
        )


class SessionListResponse(AccountApiModel):
    schema_version: Literal["community.account.v1"] = "community.account.v1"
    sessions: tuple[DeviceSessionResponse, ...]
