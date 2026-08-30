from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.factory import (
    FactorySettings,
    KimiClient,
    KimiCompletion,
)

ROOT = Path(__file__).resolve().parents[3]


class _FakeKimiTransport:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[list[dict[str, Any]]] = []

    def models(self) -> tuple[str, ...]:
        return ("kimi-k3",)

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
    ) -> KimiCompletion:
        assert response_format is not None or messages[0]["role"] == "system"
        self.calls.append(messages)
        return KimiCompletion(
            content=self.content,
            assistant_message={"role": "assistant", "content": self.content},
            finish_reason="stop",
        )


def _settings(tmp_path: Path) -> LocalSettings:
    return LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )


def test_factory_generates_reviewable_draft_then_applies_explicitly(
    tmp_path: Path,
) -> None:
    blueprint = json.loads(
        (
            ROOT / "contracts/fixtures/schema_parity/valid-agent-blueprint.json"
        ).read_text()
    )
    fake = _FakeKimiTransport(json.dumps(blueprint))
    with TestClient(create_app(_settings(tmp_path))) as client:
        client.app.state.factory.client = KimiClient(FactorySettings(), fake)
        project = client.post("/api/v1/projects", json={"name": "Factory"}).json()
        project_id = project["project_id"]
        session = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "Return the supplied value."},
        )
        assert session.status_code == 201
        session_id = session.json()["session_id"]
        generated = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/generate"
        )
        assert generated.status_code == 200
        assert generated.json()["state"] == "review"
        assert generated.json()["blueprint"]["goal"] == "Return the supplied value."
        assert len(fake.calls) == 1

        applied = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/apply-draft",
            json={"confirm": True, "name": "Value Agent"},
        )
        assert applied.status_code == 200
        assert applied.json()["session"]["state"] == "completed"
        assert applied.json()["agent"]["name"] == "Value Agent"
        assert client.get(f"/api/v1/projects/{project_id}").json()["agent_count"] == 1


def test_factory_requires_explicit_confirmation_and_surfaces_provider_gap(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        project = client.post("/api/v1/projects", json={"name": "Factory"}).json()
        project_id = project["project_id"]
        session = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "Make a draft"},
        ).json()
        session_id = session["session_id"]
        not_ready = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/apply-draft",
            json={"confirm": False},
        )
        assert not_ready.status_code == 422
        assert not_ready.json()["code"] == "factory_confirmation_required"
        unavailable = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/generate"
        )
        assert unavailable.status_code == 503
        assert unavailable.json()["code"] == "factory_provider_not_configured"
