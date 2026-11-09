import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.library.dependencies import inspect_agent_dependencies
from veyra_agent_platform.local.resources import ResourceCatalogError
from veyra_agent_platform.local.runtime.config import RuntimeSettings
from veyra_agent_platform.local.secrets import MacOSKeychainSecretStore


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MacOSKeychainSecretStore, "get", lambda self, ref: None)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)


def client_for(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            LocalSettings(
                database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
                project_storage_root=tmp_path / "projects",
            ),
            runtime_settings=RuntimeSettings(allow_process_environment_key=False),
        )
    )


def setup_agent(client: TestClient, tool: str = "filesystem.read") -> tuple:
    project = client.post("/api/v1/projects", json={}).json()
    project_url = f"/api/v1/projects/{project['project_id']}"
    agent = client.post(project_url + "/agents", json={"mode": "blank"}).json()
    url = project_url + f"/agents/{agent['agent_id']}"
    draft = client.get(url + "/draft").json()
    resource = client.get(f"/api/v1/resources/veyra.tool.{tool}/versions/1.0.0").json()
    source = deepcopy(draft["source"])
    source["nodes"].append(
        {"id": "bound_tool", "component_type": "Tool", "uses": resource["reference"]}
    )
    edge = source["transitions"][0]
    source["transitions"].append(
        {"from": "bound_tool", "port": "next", "to": edge["to"]}
    )
    edge["to"] = "bound_tool"
    source["lock"][resource["reference"]] = resource["content_hash"]
    source["extensions"]["veyra"]["permissions"] = resource["required_permissions"]
    return project_url, url, draft, resource, source


def save(client: TestClient, url: str, draft: dict, source: dict):
    return client.patch(
        url + "/draft",
        json={"source": source, "expected_revision": draft["revision"]},
        headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
    )


def bind(client: TestClient, project_url: str, resource: dict) -> None:
    response = client.post(
        project_url + "/resources",
        json={key: resource[key] for key in ("reference", "content_hash")},
    )
    assert response.status_code == 201


def test_unbound_and_wrong_project_lock_refused_without_draft_write(tmp_path: Path):
    with client_for(tmp_path) as client:
        project_url, url, draft, resource, source = setup_agent(client)
        refused = save(client, url, draft, source)
        assert refused.status_code == 422
        assert refused.json()["code"] == "resource_unbound"
        assert client.get(url + "/draft").json() == draft
        app = client.app.state
        check = inspect_agent_dependencies(
            app.projects,
            app.resource_catalog,
            project_url.rsplit("/", 1)[1],
            AgentSource.from_dict(source),
        )["dependencies"][0]
        assert check["status"] == "resource_unbound"
        bind(client, project_url, resource)
        source["lock"][resource["reference"]] = "0" * 64
        refused = save(client, url, draft, source)
        assert refused.status_code == 422
        assert refused.json()["code"] == "resource_lock_mismatch"
        assert client.get(url + "/draft").json() == draft


def test_project_pin_survives_save_reload_restart_commit_and_remove_protection(
    tmp_path: Path,
):
    with client_for(tmp_path) as client:
        project_url, url, draft, resource, source = setup_agent(client)
        bind(client, project_url, resource)
        response = save(client, url, draft, source)
        assert response.status_code == 200
        saved = response.json()
        assert saved["revision"] == draft["revision"] + 1
        assert saved["etag"] != draft["etag"]
        assert response.headers["etag"] == saved["etag"]
        assert saved["source"]["lock"] == source["lock"]
        assert save(client, url, draft, source).json()["code"] == "draft_conflict"
        assert client.get(url + "/draft").json()["source"] == saved["source"]
        reloaded = client.post(url + "/draft/reload").json()
        assert reloaded["source"] == saved["source"]
        validation = client.post(url + "/validate").json()
        assert validation["dependencies"][0]["status"] == "ready"
        assert (
            validation["dependencies"][0]["bound_content_hash"]
            == resource["content_hash"]
        )
        delete_url = (
            project_url + "/resources/veyra.tool.filesystem.read/versions/1.0.0"
        )
        assert client.delete(delete_url).json()["code"] == "resource_in_use"
        committed = client.post(
            url + "/commit",
            json={"expected_revision": reloaded["revision"]},
            headers={"If-Match": reloaded["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert committed.status_code == 200
        version_id = committed.json()["version_id"]
        assert save(client, url, reloaded, draft["source"]).status_code == 200
        assert client.delete(delete_url).json()["code"] == "resource_in_use"
        snapshot = client.app.state.library.repository.version(version_id)
        assert json.loads(snapshot["source_json"])["lock"] == source["lock"]
        assert (
            save(client, url, client.get(url + "/draft").json(), source).status_code
            == 200
        )
    with client_for(tmp_path) as client:
        assert client.get(url + "/draft").json()["source"]["lock"] == source["lock"]
        assert client.delete(delete_url).json()["code"] == "resource_in_use"


@pytest.mark.parametrize("committed", [False, True])
@pytest.mark.parametrize("state", ["current", "stale", "missing"])
def test_removed_agent_retained_versions_protect_only_their_project_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, committed: bool, state: str
):
    with client_for(tmp_path) as client:
        project_url, url, draft, resource, source = setup_agent(client)
        project_id = project_url.rsplit("/", 1)[1]
        repository = client.app.state.library.repository
        bind(client, project_url, resource)
        response = save(client, url, draft, source)
        assert response.status_code == 200
        saved = response.json()
        if committed:
            response = client.post(
                url + "/commit",
                json={"expected_revision": saved["revision"]},
                headers={"If-Match": saved["etag"], "Idempotency-Key": new_uuid7()},
            )
            assert response.status_code == 200
            version_id = response.json()["version_id"]
            original_snapshot = dict(repository.version(version_id))
        removed = client.delete(url)
        assert removed.status_code == 200
        assert removed.json()["project"]["agents"] == []
        assert repository.agents(project_id) == []
        versions = repository.project_agent_versions(project_id)
        assert len(versions) == (1 if committed else 0)
        if committed:
            assert dict(versions[0]) == original_snapshot
        assert resource["reference"] not in (
            client.app.state.projects.project_resource_usage(project_id)
        )
        delete_path = "/resources/veyra.tool.filesystem.read/versions/1.0.0"
        other_project = client.post("/api/v1/projects", json={}).json()
        other_url = f"/api/v1/projects/{other_project['project_id']}"
        bind(client, other_url, resource)
        assert repository.project_agent_versions(other_project["project_id"]) == []
        catalog = client.app.state.resource_catalog
        original = catalog.by_reference

        def changed(reference: str) -> dict[str, Any]:
            descriptor = original(reference)
            if reference == resource["reference"]:
                if state == "missing":
                    raise ResourceCatalogError(
                        "resource_not_found", "Removed descriptor"
                    )
                if state == "stale":
                    return {**descriptor, "content_hash": "0" * 64}
            return descriptor

        monkeypatch.setattr(catalog, "by_reference", changed)
        assert client.delete(other_url + delete_path).status_code == 200
        response = client.delete(project_url + delete_path)
        assert response.status_code == (409 if committed else 200)
        if committed:
            assert response.json()["code"] == "resource_in_use"
            assert dict(repository.version(version_id)) == original_snapshot
    if committed:
        with client_for(tmp_path) as client:
            response = client.delete(project_url + delete_path)
            assert response.status_code == 409
            assert response.json()["code"] == "resource_in_use"
            snapshot = client.app.state.library.repository.version(version_id)
            assert dict(snapshot) == original_snapshot
            retained_source = json.loads(snapshot["source_json"])
            assert retained_source["lock"] == source["lock"]
            assert retained_source["nodes"] == source["nodes"]
            bindings = client.app.state.projects.project_resource_bindings(project_id)
            assert bindings[0].content_hash == resource["content_hash"]


@pytest.mark.parametrize("state", ["stale", "missing", "unavailable"])
def test_descriptor_drift_or_loss_never_upgrades_project_or_agent_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
):
    with client_for(tmp_path) as client:
        project_url, url, draft, resource, source = setup_agent(client)
        bind(client, project_url, resource)
        catalog = client.app.state.resource_catalog
        original = catalog.by_reference

        def changed(reference: str) -> dict[str, Any]:
            descriptor = original(reference)
            if reference != resource["reference"]:
                return descriptor
            if state == "missing":
                raise ResourceCatalogError("resource_not_found", "Removed descriptor")
            return {
                **descriptor,
                **(
                    {"content_hash": "0" * 64}
                    if state == "stale"
                    else {"availability": "unavailable"}
                ),
            }

        monkeypatch.setattr(catalog, "by_reference", changed)
        saved = save(client, url, draft, source)
        assert saved.status_code == 200
        assert saved.json()["source"]["lock"] == source["lock"]
        validation = client.post(url + "/validate").json()
        check = validation["dependencies"][0]
        assert (
            check["status"]
            == {
                "stale": "project_binding_stale",
                "missing": "missing",
                "unavailable": "runtime_unavailable",
            }[state]
        )
        assert validation["runtime_ready"] is False
        assert (
            check["locked_hash"]
            == check["bound_content_hash"]
            == resource["content_hash"]
        )
        if state == "missing":
            assert "content_hash" not in check
            assert "availability" not in check
        else:
            assert check["project_binding_status"] == (
                "stale" if state == "stale" else "current"
            )
        bindings = client.app.state.projects.project_resource_bindings(
            project_url.rsplit("/", 1)[1]
        )
        assert bindings[0].content_hash == resource["content_hash"]


def test_requires_configuration_is_design_save_not_runnable(tmp_path: Path):
    with client_for(tmp_path) as client:
        project_url, url, draft, resource, source = setup_agent(client, "github.read")
        bind(client, project_url, resource)
        assert save(client, url, draft, source).status_code == 200
        validation = client.post(url + "/validate").json()
        check = validation["dependencies"][0]
        assert validation["runtime_ready"] is False
        assert check["status"] == "configuration_required"
        assert check["availability"] == "requires_configuration"
        assert check["blocking_reasons"] == resource["blocking_reasons"]
        assert check["locked_hash"] == resource["content_hash"]
