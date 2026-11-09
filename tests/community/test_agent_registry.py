from __future__ import annotations

import json
from pathlib import Path

import yaml

from veyra_agent_platform.contracts.agent import AgentSource

from .conftest import CommunityHarness
from .test_auth_flow import _csrf_headers, _register

_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "contracts/fixtures/project/agents/github-triage/agent.vagent.yaml"
)


def _source_bytes(**updates: object) -> bytes:
    payload = yaml.safe_load(_FIXTURE.read_text(encoding="utf-8"))
    payload.update(updates)
    source = AgentSource.from_dict(payload)
    return yaml.safe_dump(source.to_dict(), sort_keys=False).encode("utf-8")


def _publish(community: CommunityHarness, content: bytes):
    return community.client.post(
        "/api/v1/registry/agents",
        files={"package": ("github-triage.yaml", content, "application/yaml")},
        headers=_csrf_headers(community),
    )


def test_agent_registry_publishes_lists_and_downloads_immutable_source(
    community: CommunityHarness,
) -> None:
    community.app.state.database_ready = True
    _register(community, handle="agent-maker")

    response = _publish(community, _source_bytes())

    assert response.status_code == 201, response.text
    entry = response.json()
    assert entry["schema_version"] == "community.registry.v1"
    assert entry["status"] == "published"
    assert (
        entry["source_hash"]
        == AgentSource.from_dict(
            yaml.safe_load(_FIXTURE.read_text(encoding="utf-8"))
        ).source_hash
    )
    assert entry["capabilities"]["secret_refs"] == []
    assert (
        len(community.client.get("/api/v1/registry/mine/agents").json()["entries"]) == 1
    )
    assert community.client.get("/api/v1/registry/starred").json()["entries"] == []

    starred = community.client.post(
        "/api/v1/registry/agents/agent-maker/github-triage/versions/1.0.0/star",
        headers=_csrf_headers(community),
    )
    assert starred.status_code == 200
    assert [
        item["version"]
        for item in community.client.get("/api/v1/registry/starred").json()["entries"]
    ] == ["1.0.0"]

    listed = community.client.get("/api/v1/registry/agents")
    assert listed.status_code == 200
    assert listed.json()["entries"][0]["source_hash"] == entry["source_hash"]

    downloaded = community.client.get(
        "/api/v1/registry/agents/agent-maker/github-triage/versions/1.0.0/download"
    )
    assert downloaded.status_code == 200
    assert downloaded.headers["etag"] == f'"{entry["source_hash"]}"'
    assert (
        AgentSource.from_dict(yaml.safe_load(downloaded.content)).source_hash
        == entry["source_hash"]
    )
    assert "transitions" not in json.dumps(entry)

    second = _publish(
        community,
        _source_bytes(
            version="2.0.0",
            name="GitHub Triage Next",
            description="Updated immutable release metadata.",
        ),
    )
    assert second.status_code == 201, second.text
    latest = community.client.get(
        "/api/v1/registry/agents/agent-maker/github-triage"
    ).json()
    historical = community.client.get(
        "/api/v1/registry/agents/agent-maker/github-triage/versions/1.0.0"
    ).json()
    versions = community.client.get(
        "/api/v1/registry/agents/agent-maker/github-triage/versions"
    ).json()["versions"]
    assert latest["name"] == "GitHub Triage Next"
    assert historical["name"] == "GitHub Triage"
    assert historical["description"] == "Project fixture source."
    assert {item["version"]: item["name"] for item in versions} == {
        "1.0.0": "GitHub Triage",
        "2.0.0": "GitHub Triage Next",
    }


def test_agent_registry_rejects_host_secret_references_before_publish(
    community: CommunityHarness,
) -> None:
    community.app.state.database_ready = True
    _register(community, handle="secret-agent-maker")
    content = _source_bytes(
        extensions={
            "veyra": {
                "runtime_profile": "veyra-runtime-profile/1",
                "secret_refs": ["openai.api_key"],
                "permissions": {"network_hosts": [], "tools": []},
                "verification": {"required": False, "checks": []},
            }
        }
    )

    response = _publish(community, content)

    assert response.status_code == 422
    assert response.json()["detail"] == "registry_secret_reference_detected"
    assert community.client.get("/api/v1/registry/agents").json()["entries"] == []


def test_agent_registry_rejects_local_paths_before_publish(
    community: CommunityHarness,
) -> None:
    community.app.state.database_ready = True
    _register(community, handle="path-agent-maker")

    response = _publish(
        community, _source_bytes(description="Uses /Users/alice/private")
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "registry_nonportable_path_detected"
    assert community.client.get("/api/v1/registry/agents").json()["entries"] == []
