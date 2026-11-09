"""A graph image timeout is an unknown paid effect, including old event shapes."""

from __future__ import annotations

from pathlib import Path

import pytest

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.runtime.client import RuntimeProviderError

from .test_runtime_model_capability_preflight import (
    MetadataImageRuntimeTransport,
    _bind_primary,
    _client,
    _create_credential,
)
from .test_runtime_resume import _resume
from .test_runtime_routes import _agent_source, _await_run


@pytest.mark.parametrize("historical_events", [False, True])
@pytest.mark.parametrize("command", ["retry", "resume"])
def test_graph_image_retry_never_replays_dispatched_generation(
    tmp_path: Path, historical_events: bool, command: str
):
    class TimedOutImages(MetadataImageRuntimeTransport):
        def generate_images(self, prompt, *, count=1, size=None):
            self.image_calls.append((prompt, count))
            raise RuntimeProviderError(
                "runtime_timeout", "Synthetic dispatched image timeout"
            )

    transport = TimedOutImages()
    source = _agent_source()
    source["outputs"] = {"render": "image"}
    source["nodes"][1].update(model_ref="model.image", outputs={"render": "image"})
    source["nodes"][2]["output_name"] = "render"
    with _client(tmp_path, transport) as client:
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        p, a = project["project_id"], project["agents"][0]["agent_id"]
        credential = _create_credential(client)
        _bind_primary(client, p, credential)
        profile = next(
            item
            for item in client.app.state.model_registry.list_profiles_for_connection(
                credential
            )
            if item.provider_model_id == "scripted-image-model"
        )
        client.app.state.model_registry.set_default(
            "image_generation", profile.model_profile_id
        )
        prefix = f"/api/v1/projects/{p}/agents/{a}"
        started = client.post(
            f"{prefix}/run",
            json={"inputs": {"request": "Draw a blue test box"}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 200, started.text
        done = _await_run(client, f"{prefix}/run", started.json()["run_id"])
        assert done["status"] == "failed" and done["error"]["code"] == "runtime_timeout"
        assert len(transport.image_calls) == 1
        repository = client.app.state.runtime.repository
        if historical_events:
            with repository.transaction() as connection:
                connection.execute(
                    "DELETE FROM runtime_run_events WHERE run_id=? "
                    "AND kind='node.started' "
                    "AND json_extract(payload_json,'$.phase')='image'",
                    (done["run_id"],),
                )
        before = client.get(f"{prefix}/runs/{done['run_id']}").json()
        retry = (
            _resume(client, f"{prefix}/run", before)
            if command == "resume"
            else client.post(
                f"{prefix}/runs/{done['run_id']}/commands",
                json={"command": "retry"},
                headers={"Idempotency-Key": new_uuid7()},
            )
        )
        assert (
            retry.status_code == 422
            and retry.json()["code"] == f"{command}_effect_unsafe"
        )
        assert len(transport.image_calls) == 1
        assert client.get(f"{prefix}/runs/{done['run_id']}").json() == before
        assert len(client.get(f"{prefix}/runs").json()["runs"]) == 1
