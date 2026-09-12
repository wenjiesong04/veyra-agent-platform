from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings


def _settings(tmp_path: Path) -> LocalSettings:
    return LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )


def _generic_yaml() -> bytes:
    return (
        b"name: Research helper\n"
        b"description: Imports a useful research Agent\n"
        b"prompt: Summarize the requested material.\n"
        b"model:\n"
        b"  provider: openai\n"
        b"  model: gpt-5\n"
        b"  api_key: do-not-persist\n"
        b"inputs:\n"
        b"  path: string\n"
        b"outputs:\n"
        b"  result: string\n"
        b"tools:\n"
        b"  - filesystem.read\n"
        b"  - custom.python_runtime\n"
        b"workflow:\n"
        b"  - id: step-1\n"
        b"runtime: external-code\n"
    )


def test_external_import_preview_apply_and_manifest(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        project = client.post("/api/v1/projects", json={"name": "Import target"})
        assert project.status_code == 201
        project_id = project.json()["project_id"]

        analyzed = client.post(
            "/api/v1/agent-imports/file",
            files={"file": ("agent.yaml", _generic_yaml(), "application/yaml")},
        )
        assert analyzed.status_code == 201
        record = analyzed.json()
        assert record["schema_version"] == "agent.import.v1"
        assert record["ir"]["schema_version"] == "agent.import.ir.v1"
        assert record["compatibility_report"]["schema_version"] == (
            "agent.import.compatibility.v1"
        )
        assert any(
            item["status"] == "unsupported"
            for item in record["compatibility_report"]["capabilities"]
        )
        assert any(
            item["code"] == "model_credentials_ignored"
            for item in record["compatibility_report"]["warnings"]
        )

        preview = client.get(f"/api/v1/agent-imports/{record['import_id']}")
        assert preview.status_code == 200
        assert preview.json()["preview"] == record["preview"]

        rejected = client.post(
            f"/api/v1/agent-imports/{record['import_id']}/apply",
            json={"project_id": project_id, "confirm": False},
        )
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "agent_import_confirmation_required"

        applied = client.post(
            f"/api/v1/agent-imports/{record['import_id']}/apply",
            json={"project_id": project_id, "confirm": True},
        )
        assert applied.status_code == 200
        agent = applied.json()["agent"]
        assert agent["project_id"] == project_id
        assert agent["node_count"] >= 3

        root = Path(project.json()["root_path"])
        source_path = root / agent["source_path"]
        assert source_path.is_file()
        source = source_path.read_text(encoding="utf-8")
        assert "Summarize the requested material." in source
        manifest = json.loads(
            (source_path.parent / "import" / "manifest.json").read_text()
        )
        assert manifest["schema_version"] == "agent.import.manifest.v1"
        assert manifest["import_id"] == record["import_id"]

        applied_preview = client.get(f"/api/v1/agent-imports/{record['import_id']}")
        assert applied_preview.json()["state"] == "applied"


def test_folder_and_zip_sources_use_the_same_analysis_pipeline(tmp_path: Path) -> None:
    folder = tmp_path / "folder-source"
    folder.mkdir()
    (folder / "agent.yaml").write_bytes(
        b"name: Folder Agent\n"
        b"instructions:\n"
        b"  file: prompt.md\n"
        b"inputs: [request]\n"
        b"outputs: [result]\n"
    )
    (folder / "prompt.md").write_text("Read the folder prompt.", encoding="utf-8")

    with TestClient(create_app(_settings(tmp_path))) as client:
        folder_response = client.post(
            "/api/v1/agent-imports/folder", json={"path": str(folder)}
        )
        assert folder_response.status_code == 201
        folder_record = folder_response.json()
        assert folder_record["source_kind"] == "folder"
        assert folder_record["preview"]["instructions"] == "Read the folder prompt."

        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
            output.writestr("bundle/agent.yaml", _generic_yaml())
        zip_response = client.post(
            "/api/v1/agent-imports/file",
            files={"file": ("bundle.zip", archive.getvalue(), "application/zip")},
        )
        assert zip_response.status_code == 201
        assert zip_response.json()["source_kind"] == "zip"
        assert zip_response.json()["manifest"]["source_files"] == ["bundle/agent.yaml"]


def test_zip_path_traversal_is_rejected_before_yaml_analysis(tmp_path: Path) -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        output.writestr("../agent.yaml", _generic_yaml())

    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.post(
            "/api/v1/agent-imports/file",
            files={"file": ("unsafe.zip", archive.getvalue(), "application/zip")},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "agent_import_path_invalid"
