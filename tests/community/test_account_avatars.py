"""HTTP evidence for authenticated Community avatar lifecycle."""

from __future__ import annotations

from veyra_agent_platform.community.api.auth.security import CSRF_COOKIE, CSRF_HEADER

from .conftest import CommunityHarness

_PNG = b"\x89PNG\r\n\x1a\nfirst-avatar"
_PNG_REPLACEMENT = b"\x89PNG\r\n\x1a\nreplacement-avatar"


def _register(community: CommunityHarness) -> str:
    email = "avatar-owner@example.com"
    code_request = community.client.post(
        "/api/v1/auth/verification-codes",
        json={"email": email, "purpose": "registration"},
    )
    assert code_request.status_code == 202
    registered = community.client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "verification_code": community.mail.messages[-1].verification_code,
        },
    )
    assert registered.status_code == 201
    return registered.json()["account"]["id"]


def _csrf_headers(community: CommunityHarness) -> dict[str, str]:
    token = community.client.cookies.get(CSRF_COOKIE)
    assert token is not None
    return {CSRF_HEADER: token}


def _upload(
    community: CommunityHarness, content: bytes, media_type: str = "image/png"
):
    return community.client.post(
        "/api/v1/account/avatar",
        files={"avatar": ("untrusted-name.png", content, media_type)},
        headers=_csrf_headers(community),
    )


def test_avatar_upload_get_replace_and_delete(community: CommunityHarness) -> None:
    user_id = _register(community)

    uploaded = _upload(community, _PNG)
    assert uploaded.status_code == 200
    assert uploaded.json()["account"]["avatar_url"] == f"/api/v1/avatars/{user_id}"

    displayed = community.client.get(f"/api/v1/avatars/{user_id}")
    assert displayed.status_code == 200
    assert displayed.content == _PNG
    assert displayed.headers["content-type"] == "image/png"
    assert displayed.headers["cache-control"] == "public, max-age=3600"
    etag = displayed.headers["etag"]
    assert community.client.get(
        f"/api/v1/avatars/{user_id}", headers={"If-None-Match": etag}
    ).status_code == 304

    replaced = _upload(community, _PNG_REPLACEMENT)
    assert replaced.status_code == 200
    replacement_display = community.client.get(f"/api/v1/avatars/{user_id}")
    assert replacement_display.content == _PNG_REPLACEMENT
    storage_root = community.app.state.settings.avatar_storage_root
    assert len(list(storage_root.iterdir())) == 1

    assert community.client.delete("/api/v1/account/avatar").status_code == 403

    deleted = community.client.delete(
        "/api/v1/account/avatar", headers=_csrf_headers(community)
    )
    assert deleted.status_code == 204
    assert community.client.get(f"/api/v1/avatars/{user_id}").status_code == 404
    me = community.client.get("/api/v1/account/me")
    assert me.json()["account"]["avatar_url"] is None
    assert list(storage_root.iterdir()) == []


def test_avatar_rejects_unauthenticated_csrf_and_invalid_content(
    community: CommunityHarness,
) -> None:
    unauthenticated = community.client.post(
        "/api/v1/account/avatar",
        files={"avatar": ("avatar.png", _PNG, "image/png")},
    )
    assert unauthenticated.status_code == 401

    _register(community)
    missing_csrf = community.client.post(
        "/api/v1/account/avatar",
        files={"avatar": ("avatar.png", _PNG, "image/png")},
    )
    assert missing_csrf.status_code == 403
    wrong_origin = community.client.post(
        "/api/v1/account/avatar",
        files={"avatar": ("avatar.png", _PNG, "image/png")},
        headers={**_csrf_headers(community), "Origin": "https://attacker.example"},
    )
    assert wrong_origin.status_code == 403

    assert _upload(community, b"").status_code == 422
    assert _upload(community, b"GIF89a-not-an-avatar", "image/gif").status_code == 422
    assert _upload(community, _PNG, "image/jpeg").status_code == 422
    assert _upload(community, _PNG + b"x" * (2 * 1024 * 1024)).status_code == 422
