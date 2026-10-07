"""Give isolated Runtime fixtures a verified scripted model, never a host key."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from fastapi.testclient import TestClient

from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.models.contracts import CapabilityStatus
from veyra_agent_platform.local.secrets import DeviceSecretStore


class MemorySecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, secret_ref: str) -> str | None:
        return self.values.get(secret_ref)

    def set(self, secret_ref: str, value: str) -> None:
        self.values[secret_ref] = value

    def delete(self, secret_ref: str) -> None:
        self.values.pop(secret_ref, None)


RUNTIME_TEXT_CAPABILITIES = (
    "text_generation",
    "image_input",
    "structured_output",
    "tool_calling",
)


def register_verified_model(
    client: TestClient,
    *,
    capabilities: Sequence[str] = RUNTIME_TEXT_CAPABILITIES,
    model_id: str = "kimi-k3",
) -> str:
    """Add a scripted credential whose model has active-probe evidence.

    The app must use an in-memory secret store so tests never write the
    developer's system keyring.
    """
    assert not isinstance(client.app.state.secrets, DeviceSecretStore)
    created = client.post(
        "/api/v1/runtime-credentials",
        json={
            "provider_type": "moonshot",
            "label": "Scripted test model",
            "api_key": "test-only-runtime-key",
            "default_model_id": model_id,
        },
    )
    assert created.status_code == 201, created.text
    credential_id = created.json()["credential"]["credential_id"]
    registry = client.app.state.model_registry
    profiles = registry.list_profiles_for_connection(credential_id)
    profile = next(item for item in profiles if item.provider_model_id == model_id)
    for capability in capabilities:
        registry.record_capability_probe(
            profile.model_profile_id,
            capability,
            CapabilityStatus.SUPPORTED,
            detail="Scripted test transport supports this capability.",
        )
    return credential_id


@contextmanager
def verified_client(
    settings: LocalSettings,
    runtime_transport: object,
    *,
    capabilities: Sequence[str] = RUNTIME_TEXT_CAPABILITIES,
    **kwargs: Any,
) -> Iterator[TestClient]:
    kwargs.setdefault("secret_store", MemorySecretStore())
    app = create_app(settings, runtime_transport=runtime_transport, **kwargs)
    with TestClient(app) as client:
        register_verified_model(client, capabilities=capabilities)
        yield client
