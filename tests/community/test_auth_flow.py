"""End-to-end, fake-provider evidence for Community auth and account flows."""

from __future__ import annotations

import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from veyra_agent_platform.community.api.auth.security import (
    CSRF_COOKIE,
    CSRF_HEADER,
    REFRESH_COOKIE,
    SESSION_COOKIE,
)
from veyra_agent_platform.community.auth.errors import AuthenticationFailure
from veyra_agent_platform.community.auth.passwords import (
    PasswordManager,
    PasswordPolicyError,
)
from veyra_agent_platform.community.auth.sessions import ClientContext
from veyra_agent_platform.community.storage.identifiers import utc_now
from veyra_agent_platform.community.storage.schema import (
    CommunityMailOutbox,
    CommunitySession,
    CommunityVerificationCode,
)

from .conftest import CommunityHarness


def _request_registration_code(
    community: CommunityHarness, email: str = "Alice@Example.COM"
) -> str:
    response = community.client.post(
        "/api/v1/auth/registration-code",
        json={"email": email, "device_name": "Alice Mac"},
        headers={"X-Veyra-Device-Id": "alice-device"},
    )
    assert response.status_code == 202
    assert response.json() == {"schema_version": "community.auth.v1", "accepted": True}
    return community.mail.messages[-1].verification_code


def _register(
    community: CommunityHarness,
    *,
    email: str = "Alice@Example.COM",
    handle: str = "alice-maker",
    password: str = "correct-horse-battery-staple",
) -> None:
    code = _request_registration_code(community, email)
    response = community.client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "handle": handle,
            "password": password,
            "verification_code": code,
            "display_name": "Alice",
            "device_name": "Alice Mac",
        },
        headers={"X-Veyra-Device-Id": "alice-device"},
    )
    assert response.status_code == 201
    assert response.json() == {
        "schema_version": "community.auth.v1",
        "authenticated": True,
        "account": {
            "id": response.json()["account"]["id"],
            "email": email.lower(),
            "handle": handle,
            "display_name": "Alice",
            "avatar_url": None,
        },
    }


def _csrf_headers(community: CommunityHarness) -> dict[str, str]:
    token = community.client.cookies.get(CSRF_COOKIE)
    assert token is not None
    return {CSRF_HEADER: token}


@pytest.mark.parametrize(
    "password",
    [
        "1234567",
        "12345678",
        "PASSWORD",
        "Password1",
        "QWERTY123",
        "vEyRa1234",
        "Veyra-Password1",
    ],
)
def test_password_policy_rejects_short_and_common_passwords(password: str) -> None:
    with pytest.raises(PasswordPolicyError):
        PasswordManager.validate_new_password(password)


def test_password_policy_accepts_eight_and_max_length_passwords() -> None:
    manager = PasswordManager()
    for password in ("maplexyz", "密码安全" * 2, "x" * 64):
        password_hash = manager.hash_new_password(password)
        assert manager.verify(password_hash, password)

    with pytest.raises(PasswordPolicyError):
        manager.hash_new_password("x" * 65)


def test_password_policy_rejects_null_bytes() -> None:
    with pytest.raises(PasswordPolicyError, match="null byte"):
        PasswordManager.validate_new_password("safe\x00pwd")


def test_registration_accepts_eight_character_password_after_policy_failures(
    community: CommunityHarness,
) -> None:
    email = "password-policy@example.com"
    code = _request_registration_code(community, email)
    payload = {
        "email": email,
        "handle": "password-policy-user",
        "password": "1234567",
        "verification_code": code,
    }

    too_short = community.client.post("/api/v1/auth/register", json=payload)
    assert too_short.status_code == 422
    assert too_short.json() == {"detail": "password_policy_failed"}

    payload["password"] = "PASSWORD1"
    common = community.client.post("/api/v1/auth/register", json=payload)
    assert common.status_code == 422
    assert common.json() == {"detail": "password_policy_failed"}

    payload["password"] = "x" * 65
    too_long = community.client.post("/api/v1/auth/register", json=payload)
    assert too_long.status_code == 422
    assert too_long.json() == {"detail": "password_policy_failed"}

    payload["password"] = "maplexyz"
    accepted = community.client.post("/api/v1/auth/register", json=payload)
    assert accepted.status_code == 201


def test_registration_hmac_code_storage_and_account_profile(
    community: CommunityHarness,
) -> None:
    code = _request_registration_code(community)

    with community.database.transaction() as session:
        stored_code = session.scalar(select(CommunityVerificationCode))
        outbox = session.scalar(select(CommunityMailOutbox))
        assert stored_code is not None
        assert outbox is not None
        assert stored_code.email_normalized == "alice@example.com"
        assert stored_code.code_hmac != code
        assert len(stored_code.code_hmac) == 64
        assert stored_code.attempts == 0
        assert stored_code.consumed_at is None
        assert outbox.status == "delivered"
        assert outbox.provider_receipt == "fake-1"
        assert code not in str(stored_code.__dict__)
        assert code not in str(outbox.__dict__)

    response = community.client.post(
        "/api/v1/auth/register",
        json={
            "email": "ALICE@example.com",
            "handle": "alice-maker",
            "password": "correct-horse-battery-staple",
            "verification_code": code,
            "display_name": "Alice",
            "device_name": "Alice Mac",
        },
        headers={"X-Veyra-Device-Id": "alice-device"},
    )

    assert response.status_code == 201
    assert SESSION_COOKIE in response.headers["set-cookie"]
    assert REFRESH_COOKIE in response.headers["set-cookie"]
    assert CSRF_COOKIE in response.headers["set-cookie"]
    assert "token" not in response.text.lower()

    me = community.client.get("/api/v1/account/me")
    assert me.status_code == 200
    assert me.json()["account"] == {
        "id": response.json()["account"]["id"],
        "email": "alice@example.com",
        "handle": "alice-maker",
        "display_name": "Alice",
        "avatar_url": None,
    }

    unknown_identity = TestClient(community.app)
    denied = unknown_identity.get(
        "/api/v1/account/me", headers={"X-User-Id": response.json()["account"]["id"]}
    )
    assert denied.status_code == 401

    missing_csrf = community.client.patch(
        "/api/v1/account/profile", json={"display_name": "Alice New"}
    )
    assert missing_csrf.status_code == 403
    updated = community.client.patch(
        "/api/v1/account/profile",
        json={"display_name": "Alice New"},
        headers=_csrf_headers(community),
    )
    assert updated.status_code == 200
    assert updated.json()["account"]["display_name"] == "Alice New"

    sessions = community.client.get("/api/v1/account/sessions")
    assert sessions.status_code == 200
    assert sessions.json()["sessions"][0]["device_name"] == "Alice Mac"
    assert sessions.json()["sessions"][0]["current"] is True
    assert "ip" not in sessions.json()["sessions"][0]


def test_canonical_code_routes_optional_handle_and_me_patch(
    community: CommunityHarness,
) -> None:
    email = "private.owner@example.com"
    code_response = community.client.post(
        "/api/v1/auth/verification-codes",
        json={
            "email": email,
            "purpose": "registration",
            "device_name": "Owner phone",
        },
    )
    assert code_response.status_code == 202
    code = community.mail.messages[-1].verification_code

    registered = community.client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "verification_code": code,
            "display_name": "Original Name",
        },
    )
    assert registered.status_code == 201
    account = registered.json()["account"]
    assert re.fullmatch(r"veyra-[a-f0-9]{16}", account["handle"])
    assert "private" not in account["handle"]
    assert account["display_name"] == "Original Name"

    updated = community.client.patch(
        "/api/v1/account/me",
        json={"display_name": "Changed Name"},
        headers=_csrf_headers(community),
    )
    assert updated.status_code == 200
    assert updated.json()["account"]["display_name"] == "Changed Name"

    reset_request = community.client.post(
        "/api/v1/auth/verification-codes",
        json={"email": email, "purpose": "password_reset"},
    )
    assert reset_request.status_code == 202
    assert community.mail.messages[-1].purpose.value == "password_reset"

    invalid_purpose = community.client.post(
        "/api/v1/auth/verification-codes",
        json={"email": email, "purpose": "login"},
    )
    assert invalid_purpose.status_code == 422


def test_blank_registration_display_name_is_422_without_consuming_code(
    community: CommunityHarness,
) -> None:
    email = "blank-name@example.com"
    code = _request_registration_code(community, email)
    payload = {
        "email": email,
        "password": "correct-horse-battery-staple",
        "verification_code": code,
        "display_name": "   ",
    }

    invalid = community.client.post("/api/v1/auth/register", json=payload)
    assert invalid.status_code == 422

    payload["display_name"] = "Valid Name"
    registered = community.client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 201
    assert registered.json()["account"]["display_name"] == "Valid Name"


def test_login_has_generic_failures_and_code_requests_do_not_enumerate(
    community: CommunityHarness,
) -> None:
    _register(community)

    known = community.client.post(
        "/api/v1/auth/registration-code", json={"email": "alice@example.com"}
    )
    unknown = community.client.post(
        "/api/v1/auth/registration-code", json={"email": "nobody@example.com"}
    )
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()

    wrong_password = community.client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "wrong-password"},
    )
    unknown_account = community.client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "wrong-password"},
    )
    assert wrong_password.status_code == unknown_account.status_code == 401
    assert (
        wrong_password.json()
        == unknown_account.json()
        == {"detail": "invalid_credentials"}
    )


def test_login_accepts_desktop_loopback_origin(
    community: CommunityHarness,
) -> None:
    _register(community)
    community.client.cookies.clear()
    response = community.client.post(
        "/api/v1/auth/login",
        json={
            "email": "alice@example.com",
            "password": "correct-horse-battery-staple",
        },
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    assert response.status_code == 200
    assert response.json()["authenticated"] is True


def test_login_rejects_cross_site_origin(community: CommunityHarness) -> None:
    _register(community)
    community.client.cookies.clear()
    response = community.client.post(
        "/api/v1/auth/login",
        json={
            "email": "alice@example.com",
            "password": "correct-horse-battery-staple",
        },
        headers={"Origin": "https://attacker.example"},
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "origin_not_allowed"}


def test_refresh_rotation_detects_reuse_and_revokes_its_family(
    community: CommunityHarness,
) -> None:
    _register(community)
    old_refresh = community.client.cookies.get(REFRESH_COOKIE)
    old_csrf = community.client.cookies.get(CSRF_COOKIE)
    assert old_refresh is not None
    assert old_csrf is not None

    refreshed = community.client.post(
        "/api/v1/auth/refresh", headers=_csrf_headers(community)
    )
    assert refreshed.status_code == 200
    assert community.client.cookies.get(REFRESH_COOKIE) != old_refresh

    workflows = community.app.state.auth_workflows
    try:
        workflows.sessions.rotate(
            refresh_token=old_refresh,
            csrf_token=old_csrf,
            context=ClientContext(
                client_ip="testclient",
                device_fingerprint="alice-device",
                device_name="Alice Mac",
                user_agent="pytest",
            ),
        )
    except AuthenticationFailure:
        pass
    else:
        raise AssertionError("reused refresh token unexpectedly succeeded")

    assert community.client.get("/api/v1/account/me").status_code == 401
    with community.database.transaction() as session:
        sessions = session.scalars(select(CommunitySession)).all()
        assert len(sessions) == 2
        assert all(record.revoked_at is not None for record in sessions)
        assert all(record.revoke_reason == "refresh_token_reuse" for record in sessions)


def test_logout_then_login_and_refresh_smoke(community: CommunityHarness) -> None:
    _register(community)

    logout = community.client.post(
        "/api/v1/auth/logout", headers=_csrf_headers(community)
    )
    assert logout.status_code == 204
    assert community.client.get("/api/v1/account/me").status_code == 401

    login = community.client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "correct-horse-battery-staple"},
    )
    assert login.status_code == 200
    refreshed = community.client.post(
        "/api/v1/auth/refresh", headers=_csrf_headers(community)
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["authenticated"] is True


def test_logout_with_expired_access_uses_refresh_lineage(
    community: CommunityHarness,
) -> None:
    _register(community)
    with community.database.transaction() as session:
        record = session.scalar(select(CommunitySession))
        assert record is not None
        record.session_expires_at = utc_now() - timedelta(seconds=1)

    assert community.client.get("/api/v1/account/me").status_code == 401
    logout = community.client.post(
        "/api/v1/auth/logout",
        headers={**_csrf_headers(community), "Origin": "http://testserver"},
    )
    assert logout.status_code == 204
    assert community.client.cookies.get(SESSION_COOKIE) is None
    assert community.client.cookies.get(REFRESH_COOKIE) is None
    assert community.client.cookies.get(CSRF_COOKIE) is None

    with community.database.transaction() as session:
        record = session.scalar(select(CommunitySession))
        assert record is not None
        assert record.revoked_at is not None
        assert record.revoke_reason == "logout"


def test_refresh_server_csrf_mismatch_is_forbidden_not_internal_error(
    community: CommunityHarness,
) -> None:
    _register(community)
    bad_csrf = "csrf-not-bound-to-this-session"
    community.client.cookies.set(
        CSRF_COOKIE,
        bad_csrf,
        domain="testserver.local",
        path="/",
    )
    response = community.client.post(
        "/api/v1/auth/refresh", headers={CSRF_HEADER: bad_csrf}
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "csrf_failed"}


def test_logout_with_invalid_refresh_still_clears_local_cookies(
    community: CommunityHarness,
) -> None:
    _register(community)
    csrf = community.client.cookies.get(CSRF_COOKIE)
    assert csrf is not None
    community.client.cookies.set(
        REFRESH_COOKIE,
        "invalid-refresh-token",
        domain="testserver.local",
        path="/",
    )
    response = community.client.post("/api/v1/auth/logout", headers={CSRF_HEADER: csrf})
    assert response.status_code == 204
    assert community.client.cookies.get(SESSION_COOKIE) is None
    assert community.client.cookies.get(REFRESH_COOKIE) is None
    assert community.client.cookies.get(CSRF_COOKIE) is None


def test_password_reset_is_anti_enumeration_and_revokes_existing_sessions(
    community: CommunityHarness,
) -> None:
    _register(community)
    existing = community.client.post(
        "/api/v1/auth/password-reset/request", json={"email": "alice@example.com"}
    )
    nonexistent = community.client.post(
        "/api/v1/auth/password-reset/request", json={"email": "nobody@example.com"}
    )
    assert existing.status_code == nonexistent.status_code == 202
    assert existing.json() == nonexistent.json()

    reset_code = community.mail.messages[-1].verification_code
    blocked_reset = community.client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "email": "alice@example.com",
            "verification_code": reset_code,
            "new_password": "PASSWORD1",
        },
    )
    assert blocked_reset.status_code == 422
    assert blocked_reset.json() == {"detail": "password_policy_failed"}

    too_long_reset = community.client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "email": "alice@example.com",
            "verification_code": reset_code,
            "new_password": "x" * 65,
        },
    )
    assert too_long_reset.status_code == 422
    assert too_long_reset.json() == {"detail": "password_policy_failed"}

    reset = community.client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "email": "alice@example.com",
            "verification_code": reset_code,
            "new_password": "maplexyz",
        },
    )
    assert reset.status_code == 200
    assert reset.json() == {"schema_version": "community.auth.v1", "reset": True}
    assert community.client.get("/api/v1/account/me").status_code == 401

    old_password = community.client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "correct-horse-battery-staple"},
    )
    assert old_password.status_code == 401
    new_password = community.client.post(
        "/api/v1/auth/login",
        json={
            "email": "alice@example.com",
            "password": "maplexyz",
        },
    )
    assert new_password.status_code == 200


def test_failed_code_attempts_are_durable_and_exhaust_the_code(
    community: CommunityHarness,
) -> None:
    correct_code = _request_registration_code(community, "attempts@example.com")
    payload = {
        "email": "attempts@example.com",
        "handle": "attempts-user",
        "password": "correct-horse-battery-staple",
        "verification_code": "000000",
    }
    for _ in range(5):
        response = community.client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 400
        assert response.json() == {"detail": "registration_unavailable"}
    payload["verification_code"] = correct_code
    exhausted = community.client.post("/api/v1/auth/register", json=payload)
    assert exhausted.status_code == 400

    with community.database.transaction() as session:
        record = session.scalar(
            select(CommunityVerificationCode).where(
                CommunityVerificationCode.email_normalized == "attempts@example.com"
            )
        )
        assert record is not None
        assert record.attempts == 5
        assert record.consumed_at is not None
