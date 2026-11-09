"""Builder reuses deliberate verified choices without contacting a Provider."""

from pathlib import Path

from fastapi.testclient import TestClient

from tests.integration.local.verified_runtime_model import (
    MemorySecretStore,
    register_verified_model,
)
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.models.contracts import CapabilityStatus


class ScriptedModels:
    def models(self):
        return ("kimi-k3",)

    def validate(self):
        return None

    def complete(self, *args, **kwargs):
        raise AssertionError("Preflight must not call the Runtime model")


def client_for(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            LocalSettings(
                database_url=f"sqlite:///{tmp_path / 'local.sqlite'}",
                project_storage_root=tmp_path / "projects",
            ),
            secret_store=MemorySecretStore(),
            runtime_transport=ScriptedModels(),
        )
    )


def test_existing_verified_default_skips_repetitive_builder_binding(
    tmp_path: Path,
) -> None:
    with client_for(tmp_path) as client:
        project = client.post(
            "/api/v1/projects", json={"name": "Isolated gate"}
        ).json()["project_id"]
        credential = register_verified_model(client, capabilities=("text_generation",))
        registry = client.app.state.model_registry
        profile = registry.list_profiles_for_connection(credential)[0]
        registry.set_default("primary", profile.model_profile_id)
        gate = client.app.state.runtime.builder_runtime_preflight(project)
        assert gate["status"] == "ready" and gate["binding_source"] == "user_default"
        assert gate["model_profile_id"] == profile.model_profile_id
        assert client.app.state.provider_credentials.binding(project, None) is None
        registry.record_capability_probe(
            profile.model_profile_id, "text_generation", CapabilityStatus.UNSUPPORTED
        )
        assert (
            client.app.state.runtime.builder_runtime_preflight(project)["status"]
            == "waiting_for_runtime_binding"
        )


def test_verified_but_unselected_profile_does_not_become_implicit_default(
    tmp_path: Path,
) -> None:
    with client_for(tmp_path) as client:
        project = client.post(
            "/api/v1/projects", json={"name": "Isolated gate"}
        ).json()["project_id"]
        credential = register_verified_model(client, capabilities=("text_generation",))
        registry = client.app.state.model_registry
        for role in ("primary", "primary_model", "text_generation"):
            registry.clear_default(role)
        assert (
            client.app.state.runtime.builder_runtime_preflight(project)["status"]
            == "waiting_for_runtime_binding"
        )
        profile = registry.list_profiles_for_connection(credential)[0]
        client.app.state.provider_credentials.set_binding(
            project, None, credential, profile.provider_model_id
        )
        gate = client.app.state.runtime.builder_runtime_preflight(project)
        assert gate["status"] == "ready" and gate["binding_source"] == "project"
        client.app.state.provider_credentials.set_status(credential, "disabled")
        assert (
            client.app.state.runtime.builder_runtime_preflight(project)["status"]
            != "ready"
        )
