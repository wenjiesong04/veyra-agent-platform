"""Publisher confirmation is bound to the authenticated POST, not a prior UI GET."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from starlette.datastructures import UploadFile

from .conftest import CommunityHarness
from .test_agent_registry import _source_bytes
from .test_auth_flow import _csrf_headers, _register
from .test_plugin_registry import _plugin_archive


def _package(kind: str) -> tuple[str, bytes, str]:
    if kind == "agent":
        return "review.vagent.yaml", _source_bytes(), "application/yaml"
    return "research.vplugin.zip", _plugin_archive(), "application/zip"


def _registry(community: CommunityHarness, kind: str):
    return (
        community.app.state.community_registry
        if kind == "agent"
        else community.app.state.community_plugin_registry
    )


@pytest.mark.parametrize("kind", ["agent", "plugin"])
def test_publication_rejects_another_confirmed_account_before_reading_or_publishing(
    community: CommunityHarness, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    community.app.state.database_ready = True
    _register(community, email="publisher-a@example.com", handle="publisher-a")
    publisher_a = community.client.get("/api/v1/account/me").json()["account"]["id"]
    cookies_a = dict(community.client.cookies.items())
    _register(community, email="publisher-b@example.com", handle="publisher-b")
    publisher_b = community.client.get("/api/v1/account/me").json()["account"]["id"]
    assert publisher_a != publisher_b
    community.client.cookies.clear()
    community.client.cookies.update(cookies_a)
    registry = _registry(community, kind)
    publish = Mock(wraps=registry.publish)
    monkeypatch.setattr(registry, "publish", publish)
    read = AsyncMock(side_effect=AssertionError("Rejected packages must not be read"))
    monkeypatch.setattr(UploadFile, "read", read)

    response = community.client.post(
        f"/api/v1/registry/{kind}s",
        data={"expected_publisher_id": publisher_b},
        files={"package": _package(kind)},
        headers=_csrf_headers(community),
    )

    assert response.status_code == 409, response.text
    assert response.json() == {"detail": "publication_account_changed"}
    read.assert_not_awaited()
    publish.assert_not_called()
    assert community.client.get(f"/api/v1/registry/{kind}s").json()["entries"] == []
    assert (
        community.client.get("/api/v1/account/me").json()["account"]["id"]
        == publisher_a
    )


@pytest.mark.parametrize("kind", ["agent", "plugin"])
def test_publication_accepts_the_confirmed_authenticated_publisher(
    community: CommunityHarness, kind: str
) -> None:
    community.app.state.database_ready = True
    _register(community, handle="confirmed-publisher")
    publisher_id = community.client.get("/api/v1/account/me").json()["account"]["id"]

    response = community.client.post(
        f"/api/v1/registry/{kind}s",
        data={"expected_publisher_id": publisher_id},
        files={"package": _package(kind)},
        headers=_csrf_headers(community),
    )

    assert response.status_code == 201, response.text
    entry = response.json()
    assert entry["owner_handle"] == "confirmed-publisher"
    assert entry["status"] == "published"
    listed = community.client.get(f"/api/v1/registry/{kind}s").json()["entries"]
    assert len(listed) == 1
    assert listed[0]["owner_handle"] == "confirmed-publisher"
    assert listed[0]["version"] == entry["version"]


@pytest.mark.parametrize("kind", ["agent", "plugin"])
def test_publication_checks_authentication_and_csrf_before_publisher_binding(
    community: CommunityHarness, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    community.app.state.database_ready = True
    registry = _registry(community, kind)
    publish = Mock(wraps=registry.publish)
    monkeypatch.setattr(registry, "publish", publish)
    read = AsyncMock(
        side_effect=AssertionError("Unauthorized packages must not be read")
    )
    monkeypatch.setattr(UploadFile, "read", read)
    payload = {"expected_publisher_id": "another-account"}
    anonymous = community.client.post(
        f"/api/v1/registry/{kind}s",
        data=payload,
        files={"package": _package(kind)},
    )
    assert anonymous.status_code == 401
    assert anonymous.json()["detail"] == "authentication_required"
    _register(community, handle="csrf-publisher")
    no_csrf = community.client.post(
        f"/api/v1/registry/{kind}s",
        data=payload,
        files={"package": _package(kind)},
    )
    assert no_csrf.status_code == 403
    assert no_csrf.json()["detail"] == "csrf_failed"
    read.assert_not_awaited()
    publish.assert_not_called()
    assert community.client.get(f"/api/v1/registry/{kind}s").json()["entries"] == []
