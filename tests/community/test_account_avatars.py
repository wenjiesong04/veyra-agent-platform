"""HTTP evidence for authenticated Community avatar lifecycle."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from veyra_agent_platform.community.accounts.avatars import AccountAvatarService
from veyra_agent_platform.community.api.auth.security import CSRF_COOKIE, CSRF_HEADER
from veyra_agent_platform.community.storage.avatar_storage import LocalAvatarStorage

from .conftest import CommunityHarness


def _png(*, color: str, width: int = 1, height: int = 1) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), color=color).save(output, format="PNG")
    return output.getvalue()


_PNG = _png(color="red")
_PNG_REPLACEMENT = _png(color="blue")


class OldDeleteFailsStorage(LocalAvatarStorage):
    """Test double that fails only stale-object cleanup after a replacement."""

    def __init__(self, root) -> None:
        super().__init__(root)
        self.fail_storage_id: str | None = None

    def delete(self, storage_id: str) -> None:
        if storage_id == self.fail_storage_id:
            raise OSError("simulated old-object cleanup failure")
        super().delete(storage_id)


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


def _upload(community: CommunityHarness, content: bytes, media_type: str = "image/png"):
    return community.client.post(
        "/api/v1/account/avatar",
        files={"avatar": ("untrusted-name.png", content, media_type)},
        headers=_csrf_headers(community),
    )


def test_avatar_upload_get_replace_and_delete(community: CommunityHarness) -> None:
    user_id = _register(community)

    uploaded = _upload(community, _PNG)
    assert uploaded.status_code == 200
    first_url = uploaded.json()["account"]["avatar_url"]
    assert first_url.startswith(f"/api/v1/avatars/{user_id}?v=")
    assert not first_url.startswith("http://127.0.0.1:5173")

    displayed = community.client.get(f"/api/v1/avatars/{user_id}")
    assert displayed.status_code == 200
    assert displayed.content == _PNG
    assert displayed.headers["content-type"] == "image/png"
    assert displayed.headers["cache-control"] == "public, max-age=3600"
    etag = displayed.headers["etag"]
    assert (
        community.client.get(
            f"/api/v1/avatars/{user_id}", headers={"If-None-Match": etag}
        ).status_code
        == 304
    )

    replaced = _upload(community, _PNG_REPLACEMENT)
    assert replaced.status_code == 200
    assert replaced.json()["account"]["avatar_url"] != first_url
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


def test_replace_keeps_committed_new_object_when_old_cleanup_fails(
    community: CommunityHarness,
) -> None:
    storage = OldDeleteFailsStorage(community.app.state.settings.avatar_storage_root)
    community.app.state.account_avatars = AccountAvatarService(
        community.database, storage
    )
    user_id = _register(community)

    assert _upload(community, _PNG).status_code == 200
    storage.fail_storage_id = next(storage._root.iterdir()).name
    replaced = _upload(community, _PNG_REPLACEMENT)

    assert replaced.status_code == 200
    displayed = community.client.get(f"/api/v1/avatars/{user_id}")
    assert displayed.status_code == 200
    assert displayed.content == _PNG_REPLACEMENT
    assert len(list(storage._root.iterdir())) == 2


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
    assert _upload(community, b"\x89PNG\r\n\x1a\nnot-an-image").status_code == 422
    assert _upload(community, _PNG, "image/jpeg").status_code == 422
    assert _upload(community, _PNG + b"x" * (2 * 1024 * 1024)).status_code == 422
    oversized = _png(color="white", width=2049, height=2049)
    assert _upload(community, oversized).status_code == 422
