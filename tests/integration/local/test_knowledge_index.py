import json
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.projects.service import (
    MAX_INDEXED_FILE_BYTES,
    MAX_INDEXED_TOTAL_BYTES,
    ProjectError,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(socket.socket, "connect", denied)


def test_explicit_index_lifecycle_and_reload(tmp_path: Path):
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={}).json()
        url = f"/api/v1/projects/{project['project_id']}/knowledge"
        doc = client.post(
            f"{url}/ingest", files={"file": ("fact.md", b"ORBIT-731\n\nweather")}
        ).json()
        detail = f"{url}/{doc['knowledge_id']}"
        assert doc["processing"]["index_status"] == "not_indexed"
        artifact = Path(project["root_path"]) / doc["source_path"]
        artifact = artifact.parent / "index.json"
        assert not artifact.exists()
        response = client.post(f"{detail}/index")
        assert response.status_code == 200, response.text
        built = response.json()
        assert built["processing"]["index_status"] == "indexed"
        assert built["processing"]["chunk_count"] == 2
        saved = json.loads(artifact.read_text())
        assert saved["source_file_hash"] == doc["source_file_hash"]
        assert saved["schema_version"] == 1
        assert saved["built_at"]
        assert client.post(f"{detail}/index").status_code == 200
        assert json.loads(artifact.read_text())["chunks"] == saved["chunks"]
        other = client.post("/api/v1/projects", json={}).json()
        wrong = (
            f"/api/v1/projects/{other['project_id']}/knowledge/"
            f"{doc['knowledge_id']}/index"
        )
        before = artifact.read_bytes()
        assert client.post(wrong).status_code == 422
        assert artifact.read_bytes() == before
    with TestClient(create_app(settings)) as client:
        assert client.get(detail).json()["processing"]["index_status"] == "indexed"
        changed = client.patch(
            detail, json={"text": "毕业设计题目是人工智能影视分镜生成系统"}
        ).json()
        assert changed["processing"]["index_status"] == "stale"
        assert (
            client.get(url).json()["knowledge"][0]["processing"]["index_status"]
            == "stale"
        )
        assert artifact.read_bytes() == before
        rebuilt = client.post(f"{detail}/index").json()
        assert rebuilt["processing"]["index_status"] == "indexed"
        assert (
            json.loads(artifact.read_text())["source_file_hash"]
            == changed["source_file_hash"]
        )
        assert json.loads(artifact.read_text())["chunks"] != saved["chunks"]
        artifact.write_text('{"schema_version": 1}')
        failed = client.get(detail).json()["processing"]
        assert failed["index_status"] == "failed"
        assert failed["chunk_count"] is None
        assert failed["failure_reason"] == (
            "Knowledge index is invalid; explicitly rebuild the index."
        )
        assert client.post(f"{detail}/index").status_code == 200
        artifact.unlink()
        assert client.get(detail).json()["processing"]["index_status"] == "not_indexed"


def test_index_safe_path_and_bounded_build(tmp_path: Path):
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={}).json()
        url = f"/api/v1/projects/{project['project_id']}/knowledge"
        doc = client.post(url, json={"text": "fact"}).json()
        detail = f"{url}/{doc['knowledge_id']}"
        document = Path(project["root_path"]) / doc["source_path"]
        artifact = document.parent / "index.json"
        outside = tmp_path / "outside.json"
        outside.write_text("untouched")
        artifact.symlink_to(outside)
        assert client.get(detail).json()["processing"]["index_status"] == "failed"
        assert client.post(f"{detail}/index").status_code == 422
        assert outside.read_text() == "untouched"
        artifact.unlink()
        document.write_text("x" * 1_000_001)
        response = client.post(f"{detail}/index")
        assert response.status_code == 422
        assert response.json()["code"] == "knowledge_index_too_large"
        assert not artifact.exists()


def test_derived_index_exemption_preserves_file_and_project_limits(tmp_path: Path):
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        project = client.post("/api/v1/projects", json={}).json()
        project_id = project["project_id"]
        root = Path(project["root_path"])
        url = f"/api/v1/projects/{project_id}/knowledge"
        doc = client.post(url, json={"text": "marker\n\n" * 3000}).json()
        detail = f"{url}/{doc['knowledge_id']}"
        response = client.post(f"{detail}/index")
        assert response.status_code == 200, response.text
        artifact = (root / doc["source_path"]).parent / "index.json"
        assert (
            MAX_INDEXED_FILE_BYTES < artifact.stat().st_size < MAX_INDEXED_TOTAL_BYTES
        )
        app.state.projects.list_files(project_id)
        for ordinary in (
            root / "assets" / "index.json",
            root / "knowledge" / "unregistered" / "index.json",
            artifact.parent / "notes.md",
        ):
            ordinary.parent.mkdir(parents=True, exist_ok=True)
            ordinary.write_bytes(b"x" * (MAX_INDEXED_FILE_BYTES + 1))
            with pytest.raises(ProjectError, match="Project file exceeds"):
                app.state.projects.list_files(project_id)
            ordinary.unlink()
        for number in range(9):
            (root / "assets" / f"part-{number}.txt").write_bytes(
                b"x" * MAX_INDEXED_FILE_BYTES
            )
        with pytest.raises(ProjectError, match="Project exceeds the indexing total"):
            app.state.projects.list_files(project_id)


def test_build_io_failure_is_typed_and_does_not_expose_internal_path(
    tmp_path: Path, monkeypatch
):
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        project = client.post("/api/v1/projects", json={}).json()
        url = f"/api/v1/projects/{project['project_id']}/knowledge"
        doc = client.post(url, json={"text": "marker"}).json()
        detail = f"{url}/{doc['knowledge_id']}"

        def fail_write(*args, **kwargs):
            raise OSError(f"internal write failure: {tmp_path}/private/index.json")

        monkeypatch.setattr(app.state.projects, "atomic_write", fail_write)
        response = client.post(f"{detail}/index")
        assert response.status_code == 422
        assert response.json()["code"] == "knowledge_index_build_failed"
        assert response.json()["message"] == (
            "Knowledge index build failed; explicitly retry the build."
        )
        assert str(tmp_path) not in response.text
        assert "internal write failure" not in response.text
        assert client.get(detail).json()["processing"]["index_status"] == "not_indexed"
