from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.models.contracts import CapabilityStatus
from veyra_agent_platform.local.runtime.client import GeneratedImage, RuntimeCompletion
from veyra_agent_platform.local.secrets import MacOSKeychainSecretStore

from .test_loop_resource_truth import _loop_source
from .test_provider_credentials import MemorySecretStore
from .test_runtime_routes import _await_run

_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


class ImageRuntimeTransport:
    def __init__(self, completion: str | None = None) -> None:
        self.completion = completion or (
            '{"action":"final","outputs":{"brief":"cream paper and blue ribbon"}}'
        )
        self.completion_calls: list[Any] = []
        self.image_calls: list[tuple[str, int]] = []

    def models(self) -> tuple[str, ...]:
        return ("primary-text",)

    def complete(
        self, messages: Any, *, response_format: Any = None
    ) -> RuntimeCompletion:
        self.completion_calls.append((messages, response_format))
        return RuntimeCompletion(content=self.completion, finish_reason="stop")

    def generate_images(
        self, prompt: str, *, count: int = 1, size: str | None = None
    ) -> list[GeneratedImage]:
        del size
        self.image_calls.append((prompt, count))
        return [
            GeneratedImage(contents=_PNG, media_type="image/png") for _ in range(count)
        ]


class MetadataImageRuntimeTransport(ImageRuntimeTransport):
    def models(self) -> tuple[str, ...]:
        return ("primary-text", "scripted-image-model")

    def discover_models(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "primary-text",
                "capabilities": {"text_generation": True},
            },
            {
                "id": "scripted-image-model",
                "capabilities": {"image_generation": True},
            },
        ]


class SetupOnlyRuntimeTransport(ImageRuntimeTransport):
    def __init__(self) -> None:
        super().__init__()
        self.model_discovery_calls = 0

    def models(self) -> tuple[str, ...]:
        self.model_discovery_calls += 1
        return ("primary-text", "scripted-image-model")


@pytest.fixture(autouse=True)
def isolate_runtime_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MacOSKeychainSecretStore, "get", lambda self, ref: None)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("VEYRA_RUNTIME_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("VEYRA_RUNTIME_MODEL_ID", raising=False)


def _client(tmp_path: Path, transport: ImageRuntimeTransport) -> TestClient:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'db' / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    return TestClient(
        create_app(
            settings,
            runtime_transport=transport,
            secret_store=MemorySecretStore(),
        )
    )


def _source(*, image_output: bool = True) -> dict[str, Any]:
    source = _loop_source("Design gift packaging from the user's product request.")
    source["inputs"] = {"request": "string"}
    source["outputs"] = (
        {
            "brief": "string",
            "render": {"type": "artifact", "artifact_kind": "image"},
        }
        if image_output
        else {"result": "string"}
    )
    if not image_output:
        source["outputs"] = {"result": "string"}
    primary_output = "brief" if image_output else "result"
    for node in source.get("nodes") or []:
        if node.get("component_type") == "Output":
            node["output_name"] = primary_output
    return source


def _create_project(client: TestClient, source: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        "/api/v1/projects", json={"name": "Runtime setup", "agents": [source]}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_credential(
    client: TestClient,
    *,
    label: str = "Scripted Runtime",
    default_model_id: str = "primary-text",
    make_default: bool = False,
) -> str:
    response = client.post(
        "/api/v1/runtime-credentials",
        json={
            "provider_type": "moonshot",
            "label": label,
            "api_key": "test-only-runtime-key",
            "default_model_id": default_model_id,
            "make_default": make_default,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["credential"]["credential_id"]


def _add_profile(
    client: TestClient,
    credential_id: str,
    model_id: str,
    capabilities: dict[str, CapabilityStatus],
):
    registry = client.app.state.model_registry
    profile = registry.add_manual_model(credential_id, model_id)
    for capability, status in capabilities.items():
        profile = registry.record_capability_probe(
            profile.model_profile_id,
            capability,
            status,
            detail="Scripted test evidence; no Provider request was made.",
        )
    return profile


def _bind_primary(client: TestClient, project_id: str, credential_id: str) -> None:
    response = client.patch(
        f"/api/v1/projects/{project_id}/runtime-binding",
        json={"credential_id": credential_id, "model_id": "primary-text"},
    )
    assert response.status_code == 200, response.text


def _runtime_readiness(client: TestClient, project_id: str, agent_id: str):
    return client.get(
        f"/api/v1/projects/{project_id}/agents/{agent_id}/runtime-readiness"
    )


def _commit_agent(client: TestClient, project_id: str, agent_id: str) -> str:
    url = f"/api/v1/projects/{project_id}/agents/{agent_id}"
    draft = client.get(f"{url}/draft").json()
    response = client.post(
        f"{url}/commit",
        json={"expected_revision": draft["revision"]},
        headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
    )
    assert response.status_code == 200, response.text
    return response.json()["version_id"]


def test_unbound_image_model_uses_declared_registry_default_and_matching_evidence(
    tmp_path: Path,
) -> None:
    transport = MetadataImageRuntimeTransport()
    with _client(tmp_path, transport) as client:
        source = _source()
        project = _create_project(client, source)
        project_id = project["project_id"]
        agent_id = project["agents"][0]["agent_id"]
        agent_url = f"/api/v1/projects/{project_id}/agents/{agent_id}"
        draft_before = client.get(f"{agent_url}/draft").json()
        version_id = _commit_agent(client, project_id, agent_id)

        credential_id = _create_credential(client)
        profiles = {
            profile.provider_model_id: profile
            for profile in client.app.state.model_registry.list_profiles_for_connection(
                credential_id
            )
        }
        primary = profiles["primary-text"]
        image = profiles["scripted-image-model"]
        assert primary.verification.state.value == "declared"
        assert primary.registry_ready is True
        assert (
            primary.capabilities["text_generation"].evidence.source.value
            == "provider_metadata"
        )
        assert image.verification.state.value == "declared"
        assert image.registry_ready is True
        assert (
            image.capabilities["image_generation"].evidence.source.value
            == "provider_metadata"
        )
        _bind_primary(client, project_id, credential_id)
        client.app.state.model_registry.set_default(
            "image_generation", image.model_profile_id
        )

        ready = _runtime_readiness(client, project_id, agent_id)
        assert ready.status_code == 200, ready.text
        assert ready.json()["ready"] is True, ready.json()
        assert ready.json()["setup_issues"] == []
        assert (
            client.get(f"{agent_url}/runtime-binding?slot=image_model").json()[
                "explicit"
            ]
            is None
        )

        started = client.post(
            f"{agent_url}/run",
            json={
                "inputs": {"request": "a gift for a new graduate"},
                "source": "committed",
                "version_id": version_id,
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 200, started.text
        settled = _await_run(client, f"{agent_url}/run", started.json()["run_id"])
        assert settled["status"] in {"unverified", "verified"}
        assert len(transport.image_calls) == 1
        detail = client.get(f"{agent_url}/runs/{settled['run_id']}").json()
        image_event = next(
            event
            for event in detail["events"]
            if event["kind"] == "node.started" and event["node_id"] == "render_render"
        )
        assert image_event["payload"]["model"] == "scripted-image-model"
        assert image_event["payload"]["model_profile_id"] == image.model_profile_id
        assert image_event["payload"]["capability_digest"] == image.capability_digest
        assert image_event["payload"]["binding_source"] == "model_registry_default"
        assert (
            client.get(f"{agent_url}/draft").json()["source"] == draft_before["source"]
        )


def test_unsupported_explicit_image_binding_blocks_before_any_image_provider_call(
    tmp_path: Path,
) -> None:
    transport = ImageRuntimeTransport()
    with _client(tmp_path, transport) as client:
        project = _create_project(client, _source())
        project_id = project["project_id"]
        agent_id = project["agents"][0]["agent_id"]
        agent_url = f"/api/v1/projects/{project_id}/agents/{agent_id}"
        credential_id = _create_credential(client)
        primary = client.app.state.model_registry.list_profiles_for_connection(
            credential_id
        )[0]
        client.app.state.model_registry.record_capability_probe(
            primary.model_profile_id,
            "text_generation",
            CapabilityStatus.SUPPORTED,
            detail="Scripted completion capability.",
        )
        _bind_primary(client, project_id, credential_id)
        vision_only = _add_profile(
            client,
            credential_id,
            "vision-only-model",
            {
                "image_input": CapabilityStatus.SUPPORTED,
                "image_generation": CapabilityStatus.UNSUPPORTED,
            },
        )
        client.app.state.model_registry.set_default(
            "image_generation", primary.model_profile_id
        )
        bound = client.patch(
            f"{agent_url}/runtime-binding",
            json={
                "credential_id": credential_id,
                "model_id": "vision-only-model",
                "slot": "image_model",
            },
        )
        assert bound.status_code == 200, bound.text

        ready = _runtime_readiness(client, project_id, agent_id).json()
        assert ready["ready"] is False
        issue = next(
            item for item in ready["setup_issues"] if item["scope"] == "image_model"
        )
        assert issue["code"] == "model_capability_mismatch"
        assert issue["requirement"] == ["image_generation"]
        assert issue["action"] == "rebind_model"

        started = client.post(
            f"{agent_url}/run",
            json={"inputs": {"request": "a gift"}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 422
        assert started.json()["code"] == "model_capability_mismatch", started.text
        assert not transport.completion_calls
        assert not transport.image_calls
        assert vision_only.model_profile_id != primary.model_profile_id


def test_unknown_image_generation_profile_does_not_satisfy_unbound_role(
    tmp_path: Path,
) -> None:
    transport = ImageRuntimeTransport()
    with _client(tmp_path, transport) as client:
        project = _create_project(client, _source())
        project_id = project["project_id"]
        agent_id = project["agents"][0]["agent_id"]
        agent_url = f"/api/v1/projects/{project_id}/agents/{agent_id}"
        credential_id = _create_credential(client)
        primary = client.app.state.model_registry.list_profiles_for_connection(
            credential_id
        )[0]
        client.app.state.model_registry.record_capability_probe(
            primary.model_profile_id,
            "text_generation",
            CapabilityStatus.SUPPORTED,
            detail="Scripted completion capability.",
        )
        _bind_primary(client, project_id, credential_id)
        client.app.state.model_registry.add_manual_model(
            credential_id, "unverified-image-model"
        )

        ready = _runtime_readiness(client, project_id, agent_id).json()
        assert ready["ready"] is False
        issue = next(
            item for item in ready["setup_issues"] if item["scope"] == "image_model"
        )
        assert issue["code"] == "model_capability_unverified"
        assert issue["action"] == "verify_model"

        started = client.post(
            f"{agent_url}/run",
            json={"inputs": {"request": "a gift"}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 422
        assert started.json()["code"] == "model_capability_unverified"
        assert not transport.completion_calls
        assert not transport.image_calls


def test_explicit_stale_image_binding_does_not_fall_back_to_compatible_default(
    tmp_path: Path,
) -> None:
    transport = ImageRuntimeTransport()
    with _client(tmp_path, transport) as client:
        project = _create_project(client, _source())
        project_id = project["project_id"]
        agent_id = project["agents"][0]["agent_id"]
        agent_url = f"/api/v1/projects/{project_id}/agents/{agent_id}"

        primary_credential = _create_credential(client, label="Primary")
        primary = client.app.state.model_registry.list_profiles_for_connection(
            primary_credential
        )[0]
        client.app.state.model_registry.record_capability_probe(
            primary.model_profile_id,
            "text_generation",
            CapabilityStatus.SUPPORTED,
            detail="Scripted completion capability.",
        )
        _bind_primary(client, project_id, primary_credential)

        stale_credential = _create_credential(client, label="Stale image")
        stale_image = _add_profile(
            client,
            stale_credential,
            "stale-image-model",
            {"image_generation": CapabilityStatus.SUPPORTED},
        )
        fallback_credential = _create_credential(client, label="Image default")
        compatible = _add_profile(
            client,
            fallback_credential,
            "compatible-image-model",
            {"image_generation": CapabilityStatus.SUPPORTED},
        )
        client.app.state.model_registry.set_default(
            "image_generation", compatible.model_profile_id
        )
        bound = client.patch(
            f"{agent_url}/runtime-binding",
            json={
                "credential_id": stale_credential,
                "model_id": stale_image.provider_model_id,
                "slot": "image_model",
            },
        )
        assert bound.status_code == 200, bound.text
        client.app.state.model_registry.mark_discovery_failure(
            stale_credential,
            error_code="model_discovery_failed",
            state="stale",
        )

        ready = _runtime_readiness(client, project_id, agent_id).json()
        assert ready["ready"] is False
        issue = next(
            item for item in ready["setup_issues"] if item["scope"] == "image_model"
        )
        assert issue["code"] == "model_profile_stale"
        assert issue.get("model_profile_id") in {None, stale_image.model_profile_id}

        started = client.post(
            f"{agent_url}/run",
            json={"inputs": {"request": "a gift"}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 422
        assert started.json()["code"] == "model_profile_stale"
        assert not transport.completion_calls
        assert not transport.image_calls


def test_workflow_readiness_and_run_fail_closed_on_pinned_child_setup_issue(
    tmp_path: Path,
) -> None:
    transport = ImageRuntimeTransport()
    with _client(tmp_path, transport) as client:
        source = _loop_source("Summarize the user's packaging request.")
        source["inputs"] = {"request": "string"}
        source["outputs"] = {"result": "string"}
        for node in source.get("nodes") or []:
            if node.get("component_type") == "Output":
                node["output_name"] = "result"
        project = _create_project(client, source)
        project_id = project["project_id"]
        agent_id = project["agents"][0]["agent_id"]
        agent_url = f"/api/v1/projects/{project_id}/agents/{agent_id}"

        credential_id = _create_credential(client, make_default=True)
        # The discovered Provider model intentionally has no verified
        # text_generation evidence. It must not satisfy a pinned child Agent.
        version_id = _commit_agent(client, project_id, agent_id)

        created = client.post(
            f"/api/v1/projects/{project_id}/workflows",
            json={"name": "Child model setup"},
        )
        assert created.status_code == 201, created.text
        workflow_id = created.json()["workflow_id"]
        workflow_url = f"/api/v1/projects/{project_id}/workflows/{workflow_id}"
        draft = client.get(f"{workflow_url}/draft").json()
        workflow_source = draft["source"]
        reference = f"{agent_id}@{version_id}"
        workflow_source.update(
            {
                "inputs": {"request": "string"},
                "outputs": {"result": "string"},
                "nodes": [
                    {"id": "start", "component_type": "Start"},
                    {
                        "id": "call",
                        "component_type": "AgentCall",
                        "agent_ref": reference,
                        "input_mapping": {"request": "request"},
                        "output_mapping": {"result": "result"},
                    },
                    {
                        "id": "output",
                        "component_type": "Output",
                        "output_name": "result",
                    },
                ],
                "transitions": [
                    {"from": "start", "port": "next", "to": "call"},
                    {"from": "call", "port": "next", "to": "output"},
                ],
                "lock": {
                    reference: client.get(f"{agent_url}/versions").json()["versions"][
                        0
                    ]["source_hash"]
                },
                "ui": {
                    "positions": {
                        "start": {"x": 0, "y": 0},
                        "call": {"x": 200, "y": 0},
                        "output": {"x": 400, "y": 0},
                    }
                },
            }
        )
        saved = client.patch(
            f"{workflow_url}/draft",
            json={"source": workflow_source, "expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert saved.status_code == 200, saved.text
        workflow_draft = client.get(f"{workflow_url}/draft").json()
        committed = client.post(
            f"{workflow_url}/commit",
            json={"expected_revision": workflow_draft["revision"]},
            headers={
                "If-Match": workflow_draft["etag"],
                "Idempotency-Key": new_uuid7(),
            },
        )
        assert committed.status_code == 200, committed.text
        workflow_version_id = committed.json()["version_id"]

        ready = client.get(
            f"{workflow_url}/runtime-readiness?version_id={workflow_version_id}"
        )
        assert ready.status_code == 200, ready.text
        payload = ready.json()
        assert payload["ready"] is False
        assert payload["calls"][0]["setup_issues"][0]["agent_id"] == agent_id
        assert payload["calls"][0]["setup_issues"][0]["node_id"] == "call"
        assert payload["setup_issues"][0]["scope"] == "call.primary_model"
        assert payload["setup_issues"][0]["requirement"] == ["text_generation"]

        started = client.post(
            f"{workflow_url}/run",
            json={
                "inputs": {"request": "Summarize this package"},
                "source": "committed",
                "version_id": workflow_version_id,
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 422
        assert started.json()["code"] == "model_capability_unverified"
        assert client.get(f"{workflow_url}/runs").json()["runs"] == []
        assert not transport.completion_calls
        assert not transport.image_calls
        assert credential_id


def test_imported_committed_image_agent_reaches_ready_without_source_change(
    tmp_path: Path,
) -> None:
    transport = SetupOnlyRuntimeTransport()
    with _client(tmp_path, transport) as client:
        project = client.post("/api/v1/projects", json={"name": "Acceptance J"})
        assert project.status_code == 201, project.text
        project_id = project.json()["project_id"]

        imported = client.post(
            f"/api/v1/projects/{project_id}/agents/import",
            files={
                "file": (
                    "gift-packaging.vagent.yaml",
                    json.dumps(_source(), ensure_ascii=False).encode("utf-8"),
                    "application/yaml",
                )
            },
        )
        assert imported.status_code == 201, imported.text
        agent_id = imported.json()["agent_id"]
        agent_url = f"/api/v1/projects/{project_id}/agents/{agent_id}"
        version_id = _commit_agent(client, project_id, agent_id)
        committed_versions = client.get(f"{agent_url}/versions").json()["versions"]
        committed = next(
            item for item in committed_versions if item["version_id"] == version_id
        )
        source_hash = committed["source_hash"]
        draft_before = client.get(f"{agent_url}/draft").json()

        initial = client.get(
            f"{agent_url}/runtime-readiness", params={"version_id": version_id}
        )
        assert initial.status_code == 200, initial.text
        initial_payload = initial.json()
        assert initial_payload["ready"] is False
        assert initial_payload["version_id"] == version_id
        image_issue = next(
            item
            for item in initial_payload["setup_issues"]
            if item["scope"] == "image_model"
        )
        assert image_issue["code"] == "image_model_not_configured"
        assert image_issue["requirement"] == ["image_generation"]
        assert transport.model_discovery_calls == 0
        assert not transport.completion_calls
        assert not transport.image_calls

        credential_id = _create_credential(client)
        registry = client.app.state.model_registry
        profiles = {
            profile.provider_model_id: profile
            for profile in registry.list_profiles_for_connection(credential_id)
        }
        primary = registry.record_capability_probe(
            profiles["primary-text"].model_profile_id,
            "text_generation",
            CapabilityStatus.SUPPORTED,
            detail="Scripted text capability evidence; no model request was made.",
        )
        image = registry.record_capability_probe(
            profiles["scripted-image-model"].model_profile_id,
            "image_generation",
            CapabilityStatus.SUPPORTED,
            detail="Scripted image capability evidence; no model request was made.",
        )
        _bind_primary(client, project_id, credential_id)
        registry.set_default("image_generation", image.model_profile_id)
        assert image.registry_ready is True
        assert (
            image.capabilities["image_generation"].evidence.source.value
            == "active_probe"
        )
        calls_before_recheck = (
            transport.model_discovery_calls,
            len(transport.completion_calls),
            len(transport.image_calls),
        )

        refreshed = client.get(
            f"{agent_url}/runtime-readiness", params={"version_id": version_id}
        )
        assert refreshed.status_code == 200, refreshed.text
        refreshed_payload = refreshed.json()
        assert refreshed_payload["ready"] is True, refreshed_payload
        assert refreshed_payload["setup_issues"] == []
        assert refreshed_payload["version_id"] == version_id
        versions_after = client.get(f"{agent_url}/versions").json()["versions"]
        same_version = next(
            item for item in versions_after if item["version_id"] == version_id
        )
        assert same_version["source_hash"] == source_hash
        draft_after = client.get(f"{agent_url}/draft").json()
        assert draft_after["source"] == draft_before["source"]
        assert draft_after["revision"] == draft_before["revision"]
        assert calls_before_recheck == (
            transport.model_discovery_calls,
            len(transport.completion_calls),
            len(transport.image_calls),
        )
        assert not transport.completion_calls
        assert not transport.image_calls
        assert primary.registry_ready is True
