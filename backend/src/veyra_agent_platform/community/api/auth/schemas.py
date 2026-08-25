"""Pydantic contracts for versioned Community email/password routes."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from ...accounts.identifiers import normalize_email, normalize_handle
from ...accounts.profiles import AccountProfile

_SIX_DIGITS = re.compile(r"^\d{6}$")


class ApiModel(BaseModel):
    """Forbid unexpected JSON fields at the Community auth boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EmailRequest(ApiModel):
    email: str
    device_name: str | None = None

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class RegisterRequest(EmailRequest):
    handle: str
    password: str
    verification_code: str
    display_name: str | None = None

    @field_validator("handle")
    @classmethod
    def _normalize_handle(cls, value: str) -> str:
        return normalize_handle(value)

    @field_validator("verification_code")
    @classmethod
    def _validate_code(cls, value: str) -> str:
        if not _SIX_DIGITS.fullmatch(value):
            raise ValueError("verification code must contain six digits")
        return value


class LoginRequest(EmailRequest):
    password: str


class PasswordResetConfirmRequest(EmailRequest):
    verification_code: str
    new_password: str

    @field_validator("verification_code")
    @classmethod
    def _validate_code(cls, value: str) -> str:
        if not _SIX_DIGITS.fullmatch(value):
            raise ValueError("verification code must contain six digits")
        return value


class AcceptedResponse(ApiModel):
    schema_version: Literal["community.auth.v1"] = "community.auth.v1"
    accepted: Literal[True] = True


class AccountResponse(ApiModel):
    id: str
    email: str
    handle: str
    display_name: str | None

    @classmethod
    def from_profile(cls, profile: AccountProfile) -> AccountResponse:
        return cls(
            id=profile.id,
            email=profile.email,
            handle=profile.handle,
            display_name=profile.display_name,
        )


class AuthenticatedResponse(ApiModel):
    schema_version: Literal["community.auth.v1"] = "community.auth.v1"
    authenticated: Literal[True] = True
    account: AccountResponse


class ResetCompleteResponse(ApiModel):
    schema_version: Literal["community.auth.v1"] = "community.auth.v1"
    reset: Literal[True] = True
