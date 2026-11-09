"""Owned Plugin versions survive moderation without leaking to other accounts."""

from __future__ import annotations

import io
import zipfile

import pytest
import yaml

from .conftest import CommunityHarness
from .test_auth_flow import _csrf_headers, _register
from .test_plugin_registry import _plugin_archive


def _version_archive(version: str) -> bytes:
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(_plugin_archive())) as original,
        zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as updated,
    ):
        for filename in original.namelist():
            content = original.read(filename)
            if filename == "plugin.vplugin.yaml":
                manifest = yaml.safe_load(content)
                manifest["version"] = version
                manifest["skills"][0]["reference"] = (
                    f"veyra.skill.research-pack@{version}"
                )
                content = yaml.safe_dump(manifest, sort_keys=False).encode("utf-8")
            updated.writestr(filename, content)
    return output.getvalue()


def _publish(community: CommunityHarness, version: str) -> dict[str, object]:
    account_id = community.client.get("/api/v1/account/me").json()["account"]["id"]
    response = community.client.post(
        "/api/v1/registry/plugins",
        data={"expected_publisher_id": account_id},
        files={
            "package": (
                "research.vplugin.zip",
                _version_archive(version),
                "application/zip",
            )
        },
        headers=_csrf_headers(community),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_owned_plugins_include_all_versions_and_states_only_for_the_current_account(
    community: CommunityHarness,
) -> None:
    community.app.state.database_ready = True
    _register(community, email="owner-a@example.com", handle="plugin-owner-a")
    cookies_a = dict(community.client.cookies.items())
    published = _publish(community, "1.0.0")
    assert published["status"] == "published"
    registry = community.app.state.community_plugin_registry
    registry.require_moderation = True
    pending = _publish(community, "2.0.0")
    assert pending["status"] == "quarantined"
    _publish(community, "3.0.0")
    with community.database.transaction() as session:
        row = registry.repository.find_version_for_moderation(
            session,
            owner_handle="plugin-owner-a",
            slug="research",
            version="3.0.0",
        )
        assert row is not None
        registry.repository.set_version_status(
            session, row[1], status="rejected", published_at=None
        )

    _register(community, email="owner-b@example.com", handle="plugin-owner-b")
    assert community.client.get("/api/v1/registry/mine/plugins").json()["entries"] == []
    _publish(community, "4.0.0")
    own_b = community.client.get("/api/v1/registry/mine/plugins")
    assert own_b.status_code == 200
    assert [
        (entry["owner_handle"], entry["version"], entry["status"])
        for entry in own_b.json()["entries"]
    ] == [("plugin-owner-b", "4.0.0", "quarantined")]

    community.client.cookies.clear()
    community.client.cookies.update(cookies_a)
    own_a = community.client.get("/api/v1/registry/mine/plugins")
    assert own_a.status_code == 200
    assert own_a.json()["schema_version"] == "community.plugin.registry.v1"
    entries = own_a.json()["entries"]
    assert [(entry["version"], entry["status"]) for entry in entries] == [
        ("3.0.0", "rejected"),
        ("2.0.0", "quarantined"),
        ("1.0.0", "published"),
    ]
    assert all(entry["owner_handle"] == "plugin-owner-a" for entry in entries)
    assert community.client.get("/api/v1/registry/mine/plugins").json() == own_a.json()
    limited = community.client.get("/api/v1/registry/mine/plugins?limit=1")
    assert [entry["version"] for entry in limited.json()["entries"]] == ["3.0.0"]

    community.client.cookies.clear()
    public = community.client.get("/api/v1/registry/plugins")
    assert public.status_code == 200
    assert [
        (entry["owner_handle"], entry["version"], entry["status"])
        for entry in public.json()["entries"]
    ] == [("plugin-owner-a", "1.0.0", "published")]
    assert (
        community.client.get(
            "/api/v1/registry/plugins/plugin-owner-a/research/versions/2.0.0"
        ).status_code
        == 404
    )


def test_owned_plugins_require_authentication(community: CommunityHarness) -> None:
    community.app.state.database_ready = True
    response = community.client.get("/api/v1/registry/mine/plugins")
    assert response.status_code == 401
    assert response.json() == {"detail": "authentication_required"}


@pytest.mark.parametrize("limit", [0, 101])
def test_owned_plugins_enforce_the_bounded_list_limit(
    community: CommunityHarness, limit: int
) -> None:
    community.app.state.database_ready = True
    _register(community, handle="plugin-limit-owner")
    response = community.client.get(f"/api/v1/registry/mine/plugins?limit={limit}")
    assert response.status_code == 422
