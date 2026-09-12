"""Cookie, CSRF, origin, and request-context helpers for Community auth."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import timedelta
from typing import cast
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response, status

from ...auth.errors import AuthenticationFailure, CsrfFailure
from ...auth.sessions import AuthenticatedSession, ClientContext, SessionIssue
from ...auth.workflows import CommunityAuthWorkflows
from ...config import CommunitySettings

DEVELOPMENT_SESSION_COOKIE = "veyra-session"
DEVELOPMENT_REFRESH_COOKIE = "veyra-refresh"
DEVELOPMENT_CSRF_COOKIE = "veyra-csrf"
PRODUCTION_SESSION_COOKIE = "__Host-veyra-session"
PRODUCTION_REFRESH_COOKIE = "__Host-veyra-refresh"
PRODUCTION_CSRF_COOKIE = "__Host-veyra-csrf"

# Compatibility aliases describe the local browser contract. Runtime code must
# always resolve names from CommunitySettings through auth_cookie_names().
SESSION_COOKIE = DEVELOPMENT_SESSION_COOKIE
REFRESH_COOKIE = DEVELOPMENT_REFRESH_COOKIE
CSRF_COOKIE = DEVELOPMENT_CSRF_COOKIE
CSRF_HEADER = "X-CSRF-Token"
_LOOPBACK_ORIGIN_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class AuthCookieNames:
    """Mode-specific browser cookie names exported for clients and tests."""

    session: str
    refresh: str
    csrf: str


DEVELOPMENT_AUTH_COOKIE_NAMES = AuthCookieNames(
    session=DEVELOPMENT_SESSION_COOKIE,
    refresh=DEVELOPMENT_REFRESH_COOKIE,
    csrf=DEVELOPMENT_CSRF_COOKIE,
)
PRODUCTION_AUTH_COOKIE_NAMES = AuthCookieNames(
    session=PRODUCTION_SESSION_COOKIE,
    refresh=PRODUCTION_REFRESH_COOKIE,
    csrf=PRODUCTION_CSRF_COOKIE,
)


def auth_cookie_names(settings: CommunitySettings) -> AuthCookieNames:
    """Return the only cookie-name set valid for this deployment mode."""

    if settings.secure_cookies:
        return PRODUCTION_AUTH_COOKIE_NAMES
    return DEVELOPMENT_AUTH_COOKIE_NAMES


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

    names = auth_cookie_names(get_settings(request))
    session_token = request.cookies.get(names.session)
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


def require_moderator(request: Request, authenticated: AuthenticatedSession) -> None:
    """Require a handle explicitly configured for Community moderation."""

    profile = request.app.state.account_profiles.get(authenticated.user_id)
    settings = get_settings(request)
    if profile is None or profile.handle.lower() not in settings.moderator_handle_set:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="moderator_required"
        )


def require_csrf(
    request: Request,
    authenticated: AuthenticatedSession,
    settings: CommunitySettings,
) -> None:
    """Protect an authenticated unsafe request with origin and double-submit CSRF."""

    require_trusted_origin(request, settings)
    cookie_token = request.cookies.get(auth_cookie_names(settings).csrf)
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
    cookie_token = request.cookies.get(auth_cookie_names(settings).csrf)
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
    if normalized_origin in allowed_origins:
        return
    if settings.mode != "production" and _is_loopback_http_origin(origin):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="origin_not_allowed"
    )


def _is_loopback_http_origin(origin: str) -> bool:
    """Allow local Desktop/Community Vite origins in development and tests."""

    parsed = urlsplit(origin)
    hostname = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "http"
        and hostname in _LOOPBACK_ORIGIN_HOSTS
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )


def set_auth_cookies(
    response: Response, issue: SessionIssue, settings: CommunitySettings
) -> None:
    """Set HttpOnly access/refresh cookies and a session-bound CSRF cookie."""

    secure = settings.secure_cookies
    names = auth_cookie_names(settings)
    response.set_cookie(
        names.session,
        issue.secrets.session_token,
        max_age=_seconds(settings.session_ttl_minutes, "minutes"),
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        names.refresh,
        issue.secrets.refresh_token,
        max_age=_seconds(settings.refresh_ttl_days, "days"),
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        names.csrf,
        issue.secrets.csrf_token,
        max_age=_seconds(settings.refresh_ttl_days, "days"),
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response: Response, settings: CommunitySettings) -> None:
    """Expire every cookie used for Community account authentication."""

    names = auth_cookie_names(settings)
    for cookie_name in (names.session, names.refresh, names.csrf):
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
