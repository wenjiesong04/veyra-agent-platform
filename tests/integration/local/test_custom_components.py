from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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


def _transform_payload() -> dict[str, object]:
    return {
        "display_name": "Text Formatter",
        "description": "A reusable deterministic formatter.",
        "inputs": {"text": "string"},
        "outputs": {"result": "string"},
        "implementation": {"kind": "transform", "mapping": {"result": "{{text}}"}},
        "metadata": {"category": "text", "owner": "project"},
    }


def test_custom_component_lifecycle_is_immutable_and_project_scoped(
    tmp_path: Path,
) -> None:
    with client_for(tmp_path) as client:
        first_project = client.post("/api/v1/projects", json={}).json()
        project_id = first_project["project_id"]
        base = f"/api/v1/projects/{project_id}/custom-components"

        created = client.post(base, json=_transform_payload())
        assert created.status_code == 201
        draft = created.json()
        component_id = draft["component_id"]
        assert draft["version"] == "0.0.0"
        assert draft["metadata"] == {"category": "text", "owner": "project"}
        assert draft["readiness"] == "ready"

        validated = client.post(f"{base}/{component_id}/validate")
        assert validated.status_code == 200
        assert validated.json()["implementation"]["kind"] == "transform"

        first = client.post(f"{base}/{component_id}/versions", json={})
        assert first.status_code == 200
        first_version = first.json()
        assert first_version["version"] == "1.0.0"
        first_hash = first_version["content_hash"]

        edited = client.patch(
            f"{base}/{component_id}",
            json={"description": "Updated deterministic formatter."},
        )
        assert edited.status_code == 200
        second = client.post(f"{base}/{component_id}/versions", json={})
        assert second.status_code == 200
        assert second.json()["version"] == "1.0.1"

        old = client.get(f"{base}/{component_id}?version=1.0.0")
        assert old.status_code == 200
        assert old.json()["content_hash"] == first_hash
        assert old.json()["description"] == "A reusable deterministic formatter."

        deprecated = client.post(f"{base}/{component_id}/versions/1.0.0/deprecate")
        assert deprecated.status_code == 200
        assert deprecated.json()["deprecated"] is True
        assert client.delete(f"{base}/{component_id}").status_code == 409

        other_project = client.post("/api/v1/projects", json={}).json()
        isolated = client.get(
            f"/api/v1/projects/{other_project['project_id']}/custom-components/{component_id}"
        )
        assert isolated.status_code == 404


def test_tool_wrapper_requires_a_project_pin_and_derives_permissions(
    tmp_path: Path,
) -> None:
    with client_for(tmp_path) as client:
        project = client.post("/api/v1/projects", json={}).json()
        project_id = project["project_id"]
        base = f"/api/v1/projects/{project_id}/custom-components"
        wrapper = {
            **_transform_payload(),
            "display_name": "GitHub Reader",
            "implementation": {
                "kind": "tool_wrapper",
                "tool_reference": "veyra.tool.github.read@1.0.0",
            },
        }

        unbound = client.post(base, json=wrapper)
        assert unbound.status_code == 422
        assert unbound.json()["code"] == "dependency_not_project_bound"

        tool = client.get("/api/v1/resources/veyra.tool.github.read/versions/1.0.0")
        assert tool.status_code == 200
        bound = client.post(
            f"/api/v1/projects/{project_id}/resources",
            json={
                "reference": tool.json()["reference"],
                "content_hash": tool.json()["content_hash"],
            },
        )
        assert bound.status_code == 201

        created = client.post(base, json=wrapper)
        assert created.status_code == 201
        definition = created.json()
        assert definition["readiness"] == "requires_configuration"
        assert definition["dependencies"] == [
            {
                "reference": tool.json()["reference"],
                "content_hash": tool.json()["content_hash"],
            }
        ]
        assert "veyra.tool.github.read" in definition["required_permissions"]["tools"]

        overgrant = {
            **wrapper,
            "required_permissions": {
                "network_hosts": ["attacker.example"],
                "tools": [],
                "filesystem_read_roots": [],
                "filesystem_write_roots": [],
                "shell_workspace_only": False,
            },
        }
        rejected = client.post(base, json=overgrant)
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "permission_overgrant"
