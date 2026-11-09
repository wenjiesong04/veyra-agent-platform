from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.models.contracts import CAPABILITY_NAMES
from veyra_agent_platform.local.runtime.client import (
    GeneratedImage,
    RuntimeCompletion,
    RuntimeProviderError,
)
from veyra_agent_platform.local.storage.bootstrap import HEAD_REVISION

ROOT = Path(__file__).resolve().parents[3]


class MemorySecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, secret_ref: str) -> str | None:
        return self.values.get(secret_ref)

    def set(self, secret_ref: str, value: str) -> None:
        self.values[secret_ref] = value

    def delete(self, secret_ref: str) -> None:
        self.values.pop(secret_ref, None)


class FakeProvider:
    def __init__(self, models: list[dict] | None = None) -> None:
        self.model_rows = list(models or [{"id": "fake-text-model"}])
        self.discovery_error: RuntimeProviderError | None = None
        self.completion_calls: list[tuple[object, object]] = []
        self.generated_prompts: list[str] = []
        self.generated_parameters: list[tuple[int, str | None]] = []

    def models(self) -> tuple[str, ...]:
        if self.discovery_error is not None:
            raise self.discovery_error
        return tuple(
            item["id"] for item in self.model_rows if isinstance(item.get("id"), str)
        )

    def discover_models(self) -> list[dict]:
        if self.discovery_error is not None:
            raise self.discovery_error
        return list(self.model_rows)

    def complete(self, messages, *, response_format=None) -> RuntimeCompletion:
        self.completion_calls.append((messages, response_format))
        content = '{"ok":true}' if response_format else "PRIVATE-PROBE-OUTPUT"
        return RuntimeCompletion(content=content, finish_reason="stop")

    def generate_images(self, prompt: str, *, count: int = 1, size=None):
        self.generated_prompts.append(prompt)
        self.generated_parameters.append((count, size))
        return [
            GeneratedImage(
                contents=b"PRIVATE-PROBE-IMAGE-BYTES",
                media_type="image/png",
            )
            for _ in range(count)
        ]


def _client(
    tmp_path: Path,
    provider: FakeProvider | None = None,
    secrets: MemorySecretStore | None = None,
    database_path: Path | None = None,
) -> TestClient:
    db = database_path or tmp_path / "app.sqlite3"
    return TestClient(
        create_app(
            LocalSettings(
                database_url=f"sqlite:///{db}",
                project_storage_root=tmp_path / "projects",
            ),
            runtime_transport=provider or FakeProvider(),
            secret_store=secrets or MemorySecretStore(),
        )
    )


def _create_credential(client: TestClient, *, make_default: bool = False) -> dict:
    response = client.post(
        "/api/v1/runtime-credentials",
        json={
            "provider_type": "openai_compatible",
            "label": "Synthetic Provider",
            "api_key": "sk-never-return-this-value",
            "base_url": "http://127.0.0.1:9876/v1",
            "make_default": make_default,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_fresh_local_database_creates_model_registry_tables(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        assert client.app.state.database_revision == HEAD_REVISION
        assert HEAD_REVISION == "local_0038_work_item_version_binding"
        with client.app.state.repository._connect() as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            tables = {row["name"] for row in rows}
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(provider_credentials)"
                ).fetchall()
            }
        assert {"model_profiles", "model_role_defaults"} <= tables
        assert {
            "model_discovery_state",
            "model_discovery_checked_at",
            "model_discovered_at",
            "model_discovery_error_code",
        } <= columns


def test_upgrade_from_0035_preserves_credentials_and_backfills_only_model_ids(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "upgrade.sqlite3"
    config = Config(str(ROOT / "backend/migrations/local/alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "local_0035_workflow_versions")

    credential_id = new_uuid7()
    validated_at = "2026-10-01T10:00:00Z"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """INSERT INTO provider_credentials(
                credential_id, owner_id, provider_type, label, base_url, status,
                credential_scope, masked_hint, capabilities_json, default_model_id,
                is_default, secret_ref, created_at, updated_at, validated_at,
                last_used_at
            ) VALUES (?, 'local', 'openai_compatible', 'Saved Provider',
                'https://example.invalid/v1', 'active', 'device', '••••test', ?,
                'legacy-model', 1, ?, ?, ?, ?, NULL)""",
            (
                credential_id,
                json.dumps(
                    {"models": ["legacy-model"], "validated_without_generation": True}
                ),
                f"runtime.credential.{credential_id}",
                validated_at,
                validated_at,
                validated_at,
            ),
        )

    with _client(tmp_path, database_path=database_path) as client:
        assert client.app.state.database_revision == HEAD_REVISION
        listed = client.get("/api/v1/runtime-models")
        assert listed.status_code == 200, listed.text
        profile = listed.json()["models"][0]
        assert profile["provider_connection_id"] == credential_id
        assert profile["provider_model_id"] == "legacy-model"
        assert profile["verification"]["state"] == "unknown"
        assert all(
            profile["capabilities"][name]["status"] == "unknown"
            and profile["capabilities"][name]["evidence"] is None
            for name in CAPABILITY_NAMES
        )
        assert profile["registry_ready"] is False
        defaults = client.get("/api/v1/runtime-models/defaults").json()["defaults"]
        assert defaults[0]["role"] == "primary"
        assert defaults[0]["model_profile_id"] == profile["model_profile_id"]
        with client.app.state.repository._connect() as connection:
            credential = connection.execute(
                "SELECT credential_id, status, default_model_id, secret_ref "
                "FROM provider_credentials WHERE credential_id = ?",
                (credential_id,),
            ).fetchone()
            version = connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()[0]
        assert tuple(credential) == (
            credential_id,
            "active",
            "legacy-model",
            f"runtime.credential.{credential_id}",
        )
        assert version == HEAD_REVISION


def test_provider_metadata_discovery_is_separate_from_capability_verification(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(
        [
            {
                "id": "provider-model-id",
                "display_name": "Metadata Model",
                "context_window": 8192,
                "max_output_tokens": 1024,
                "modalities": ["text", "image"],
                "provider_family": "compatible-family",
                "capabilities": {
                    "text_generation": True,
                    "image_generation": False,
                    "not_a_capability": True,
                },
                "api_key": "MUST-NOT-BE-COPIED",
            }
        ]
    )
    with _client(tmp_path, provider) as client:
        created = _create_credential(client)
        assert created["valid"] is True
        assert created["discovery"]["state"] == "ready"
        profile = created["models"][0]
        assert profile["display_name"] == "Metadata Model"
        assert profile["metadata"] == {
            "context_window": 8192,
            "max_output_tokens": 1024,
            "modalities": ["image", "text"],
            "provider_family": "compatible-family",
        }
        assert profile["capabilities"]["text_generation"]["status"] == "supported"
        assert (
            profile["capabilities"]["text_generation"]["evidence"]["source"]
            == "provider_metadata"
        )
        assert profile["capabilities"]["image_generation"]["status"] == "unsupported"
        assert profile["capabilities"]["image_input"]["status"] == "unknown"
        assert profile["verification"]["state"] == "declared"
        assert profile["registry_ready"] is True
        assert "MUST-NOT-BE-COPIED" not in json.dumps(created)
        assert "sk-never-return-this-value" not in json.dumps(created)
        with client.app.state.repository._connect() as connection:
            persisted = connection.execute(
                "SELECT metadata_json, capabilities_json, verification_json "
                "FROM model_profiles"
            ).fetchone()
            credential = connection.execute(
                "SELECT capabilities_json FROM provider_credentials"
            ).fetchone()[0]
        assert "MUST-NOT-BE-COPIED" not in " ".join(persisted)
        assert "sk-never-return-this-value" not in " ".join(persisted)
        assert "MUST-NOT-BE-COPIED" not in credential


def test_validation_preserves_user_default_model_when_provider_omits_it(
    tmp_path: Path,
) -> None:
    provider = FakeProvider([{"id": "listed-model"}])
    with _client(tmp_path, provider) as client:
        response = client.post(
            "/api/v1/runtime-credentials",
            json={
                "provider_type": "openai_compatible",
                "label": "Saved image default",
                "api_key": "sk-not-returned",
                "base_url": "http://127.0.0.1:9876/v1",
                "default_model_id": "omitted-image-model",
            },
        )
        assert response.status_code == 201, response.text
        result = response.json()
        assert result["valid"] is True
        assert result["code"] == "default_model_unavailable"
        assert result["model_selection"] == {
            "provider_model_id": "omitted-image-model",
            "state": "needs_setup",
        }
        assert result["credential"]["default_model_id"] == "omitted-image-model"
        assert [item["provider_model_id"] for item in result["models"]] == [
            "listed-model"
        ]
        credential_id = result["credential"]["credential_id"]
        rechecked = client.post(f"/api/v1/runtime-credentials/{credential_id}/validate")
        assert (
            rechecked.json()["credential"]["default_model_id"] == "omitted-image-model"
        )
        assert rechecked.json()["code"] == "default_model_unavailable"
        assert "sk-not-returned" not in response.text


def test_manual_model_when_discovery_is_unavailable_starts_unknown_and_can_be_probed(
    tmp_path: Path,
) -> None:
    provider = FakeProvider()
    provider.discovery_error = RuntimeProviderError(
        "runtime_model_discovery_unavailable", "private endpoint detail"
    )
    with _client(tmp_path, provider) as client:
        created = _create_credential(client)
        assert created["valid"] is False
        assert created["discovery"]["state"] == "failed"
        assert created["credential"]["readiness"] == "unverified"
        added = client.post(
            f"/api/v1/runtime-credentials/{created['credential']['credential_id']}/models",
            json={
                "provider_model_id": "manual-image-model",
                "display_name": "My model",
            },
        )
        assert added.status_code == 200, added.text
        profile = added.json()["model"]
        assert profile["provider_model_id"] == "manual-image-model"
        assert profile["listed"] is False
        assert profile["verification"]["state"] == "unknown"
        assert profile["verification"]["source"] == "user_declared"
        assert all(
            profile["capabilities"][name]["status"] == "unknown"
            and profile["capabilities"][name]["evidence"] is None
            for name in CAPABILITY_NAMES
        )
        assert profile["registry_ready"] is False

        provider.discovery_error = None
        probed = client.post(
            f"/api/v1/runtime-models/{profile['model_profile_id']}/capabilities/probe",
            json={"capability": "text_generation"},
        )
        assert probed.status_code == 200, probed.text
        updated = probed.json()["model"]
        assert updated["capabilities"]["text_generation"]["status"] == "supported"
        assert (
            updated["capabilities"]["text_generation"]["evidence"]["source"]
            == "active_probe"
        )
        assert updated["verification"]["state"] == "verified"
        assert updated["registry_ready"] is True
        assert "PRIVATE-PROBE-OUTPUT" not in probed.text

        image_probe = client.post(
            f"/api/v1/runtime-models/{profile['model_profile_id']}/capabilities/probe",
            json={"capability": "image_input", "acknowledge_cost": True},
        )
        assert image_probe.status_code == 200, image_probe.text
        image_profile = image_probe.json()["model"]
        assert image_profile["listed"] is False
        assert image_profile["capabilities"]["image_input"]["status"] == "supported"
        assert image_profile["registry_ready"] is True
        assert "PRIVATE-PROBE-OUTPUT" not in image_probe.text
        project = client.post("/api/v1/projects", json={"name": "Manual model"})
        assert project.status_code == 201, project.text
        bound = client.patch(
            f"/api/v1/projects/{project.json()['project_id']}/runtime-binding",
            json={
                "credential_id": created["credential"]["credential_id"],
                "model_id": "manual-image-model",
            },
        )
        assert bound.status_code == 200, bound.text


def test_explicit_text_structured_and_image_probes_are_bounded_and_never_return_output(
    tmp_path: Path,
) -> None:
    provider = FakeProvider([{"id": "fake-model"}])
    with _client(tmp_path, provider) as client:
        created = _create_credential(client)
        profile = created["models"][0]
        profile_id = profile["model_profile_id"]
        url = f"/api/v1/runtime-models/{profile_id}/capabilities/probe"

        image_without_ack = client.post(url, json={"capability": "image_input"})
        assert image_without_ack.status_code == 422
        assert (
            image_without_ack.json()["code"]
            == "capability_probe_cost_confirmation_required"
        )
        assert provider.completion_calls == []

        text = client.post(url, json={"capability": "text_generation"})
        assert text.status_code == 200, text.text
        assert (
            text.json()["model"]["capabilities"]["text_generation"]["status"]
            == "supported"
        )
        assert "PRIVATE-PROBE-OUTPUT" not in text.text

        structured = client.post(url, json={"capability": "structured_output"})
        assert structured.status_code == 200, structured.text
        assert (
            structured.json()["model"]["capabilities"]["structured_output"]["status"]
            == "supported"
        )
        assert provider.completion_calls[-1][1] == {"type": "json_object"}
        assert '{"ok":true}' not in structured.text

        image_input = client.post(
            url,
            json={"capability": "image_input", "acknowledge_cost": True},
        )
        assert image_input.status_code == 200, image_input.text
        assert (
            image_input.json()["model"]["capabilities"]["image_input"]["status"]
            == "supported"
        )
        serialized = json.dumps(provider.completion_calls[-1][0])
        assert "data:image/png;base64," in serialized
        assert "PRIVATE-PROBE-OUTPUT" not in image_input.text

        generation_without_ack = client.post(
            url, json={"capability": "image_generation"}
        )
        assert generation_without_ack.status_code == 422
        assert (
            generation_without_ack.json()["code"]
            == "capability_probe_cost_confirmation_required"
        )
        assert provider.generated_prompts == []

        generation = client.post(
            url,
            json={"capability": "image_generation", "acknowledge_cost": True},
        )
        assert generation.status_code == 200, generation.text
        assert (
            generation.json()["model"]["capabilities"]["image_generation"]["status"]
            == "supported"
        )
        assert len(provider.generated_prompts) == 1
        assert provider.generated_parameters == [(1, None)]
        assert "PRIVATE-PROBE-IMAGE-BYTES" not in generation.text
        with client.app.state.repository._connect() as connection:
            persisted = connection.execute(
                "SELECT capabilities_json, verification_json FROM model_profiles"
            ).fetchone()
        assert "PRIVATE-PROBE-OUTPUT" not in " ".join(persisted)
        assert "PRIVATE-PROBE-IMAGE-BYTES" not in " ".join(persisted)


def test_console_address_is_rejected_before_storing_a_new_key(tmp_path: Path) -> None:
    secrets = MemorySecretStore()
    with _client(tmp_path, secrets=secrets) as client:
        response = client.post(
            "/api/v1/runtime-credentials",
            json={
                "provider_type": "openai_compatible",
                "label": "Qwen",
                "api_key": "SYNTHETIC-PRIVATE-KEY",
                "base_url": "https://bailian.console.aliyun.com/cn-beijing/settings/api-key",
            },
        )
        assert response.status_code == 422
        assert response.json()["code"] == "provider_console_url"
        assert "SYNTHETIC-PRIVATE-KEY" not in response.text
        assert secrets.values == {}
        assert client.get("/api/v1/runtime-credentials").json()["credentials"] == []


def test_correcting_console_address_allows_image_probe_without_old_evidence(
    tmp_path: Path,
) -> None:
    provider = FakeProvider()
    with _client(tmp_path, provider) as client:
        created = _create_credential(client)
        credential_id = created["credential"]["credential_id"]
        profile = client.post(
            f"/api/v1/runtime-credentials/{credential_id}/models",
            json={"provider_model_id": "manual-image-model"},
        ).json()["model"]
        profile_id = profile["model_profile_id"]
        probe_url = f"/api/v1/runtime-models/{profile_id}/capabilities/probe"
        initial = client.post(probe_url, json={"capability": "text_generation"})
        assert initial.status_code == 200
        assert (
            initial.json()["model"]["capabilities"]["text_generation"]["status"]
            == "supported"
        )
        # Reproduce metadata from an older app that accepted a console URL.
        # Test-only SQLite is used; no host credential or live service is read.
        with client.app.state.repository.transaction() as connection:
            connection.execute(
                "UPDATE provider_credentials SET base_url = ? WHERE credential_id = ?",
                (
                    "https://bailian.console.aliyun.com/cn-beijing/settings/api-key",
                    credential_id,
                ),
            )
        rejected = client.post(
            probe_url, json={"capability": "image_generation", "acknowledge_cost": True}
        )
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "provider_console_url"
        assert provider.generated_prompts == []

        corrected = client.patch(
            f"/api/v1/runtime-credentials/{credential_id}",
            json={
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            },
        )
        assert corrected.status_code == 200
        before_probe = client.get(f"/api/v1/runtime-models/{profile_id}").json()[
            "model"
        ]
        assert before_probe["registry_ready"] is False
        provider.discovery_error = RuntimeProviderError(
            "runtime_model_discovery_unavailable", "PRIVATE-DISCOVERY-DETAIL"
        )
        discovery = client.post(
            f"/api/v1/runtime-credentials/{credential_id}/models/discover"
        )
        assert discovery.status_code == 200
        assert discovery.json()["valid"] is False

        probed = client.post(
            probe_url, json={"capability": "image_generation", "acknowledge_cost": True}
        )
        assert probed.status_code == 200, probed.text
        updated = probed.json()["model"]
        assert updated["model_profile_id"] == profile_id
        assert updated["registry_ready"] is True
        assert updated["capabilities"]["image_generation"]["status"] == "supported"
        assert updated["capabilities"]["text_generation"]["status"] == "unknown"
        assert updated["capabilities"]["text_generation"]["evidence"] is None
        assert updated["verification"]["stale_reason"] is None
        assert provider.generated_parameters == [(1, None)]
        assert "PRIVATE-PROBE-IMAGE-BYTES" not in probed.text
        assert "PRIVATE-DISCOVERY-DETAIL" not in probed.text


def test_image_probe_cannot_verify_an_address_changed_during_generation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider = FakeProvider()
    with _client(tmp_path, provider) as client:
        created = _create_credential(client)
        credential_id = created["credential"]["credential_id"]
        profile_id = created["models"][0]["model_profile_id"]
        original_generate = provider.generate_images

        def change_address(prompt, *, count=1, size=None):
            result = original_generate(prompt, count=count, size=size)
            client.app.state.provider_credentials.update_metadata(
                credential_id, base_url="https://different.example/v1"
            )
            return result

        monkeypatch.setattr(provider, "generate_images", change_address)
        result = client.post(
            f"/api/v1/runtime-models/{profile_id}/capabilities/probe",
            json={"capability": "image_generation", "acknowledge_cost": True},
        )
        assert result.status_code == 422
        assert result.json()["code"] == "model_connection_endpoint_changed"
        profile = client.get(f"/api/v1/runtime-models/{profile_id}").json()["model"]
        assert profile["registry_ready"] is False
        assert profile["capabilities"]["image_generation"]["status"] == "unknown"


def test_explicit_enable_allows_manual_verification_when_model_list_is_unavailable(
    tmp_path: Path,
) -> None:
    provider = FakeProvider()
    provider.discovery_error = RuntimeProviderError(
        "runtime_model_discovery_unavailable", "synthetic model list unavailable"
    )
    with _client(tmp_path, provider) as client:
        created = _create_credential(client)
        credential_id = created["credential"]["credential_id"]
        added = client.post(
            f"/api/v1/runtime-credentials/{credential_id}/models",
            json={"provider_model_id": "manual-model"},
        )
        assert added.status_code == 200, added.text
        profile_id = added.json()["model"]["model_profile_id"]
        probe_url = f"/api/v1/runtime-models/{profile_id}/capabilities/probe"

        disabled = client.post(f"/api/v1/runtime-credentials/{credential_id}/disable")
        assert disabled.status_code == 200, disabled.text
        refused = client.post(probe_url, json={"capability": "text_generation"})
        assert refused.status_code == 422
        assert refused.json()["code"] == "model_connection_disabled"
        assert provider.completion_calls == []

        enabled = client.post(f"/api/v1/runtime-credentials/{credential_id}/enable")
        assert enabled.status_code == 200, enabled.text
        assert enabled.json()["valid"] is False
        assert enabled.json()["code"] == "runtime_model_discovery_unavailable"
        assert enabled.json()["credential"]["status"] == "unverified"
        assert enabled.json()["credential"]["readiness"] == "unverified"
        assert provider.completion_calls == []
        assert (
            client.get(f"/api/v1/runtime-models/{profile_id}").json()["model"][
                "registry_ready"
            ]
            is False
        )

        verified = client.post(probe_url, json={"capability": "text_generation"})
        assert verified.status_code == 200, verified.text
        assert len(provider.completion_calls) == 1
        assert verified.json()["model"]["registry_ready"] is True
        assert (
            verified.json()["model"]["capabilities"]["text_generation"]["status"]
            == "supported"
        )
        assert (
            client.get("/api/v1/runtime-credentials").json()["credentials"][0]["status"]
            == "active"
        )


def test_explicit_enable_does_not_make_a_rejected_key_ready(tmp_path: Path) -> None:
    provider = FakeProvider()
    with _client(tmp_path, provider) as client:
        created = _create_credential(client)
        credential_id = created["credential"]["credential_id"]
        client.post(f"/api/v1/runtime-credentials/{credential_id}/disable")
        provider.discovery_error = RuntimeProviderError(
            "runtime_unauthorized", "synthetic rejected key"
        )

        enabled = client.post(f"/api/v1/runtime-credentials/{credential_id}/enable")
        assert enabled.status_code == 200, enabled.text
        assert enabled.json()["valid"] is False
        assert enabled.json()["code"] == "runtime_unauthorized"
        assert enabled.json()["credential"]["status"] == "invalid"
        assert enabled.json()["credential"]["readiness"] == "invalid"
        assert provider.completion_calls == []
        assert (
            client.get("/api/v1/runtime-models").json()["models"][0]["registry_ready"]
            is False
        )


def test_transient_recheck_preserves_evidence_but_auth_failure_makes_profile_not_ready(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(
        [{"id": "fake-model", "capabilities": {"text_generation": True}}]
    )
    with _client(tmp_path, provider) as client:
        created = _create_credential(client)
        credential_id = created["credential"]["credential_id"]
        before = created["models"][0]

        provider.discovery_error = RuntimeProviderError(
            "runtime_rate_limited", "RAW-PROVIDER-SECRET-DETAIL"
        )
        limited = client.post(f"/api/v1/runtime-credentials/{credential_id}/validate")
        assert limited.status_code == 200
        assert limited.json()["valid"] is False
        assert limited.json()["credential"]["status"] == "active"
        assert limited.json()["discovery"]["state"] == "failed"
        assert "RAW-PROVIDER-SECRET-DETAIL" not in limited.text
        after_rate_limit = client.get("/api/v1/runtime-models").json()["models"][0]
        assert after_rate_limit["capabilities"] == before["capabilities"]
        assert after_rate_limit["verification"]["state"] == "stale"
        assert (
            after_rate_limit["verification"]["stale_reason"] == "model_discovery_failed"
        )
        assert after_rate_limit["registry_ready"] is False

        provider.discovery_error = RuntimeProviderError(
            "runtime_unauthorized", "RAW-AUTH-DETAIL"
        )
        unauthorized = client.post(
            f"/api/v1/runtime-credentials/{credential_id}/validate"
        )
        assert unauthorized.json()["credential"]["status"] == "invalid"
        assert "RAW-AUTH-DETAIL" not in unauthorized.text
        after_auth = client.get("/api/v1/runtime-models").json()["models"][0]
        assert after_auth["capabilities"] == before["capabilities"]
        assert after_auth["verification"]["state"] == "stale"
        assert after_auth["registry_ready"] is False


def test_provider_lifecycle_endpoint_change_disable_and_delete_invalidate_registry(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(
        [{"id": "fake-model", "capabilities": {"text_generation": True}}]
    )
    with _client(tmp_path, provider) as client:
        created = _create_credential(client, make_default=True)
        credential_id = created["credential"]["credential_id"]
        profile = created["models"][0]
        default = client.get("/api/v1/runtime-models/defaults").json()["defaults"]
        assert default[0]["role"] == "primary"
        assert default[0]["model_profile_id"] == profile["model_profile_id"]

        project = client.post("/api/v1/projects", json={"name": "Registry binding"})
        assert project.status_code == 201, project.text
        project_id = project.json()["project_id"]
        binding = client.patch(
            f"/api/v1/projects/{project_id}/runtime-binding",
            json={"credential_id": credential_id, "model_id": "fake-model"},
        )
        assert binding.status_code == 200, binding.text
        mapped = client.app.state.model_registry.runtime_binding_profiles(project_id)
        assert mapped == {"project": {"primary_model": profile["model_profile_id"]}}

        changed = client.patch(
            f"/api/v1/runtime-credentials/{credential_id}",
            json={"base_url": "http://127.0.0.1:9877/v1"},
        )
        assert changed.status_code == 200, changed.text
        stale = client.get("/api/v1/runtime-models").json()["models"][0]
        assert stale["connection_readiness"] == "unverified"
        assert stale["verification"]["state"] == "stale"
        assert stale["verification"]["stale_reason"] == "provider_endpoint_changed"
        assert stale["registry_ready"] is False
        mapped = client.app.state.model_registry.runtime_binding_profiles(project_id)
        assert mapped == {"project": {"primary_model": "__unresolved_binding__"}}

        rediscovered = client.post(
            f"/api/v1/runtime-credentials/{credential_id}/models/discover"
        )
        assert rediscovered.status_code == 200, rediscovered.text
        assert rediscovered.json()["discovery"]["state"] == "ready"
        active = client.get("/api/v1/runtime-models").json()["models"][0]
        assert active["registry_ready"] is True

        disabled = client.post(f"/api/v1/runtime-credentials/{credential_id}/disable")
        assert disabled.status_code == 200
        disabled_profile = client.get("/api/v1/runtime-models").json()["models"][0]
        assert disabled_profile["connection_readiness"] == "disabled"
        assert disabled_profile["verification"]["state"] == "stale"
        assert disabled_profile["registry_ready"] is False

        deleted = client.delete(f"/api/v1/runtime-credentials/{credential_id}")
        assert deleted.status_code == 200
        assert client.get("/api/v1/runtime-models").json()["models"] == []
        assert client.get("/api/v1/runtime-models/defaults").json()["defaults"] == []
