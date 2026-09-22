from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.runtime.tools import ProducedArtifact, ToolExecution
from veyra_agent_platform.local.secrets import MacOSKeychainSecretStore

from .test_runtime_routes import (
    ScriptedRuntimeTransport,
    _agent_source,
    _await_run,
    _source,
)

_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)
_PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@pytest.fixture(autouse=True)
def isolate_runtime_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MacOSKeychainSecretStore, "get", lambda self, ref: None)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)


def _client(tmp_path: Path, **kwargs: object) -> TestClient:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'db' / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    return TestClient(create_app(settings, **kwargs))


def _image_agent() -> dict[str, object]:
    source = _source(
        [
            {"id": "start", "component_type": "Start"},
            {
                "id": "transform",
                "component_type": "Transform",
                "mapping": {"result": "described"},
            },
            {"id": "output", "component_type": "Output", "output_name": "result"},
        ],
        [
            {"from": "start", "port": "next", "to": "transform"},
            {"from": "transform", "port": "next", "to": "output"},
        ],
        {"photo": "image"},
    )
    source["outputs"] = {"result": "string"}
    return source


def _upload(client: TestClient, project_id: str, name: str, payload: bytes, mime: str):
    return client.post(
        f"/api/v1/projects/{project_id}/artifacts",
        files={"file": (name, payload, mime)},
    )


def test_artifact_input_persists_ref_and_rejects_cross_project(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        first = client.post(
            "/api/v1/projects", json={"agents": [_image_agent()]}
        ).json()
        second = client.post(
            "/api/v1/projects", json={"agents": [_image_agent()]}
        ).json()
        uploaded = _upload(
            client, first["project_id"], "product.png", _PNG, "image/png"
        ).json()
        ref = {
            "kind": "artifact",
            "artifact_id": uploaded["artifact_id"],
            "media_type": "image/png",
            "filename": "product.png",
        }
        url = (
            f"/api/v1/projects/{first['project_id']}/agents/"
            f"{first['agents'][0]['agent_id']}/run"
        )
        started = client.post(
            url,
            json={"inputs": {"photo": ref}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 200, started.text
        settled = _await_run(client, url, started.json()["run_id"])
        assert settled["status"] == "unverified"
        assert settled["result"] == {"result": "described"}
        stored = client.app.state.runtime.repository.run_inputs(settled["run_id"])
        assert stored == {"photo": ref}
        assert "bytes" not in str(stored)
        stolen = client.post(
            f"/api/v1/projects/{second['project_id']}/agents/"
            f"{second['agents'][0]['agent_id']}/run",
            json={"inputs": {"photo": ref}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert stolen.status_code == 422
        assert stolen.json()["code"] == "inputs_invalid"


def test_missing_wrong_mime_and_multiple_artifacts(tmp_path: Path) -> None:
    source = _image_agent()
    source["inputs"] = {
        "photos": {
            "type": "artifact",
            "artifact_kind": "image",
            "multiple": True,
        }
    }
    with _client(tmp_path) as client:
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        pdf = _upload(
            client, project["project_id"], "report.pdf", _PDF, "application/pdf"
        ).json()
        first = _upload(
            client, project["project_id"], "one.png", _PNG, "image/png"
        ).json()
        second = _upload(
            client, project["project_id"], "two.png", _PNG, "image/png"
        ).json()
        url = (
            f"/api/v1/projects/{project['project_id']}/agents/"
            f"{project['agents'][0]['agent_id']}/run"
        )
        missing = client.post(
            url,
            json={
                "inputs": {
                    "photos": [
                        {
                            "kind": "artifact",
                            "artifact_id": "art_missing",
                            "media_type": "image/png",
                            "filename": "gone.png",
                        }
                    ]
                }
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert missing.status_code == 422
        assert missing.json()["code"] == "inputs_invalid"
        wrong = client.post(
            url,
            json={
                "inputs": {
                    "photos": [
                        {
                            "kind": "artifact",
                            "artifact_id": pdf["artifact_id"],
                            "media_type": "application/pdf",
                            "filename": "report.pdf",
                        }
                    ]
                }
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert wrong.status_code == 422
        ok = client.post(
            url,
            json={
                "inputs": {
                    "photos": [
                        {
                            "kind": "artifact",
                            "artifact_id": first["artifact_id"],
                            "media_type": "image/png",
                            "filename": "one.png",
                        },
                        {"$artifact": second["artifact_id"]},
                    ]
                }
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        settled = _await_run(client, url, ok.json()["run_id"])
        assert settled["status"] == "unverified"
        stored = client.app.state.runtime.repository.run_inputs(settled["run_id"])
        assert [item["artifact_id"] for item in stored["photos"]] == [
            first["artifact_id"],
            second["artifact_id"],
        ]


def test_pdf_string_output_is_invalid_and_tool_emits_artifact_created(
    tmp_path: Path,
) -> None:
    fake = _source(
        [
            {"id": "start", "component_type": "Start"},
            {
                "id": "transform",
                "component_type": "Transform",
                "mapping": {"report": "this is a PDF"},
            },
            {"id": "output", "component_type": "Output", "output_name": "report"},
        ],
        [
            {"from": "start", "port": "next", "to": "transform"},
            {"from": "transform", "port": "next", "to": "output"},
        ],
        {"text": "string"},
    )
    fake["outputs"] = {"report": "pdf"}

    def render_pdf(**_kwargs: object) -> ToolExecution:
        return ToolExecution(
            output={},
            receipt={"outcome": "succeeded"},
            produced_artifacts=(
                ProducedArtifact(
                    field="report",
                    filename="report.pdf",
                    contents=_PDF,
                    claimed_type="application/pdf",
                ),
            ),
        )

    real = _source(
        [
            {"id": "start", "component_type": "Start"},
            {
                "id": "render",
                "component_type": "Tool",
                "uses": "veyra.tool.filesystem.read@1.0.0",
            },
            {"id": "output", "component_type": "Output", "output_name": "report"},
        ],
        [
            {"from": "start", "port": "next", "to": "render"},
            {"from": "render", "port": "next", "to": "output"},
        ],
        {"text": "string"},
    )
    real["outputs"] = {"report": "pdf"}
    real["extensions"]["veyra"]["permissions"] = {
        "network_hosts": [],
        "tools": ["veyra.tool.filesystem.read"],
        "filesystem_read_roots": ["project"],
        "filesystem_write_roots": [],
        "shell_workspace_only": False,
    }
    with _client(
        tmp_path, tool_adapters={"veyra.runtime.filesystem.read": render_pdf}
    ) as client:
        broken = client.post("/api/v1/projects", json={"agents": [fake]}).json()
        broken_url = (
            f"/api/v1/projects/{broken['project_id']}/agents/"
            f"{broken['agents'][0]['agent_id']}/run"
        )
        failed = client.post(
            broken_url,
            json={"inputs": {"text": "hello"}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        settled = _await_run(client, broken_url, failed.json()["run_id"])
        assert settled["status"] == "failed"
        assert settled["error"]["code"] == "output_type_invalid"

        real["lock"]["veyra.tool.filesystem.read@1.0.0"] = (
            client.app.state.resource_catalog.detail(
                "veyra.tool.filesystem.read", "1.0.0"
            )["content_hash"]
        )
        project = client.post("/api/v1/projects", json={"agents": [real]}).json()
        binding = client.post(
            f"/api/v1/projects/{project['project_id']}/resources",
            json={
                key: client.app.state.resource_catalog.by_reference(
                    "veyra.tool.filesystem.read@1.0.0"
                )[key]
                for key in ("reference", "content_hash")
            },
        )
        assert binding.status_code == 201
        url = (
            f"/api/v1/projects/{project['project_id']}/agents/"
            f"{project['agents'][0]['agent_id']}/run"
        )
        started = client.post(
            url,
            json={"inputs": {"text": "Write a report"}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        done = _await_run(client, url, started.json()["run_id"])
        assert done["status"] == "unverified"
        result = done["result"]["report"]
        assert result["kind"] == "artifact"
        assert result["media_type"] == "application/pdf"
        assert "bytes" not in result
        detail = client.get(f"{url}s/{done['run_id']}").json()
        created = [
            event for event in detail["events"] if event["kind"] == "artifact.created"
        ]
        assert len(created) == 1
        payload = created[0]["payload"]
        assert payload["artifact_id"] == result["artifact_id"]
        assert payload["digest"]
        assert payload["node_id"] == "render"
        assert "bytes" not in payload
        blob = str(detail)
        assert "%PDF" not in blob
        assert _PNG.hex() not in blob
        stored = client.app.state.runtime.repository.run_inputs(done["run_id"])
        assert stored == {"text": "Write a report"}
        record, contents = client.app.state.artifacts.read_bytes(
            project["project_id"], result["artifact_id"]
        )
        assert contents == _PDF
        assert record.run_id == done["run_id"]


def test_image_model_run_fails_before_provider_without_vision(
    tmp_path: Path,
) -> None:
    transport = ScriptedRuntimeTransport("a product description")
    source = _agent_source()
    source["inputs"] = {"photo": "image"}
    with _client(tmp_path, runtime_transport=transport) as client:
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        agent = project["agents"][0]
        uploaded = _upload(
            client, project["project_id"], "product.png", _PNG, "image/png"
        ).json()
        ref = {
            "kind": "artifact",
            "artifact_id": uploaded["artifact_id"],
            "media_type": "image/png",
            "filename": "product.png",
        }
        ready = client.get(
            f"/api/v1/projects/{project['project_id']}/agents/"
            f"{agent['agent_id']}/runtime-readiness"
        ).json()
        assert ready["ready"] is False
        modality = next(item for item in ready["checks"] if item["id"] == "modalities")
        assert modality["code"] == "runtime_model_incompatible"
        assert modality["detail"] == "Runtime model does not support image input"
        assert ready["model"]["modalities"]["image_input"] == "unsupported"
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        started = client.post(
            url,
            json={"inputs": {"photo": ref}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 422
        assert started.json()["code"] == "runtime_model_incompatible"
        assert transport.calls == []
