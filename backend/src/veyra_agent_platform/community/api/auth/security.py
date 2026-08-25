"""Cookie, CSRF, origin, and request-context helpers for Community auth."""

from __future__ import annotations

import hmac
from datetime import timedelta
from typing import cast
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response, status

from ...auth.errors import AuthenticationFailure, CsrfFailure
from ...auth.sessions import AuthenticatedSession, ClientContext, SessionIssue
from ...auth.workflows import CommunityAuthWorkflows
from ...config import CommunitySettings

SESSION_COOKIE = "__Host-veyra-session"
REFRESH_COOKIE = "__Host-veyra-refresh"
CSRF_COOKIE = "__Host-veyra-csrf"
CSRF_HEADER = "X-CSRF-Token"


def get_workflows(request: Request) -> CommunityAuthWorkflows:
    """Read the configured server-owned workflows from application state."""

    return cast(CommunityAuthWorkflows, request.app.state.auth_workflows)


def get_settings(request: Request) -> CommunitySettings:
    """Read Community deployment configuration from application state."""

    return cast(CommunitySettings, request.app.state.settings)


def request_context(request: Request, device_name: str | None) -> ClientContext:
    """Capture bounded metadata for rate controls, never as user identity."""

    client_ip = request.client.host if request.client is not None else "unknown"
    user_agent = _clean_header(
        request.headers.get("user-agent"), fallback="unknown", limit=512
    )
    device_identifier = _clean_header(
        request.headers.get("x-veyra-device-id"), fallback=user_agent, limit=128
    )
    return ClientContext(
        client_ip=client_ip,
        device_fingerprint=device_identifier,
        device_name=_clean_device_name(device_name),
        user_agent=user_agent,
    )


def authenticate_request(request: Request) -> AuthenticatedSession:
    """Authenticate only the opaque HttpOnly session cookie."""

    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication_required",
        )
    try:
        return get_workflows(request).sessions.authenticate(session_token)
    except AuthenticationFailure as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication_required",
        ) from error


def require_csrf(
    request: Request,
    authenticated: AuthenticatedSession,
    settings: CommunitySettings,
) -> None:
    """Protect an authenticated unsafe request with origin and double-submit CSRF."""

    require_trusted_origin(request, settings)
    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get(CSRF_HEADER)
    if (
        cookie_token is None
        or header_token is None
        or not hmac.compare_digest(cookie_token, header_token)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf_failed")
    try:
        get_workflows(request).sessions.require_csrf(authenticated, header_token)
    except CsrfFailure as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="csrf_failed"
        ) from error


def require_refresh_csrf(request: Request, settings: CommunitySettings) -> str:
    """Check browser CSRF evidence before a refresh-cookie rotation request."""

    require_trusted_origin(request, settings)
    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get(CSRF_HEADER)
    if (
        cookie_token is None
        or header_token is None
        or not hmac.compare_digest(cookie_token, header_token)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf_failed")
    return header_token


def require_trusted_origin(request: Request, settings: CommunitySettings) -> None:
    """Reject an explicit cross-site Origin while allowing non-browser API clients."""

    origin = request.headers.get("origin")
    if origin is None:
        return
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="origin_not_allowed"
        )
    normalized_origin = f"{parsed.scheme}://{parsed.netloc}".lower()
    request_origin = f"{request.url.scheme}://{request.url.netloc}".lower()
    allowed_origins = {request_origin}
    if settings.public_origin is not None:
        allowed_origins.add(settings.public_origin.lower())
    if normalized_origin not in allowed_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="origin_not_allowed"
        )


def set_auth_cookies(
    response: Response, issue: SessionIssue, settings: CommunitySettings
) -> None:
    """Set HttpOnly access/refresh cookies and a session-bound CSRF cookie."""

    secure = settings.secure_cookies
    response.set_cookie(
        SESSION_COOKIE,
        issue.secrets.session_token,
        max_age=_seconds(settings.session_ttl_minutes, "minutes"),
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        issue.secrets.refresh_token,
        max_age=_seconds(settings.refresh_ttl_days, "days"),
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        issue.secrets.csrf_token,
        max_age=_seconds(settings.refresh_ttl_days, "days"),
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response: Response, settings: CommunitySettings) -> None:
    """Expire every cookie used for Community account authentication."""

    for cookie_name in (SESSION_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(
            cookie_name,
            path="/",
            secure=settings.secure_cookies,
            samesite="lax",
        )


def _seconds(value: int, unit: str) -> int:
    duration = timedelta(**{unit: value})
    return int(duration.total_seconds())


def _clean_header(value: str | None, *, fallback: str, limit: int) -> str:
    if value is None:
        return fallback
    cleaned = value.replace("\r", "").replace("\n", "").replace("\x00", "").strip()
    return cleaned[:limit] or fallback


def _clean_device_name(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.replace("\r", "").replace("\n", "").replace("\x00", "").strip()
    return cleaned[:120] or None
