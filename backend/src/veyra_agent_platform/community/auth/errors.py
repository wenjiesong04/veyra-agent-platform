"""Typed failures deliberately mapped to generic public auth responses."""

from __future__ import annotations


class AuthenticationFailure(Exception):
    """Authentication did not establish a valid account session."""


class CsrfFailure(AuthenticationFailure):
    """A state-changing cookie request did not prove same-site intent."""


class VerificationCodeFailure(Exception):
    """A one-time code is missing, invalid, expired, or exhausted."""


class RateLimited(AuthenticationFailure):
    """A durable rate policy denied this public authentication operation."""


class RegistrationUnavailable(Exception):
    """Registration cannot create an account without exposing exact cause."""
