from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from tests.integration.local.test_builder_conversations import _turn
from tests.integration.local.test_builder_resolution import intent
from tests.integration.local.test_factory_routes import (
    ScriptedKimiTransport,
    _completion,
)
from tests.integration.local.test_runtime_routes import _agent_source
from tests.integration.local.verified_runtime_model import MemorySecretStore
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.runtime.client import RuntimeCompletion


class RuntimeTransport:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def models(self) -> tuple[str, ...]:
        return ("kimi-k3", "gpt-test")

    def complete(self, messages: object) -> RuntimeCompletion:
        self.calls.append(messages)
        return RuntimeCompletion(content="unused", finish_reason="stop")


def _client(
    tmp_path: Path,
    *,
    factory_transport: ScriptedKimiTransport | None = None,
    runtime_preflight: bool | None = None,
    secrets: MemorySecretStore | None = None,
) -> TestClient:
    return TestClient(
        create_app(
            LocalSettings(
                database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
                project_storage_root=tmp_path / "projects",
            ),
            factory_transport=factory_transport,
            runtime_transport=RuntimeTransport(),
            runtime_preflight=runtime_preflight,
            secret_store=secrets or MemorySecretStore(),
        )
    )


def test_runtime_credential_metadata_never_returns_secret_and_binds_project(
    tmp_path: Path,
) -> None:
    secrets = MemorySecretStore()
    with _client(tmp_path, secrets=secrets) as client:
        created = client.post(
            "/api/v1/runtime-credentials",
            json={
                "provider_type": "moonshot",
                "label": "My Kimi",
                "api_key": "sk-user-runtime-secret",
                "make_default": True,
            },
        )
        assert created.status_code == 201, created.text
        payload = created.json()
        assert payload["valid"] is True
        assert payload["credential"]["status"] == "active"
        assert payload["credential"]["credential_scope"] == "device"
        assert payload["credential"]["secret_state"] == "available"
        assert payload["credential"]["readiness"] == "ready"
        assert "sk-user-runtime-secret" not in json.dumps(payload)
        credential_id = payload["credential"]["credential_id"]
        assert (
            secrets.values[f"runtime.credential.{credential_id}"]
            == "sk-user-runtime-secret"
        )

        listed = client.get("/api/v1/runtime-credentials").json()
        assert listed["credentials"][0]["credential_id"] == credential_id
        assert "sk-user-runtime-secret" not in json.dumps(listed)

        project = client.post(
            "/api/v1/projects", json={"name": "Runtime Binding"}
        ).json()
        bound = client.patch(
            f"/api/v1/projects/{project['project_id']}/runtime-binding",
            json={"credential_id": credential_id, "model_id": "kimi-k3"},
        )
        assert bound.status_code == 200, bound.text
        assert bound.json()["binding"]["credential_id"] == credential_id
        assert bound.json()["credential"]["label"] == "My Kimi"
        assert "sk-user-runtime-secret" not in bound.text

        disabled = client.post(f"/api/v1/runtime-credentials/{credential_id}/disable")
        assert disabled.status_code == 200
        assert disabled.json()["schema_version"] == "1.0"
        assert disabled.json()["credential"]["status"] == "disabled"
        rejected = client.patch(
            f"/api/v1/projects/{project['project_id']}/runtime-binding",
            json={"credential_id": credential_id, "model_id": "kimi-k3"},
        )
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "credential_not_active"

        enabled = client.post(f"/api/v1/runtime-credentials/{credential_id}/enable")
        assert enabled.status_code == 200
        assert enabled.json()["schema_version"] == "1.0"
        assert enabled.json()["credential"]["status"] == "active"

        replaced = client.post(
            f"/api/v1/runtime-credentials/{credential_id}/replace-secret",
            json={"api_key": "sk-replaced-runtime-secret"},
        )
        assert replaced.status_code == 200
        assert replaced.json()["credential"]["status"] == "active"
        assert replaced.json()["credential"]["readiness"] == "ready"
        assert "sk-replaced-runtime-secret" not in replaced.text
        deleted = client.delete(f"/api/v1/runtime-credentials/{credential_id}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True
        assert f"runtime.credential.{credential_id}" not in secrets.values
        assert client.get("/api/v1/runtime-credentials").json()["credentials"] == []


def test_missing_device_secret_is_visible_without_deleting_metadata(
    tmp_path: Path,
) -> None:
    secrets = MemorySecretStore()
    with _client(tmp_path, secrets=secrets) as client:
        created = client.post(
            "/api/v1/runtime-credentials",
            json={
                "provider_type": "openai_compatible",
                "label": "Stale Mock",
                "api_key": "synthetic-key",
                "base_url": "http://127.0.0.1:8790/v1",
                "default_model_id": "mock-model",
            },
        )
        assert created.status_code == 201, created.text
        credential_id = created.json()["credential"]["credential_id"]
        secrets.delete(f"runtime.credential.{credential_id}")

        listed = client.get("/api/v1/runtime-credentials").json()["credentials"]
        stale = next(item for item in listed if item["credential_id"] == credential_id)
        assert stale["status"] == "active"
        assert stale["secret_state"] == "missing"
        assert stale["readiness"] == "needs_reentry"


def test_device_scope_rejects_future_cloud_scope_on_local_api(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/runtime-credentials",
            json={
                "provider_type": "moonshot",
                "label": "Cloud placeholder",
                "api_key": "not-persisted",
                "credential_scope": "cloud",
            },
        )
        assert response.status_code == 422
        assert response.json()["code"] == "credential_scope_unsupported"


def test_device_credential_metadata_and_secret_survive_app_restart(
    tmp_path: Path,
) -> None:
    secrets = MemorySecretStore()
    with _client(tmp_path, secrets=secrets) as first:
        created = first.post(
            "/api/v1/runtime-credentials",
            json={
                "provider_type": "moonshot",
                "label": "Restart proof",
                "api_key": "restart-secret",
                "default_model_id": "kimi-k3",
            },
        )
        assert created.status_code == 201, created.text
        credential_id = created.json()["credential"]["credential_id"]

    with _client(tmp_path, secrets=secrets) as restarted:
        listed = restarted.get("/api/v1/runtime-credentials").json()["credentials"]
        credential = next(
            item for item in listed if item["credential_id"] == credential_id
        )
        assert credential["readiness"] == "ready"
        assert secrets.values[f"runtime.credential.{credential_id}"] == "restart-secret"


def test_account_default_credential_reports_contract_profile_source(
    tmp_path: Path,
) -> None:
    secrets = MemorySecretStore()
    with _client(tmp_path, secrets=secrets) as client:
        created = client.post(
            "/api/v1/runtime-credentials",
            json={
                "provider_type": "moonshot",
                "label": "My Kimi",
                "api_key": "sk-user-runtime-secret",
                "default_model_id": "kimi-k3",
                "make_default": True,
            },
        )
        assert created.status_code == 201, created.text
        project = client.post(
            "/api/v1/projects", json={"agents": [_agent_source()]}
        ).json()
        agent = project["agents"][0]
        ready = client.get(
            f"/api/v1/projects/{project['project_id']}/agents/"
            f"{agent['agent_id']}/runtime-readiness"
        )
        assert ready.status_code == 200, ready.text
        payload = ready.json()
        assert payload["profile_source"] == "default"
        assert payload["model"]["configured"] is True
        assert payload["model"]["model_id"] == "kimi-k3"


def test_platform_credential_cannot_be_mutated_through_user_secret_api(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        response = client.put(
            "/api/v1/secrets/model.primary", json={"value": "sk-platform"}
        )
        assert response.status_code == 403
        assert response.json()["code"] == "platform_credential_forbidden"


def test_builder_create_agent_waits_for_runtime_credential_before_semantic_generation(
    tmp_path: Path,
) -> None:
    transport = ScriptedKimiTransport(
        [_completion(json.dumps(intent(intent="create", create_kind="agent")))]
    )
    with _client(
        tmp_path, factory_transport=transport, runtime_preflight=True
    ) as client:
        project = client.post(
            "/api/v1/projects", json={"name": "Builder Runtime Gate"}
        ).json()["project_id"]
        snapshot = _turn(
            client,
            project,
            content="Create a review Agent.",
            locale="en",
        ).json()
        operation = snapshot["operations"][0]
        assert operation["status"] == "waiting"
        assert (
            operation["diagnostic"]["waiting_for"] == "waiting_for_runtime_credential"
        )
        assert snapshot["factory_session"] is None
        assert len(transport.calls) == 1
