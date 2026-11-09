from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
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


def test_binding_identity_duplicates_persistence_and_unbind(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        project = client.post("/api/v1/projects", json={}).json()
        url = f"/api/v1/projects/{project['project_id']}/resources"
        detail_url = "/api/v1/resources/veyra.tool.github.read/versions/1.0.0"
        resource = client.get(detail_url).json()
        identity = {key: resource[key] for key in ("reference", "content_hash")}
        assert client.get(url).json()["project_count"] == 0
        wrong = client.post(url, json={**identity, "content_hash": "0" * 64})
        assert wrong.status_code == 409
        assert wrong.json()["code"] == "resource_identity_conflict"
        added = client.post(url, json=identity)
        assert added.status_code == 201
        selected = next(
            item for item in added.json()["resources"] if item["scope"] == "project"
        )
        assert selected["availability"] == "requires_configuration"
        assert selected["runtime_status"] == "runtime_not_configured"
        assert selected["blocking_reasons"]
        assert selected["bound_content_hash"] == identity["content_hash"]
        manifest = Path(project["root_path"]) / "project.vproject.yaml"
        original = manifest.read_bytes()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(
                pool.map(lambda _: client.post(url, json=identity), range(4))
            )
        assert all(
            item.status_code == 201 and item.json()["project_count"] == 1
            for item in results
        )
        assert manifest.read_bytes() == original
        assert (
            client.post(url, json={**identity, "content_hash": "0" * 64}).json()["code"]
            == "resource_binding_conflict"
        )
        assert (
            client.post(url, json={"reference": "missing@1.0.0"}).json()["code"]
            == "resource_not_found"
        )
        assert (
            client.post("/api/v1/projects/missing/resources", json=identity).status_code
            == 422
        )
    with client_for(tmp_path) as client:
        assert client.get(url).json()["project_count"] == 1
        removed = client.delete(url + "/veyra.tool.github.read/versions/1.0.0")
        assert removed.status_code == 200
        assert removed.json()["project_count"] == 0
        assert client.get(detail_url).status_code == 200
        assert (
            client.delete(url + "/veyra.tool.github.read/versions/1.0.0").json()["code"]
            == "resource_not_bound"
        )
    with client_for(tmp_path) as client:
        assert client.get(url).json()["project_count"] == 0


def test_quarantine_drift_missing_preserve_pinned_identity(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        project = client.post("/api/v1/projects", json={}).json()
        url = f"/api/v1/projects/{project['project_id']}/resources"
        workshop = client.app.state.workshop
        resource = workshop.create_draft(
            confirm=True, kind="skill", requested_reference="veyra.skill.example@1.0.0"
        )["resource"]
        identity = {key: resource[key] for key in ("reference", "content_hash")}
        added = client.post(url, json=identity).json()
        bound = next(item for item in added["resources"] if item["scope"] == "project")
        assert bound["availability"] == "quarantined"
        assert bound["blocking_reasons"]
        manifest = Path(project["root_path"]) / "project.vproject.yaml"
        original = manifest.read_bytes()
        workshop.approve_skill(
            resource["resource_id"], resource["version"], "Summarize evidence."
        )
        changed = client.get(url).json()
        bound = next(
            item for item in changed["resources"] if item["scope"] == "project"
        )
        assert bound["binding_status"] == "stale"
        assert bound["bound_content_hash"] == identity["content_hash"]
        assert bound["content_hash"] != identity["content_hash"]
        assert bound["version"] == resource["version"]
        assert client.post(url, json=identity).json()["stale_count"] == 1
        for package in workshop.overlay_root.glob("workshop/*/node.yaml"):
            package.unlink()
        client.app.state.resource_catalog.reload_overlays()
        missing = client.get(url).json()
        assert missing["project_count"] == 1
        assert missing["missing_references"] == [identity["reference"]]
        assert missing["missing_bindings"] == [
            {**identity, "source": "manual", "used_by": []}
        ]
        assert manifest.read_bytes() == original
        assert (
            client.delete(
                url + f"/{resource['resource_id']}/versions/{resource['version']}"
            ).json()["project_count"]
            == 0
        )


def test_runtime_profile_lock_is_not_a_missing_project_resource(
    tmp_path: Path,
) -> None:
    with client_for(tmp_path) as client:
        project = client.post("/api/v1/projects", json={}).json()
        project_id = project["project_id"]
        agent = client.post(
            f"/api/v1/projects/{project_id}/agents", json={"mode": "blank"}
        ).json()
        draft = client.get(
            f"/api/v1/projects/{project_id}/agents/{agent['agent_id']}/draft"
        ).json()
        assert "veyra.runtime.profile@1.0.0" in draft["source"]["lock"]
        payload = client.get(f"/api/v1/projects/{project_id}/resources").json()
        assert payload["missing_references"] == []


def test_remove_refuses_source_usage_and_unreadable_usage(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        project = client.post("/api/v1/projects", json={}).json()
        project_id = project["project_id"]
        url = f"/api/v1/projects/{project_id}/resources"
        resource = client.get(
            "/api/v1/resources/veyra.tool.filesystem.read/versions/1.0.0"
        ).json()
        assert (
            client.post(
                url,
                json={
                    "reference": resource["reference"],
                    "content_hash": resource["content_hash"],
                },
            ).status_code
            == 201
        )
        agent = client.post(
            f"/api/v1/projects/{project_id}/agents", json={"mode": "blank"}
        ).json()
        root = Path(project["root_path"])
        manifest_path = root / "project.vproject.yaml"
        manifest = yaml.safe_load(manifest_path.read_text())
        entry = next(
            item for item in manifest["agents"] if item["agent_id"] == agent["agent_id"]
        )
        source_path = root / entry["path"] / "agent.vagent.yaml"
        source = yaml.safe_load(source_path.read_text())
        source["lock"][resource["reference"]] = resource["content_hash"]
        source_path.write_text(yaml.safe_dump(source))
        original = manifest_path.read_bytes()
        delete_url = url + "/veyra.tool.filesystem.read/versions/1.0.0"
        refused = client.delete(delete_url)
        assert refused.status_code == 409
        assert refused.json()["code"] == "resource_in_use"
        library = client.app.state.library
        draft = library.reload_from_disk(project_id, agent["agent_id"])
        library.commit(
            project_id=project_id,
            agent_id=agent["agent_id"],
            expected_revision=draft["revision"],
            expected_etag=draft["etag"],
            idempotency_key=new_uuid7(),
        )
        source["lock"].pop(resource["reference"])
        source_path.write_text(yaml.safe_dump(source))
        assert client.delete(delete_url).json()["code"] == "resource_in_use"
        source_path.write_text("invalid: [")
        assert client.delete(delete_url).status_code != 200
        assert manifest_path.read_bytes() == original


def test_concurrent_distinct_bindings_and_design_reference(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        project = client.post("/api/v1/projects", json={}).json()
        url = f"/api/v1/projects/{project['project_id']}/resources"
        resources = client.get("/api/v1/resources").json()["resources"]
        selected = [
            next(item for item in resources if item["kind"] == kind)
            for kind in ("tool", "template")
        ]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda item: client.post(
                        url,
                        json={
                            "reference": item["reference"],
                            "content_hash": item["content_hash"],
                        },
                    ),
                    selected,
                )
            )
        assert all(item.status_code == 201 for item in results)
        payload = client.get(url).json()
        assert payload["project_count"] == 2
        template = next(
            item for item in payload["resources"] if item["kind"] == "template"
        )
        assert template["availability"] == "design_only"
        assert template["runtime_status"] == "runtime_not_supported"
        assert template["blocking_reasons"]
