from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.canonical import file_hash
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.projects.knowledge_ingest import (
    KnowledgeIntakeError,
    parse_upload,
)
from veyra_agent_platform.local.projects.service import ProjectError


@pytest.mark.parametrize("filename", ["thesis.txt", "thesis.md"])
def test_local_file_ingest_persists_truth_and_project_ownership(
    tmp_path: Path, filename: str
) -> None:
    local_file = tmp_path / filename
    local_file.write_bytes(
        "Veyra Knowledge acceptance marker is ORBIT-731.\r\n"
        "Cafe\u0301 实验\r\n".encode()
    )
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={"name": "Research"}).json()
        url = f"/api/v1/projects/{project['project_id']}/knowledge"
        with local_file.open("rb") as stream:
            response = client.post(f"{url}/ingest", files={"file": (filename, stream)})
        assert response.status_code == 201, response.text
        document = response.json()
        state = document["processing"]
        assert document["project_id"] == project["project_id"]
        root = Path(project["root_path"])
        document_path = root / document["source_path"]
        assert document_path.parent == root / "knowledge" / document["slug"]
        manifest = yaml.safe_load((root / "project.vproject.yaml").read_text())
        assert manifest["knowledge"] == [
            {
                "kind": "knowledge",
                "resource_id": document["knowledge_id"],
                "slug": document["slug"],
                "version": document["version"],
                "path": f"knowledge/{document['slug']}",
            }
        ]
        resource = yaml.safe_load((document_path.parent / "resource.yaml").read_text())
        assert resource["resource_id"] == document["knowledge_id"]
        assert resource["slug"] == document["slug"]
        assert document_path.read_bytes() == local_file.read_bytes()
        origin = yaml.safe_load((document_path.parent / "source.json").read_text())
        assert origin == {
            "kind": "upload",
            "filename": filename,
            "media_type": "text/plain"
            if filename.endswith(".txt")
            else "text/markdown",
            "uploaded_content_hash": hashlib.sha256(
                local_file.read_bytes()
            ).hexdigest(),
        }
        assert state["origin"] == origin["kind"]
        assert state["media_type"] == origin["media_type"]
        assert state["filename"] == filename
        assert state["ingest_status"] == "ingested"
        assert state["parse_status"] == "parsed"
        assert state["index_status"] == "not_indexed"
        assert state["failure_reason"] is None
        assert state["updated_at"]
        assert (
            state["uploaded_content_hash"]
            == hashlib.sha256(local_file.read_bytes()).hexdigest()
        )
        assert (
            state["content_hash"]
            == hashlib.sha256(document_path.read_bytes()).hexdigest()
        )
        assert document["source_file_hash"] == file_hash(document["text"])
        assert document["source_file_hash"] != state["content_hash"]
        assert "ORBIT-731" in document["text"]
        assert client.get(f"{url}/{document['knowledge_id']}").json() == document
        assert client.get(url).json()["knowledge"][0]["processing"] == state
        other = client.post("/api/v1/projects", json={"name": "Other"}).json()
        assert (
            client.get(
                f"/api/v1/projects/{other['project_id']}/knowledge/{document['knowledge_id']}"
            ).status_code
            == 422
        )
    with TestClient(create_app(settings)) as client:
        detail_url = f"{url}/{document['knowledge_id']}"
        assert client.get(detail_url).json() == document
        assert client.get(url).json()["knowledge"][0]["processing"] == state
        changed = client.patch(detail_url, json={"text": "Updated thesis"}).json()
        assert changed["processing"]["content_hash"] != state["content_hash"]
        assert (
            changed["processing"]["uploaded_content_hash"]
            == state["uploaded_content_hash"]
        )
        assert changed["processing"]["index_status"] == "not_indexed"


@pytest.mark.parametrize(
    ("filename", "contents", "code"),
    [
        ("thesis.pdf", b"%PDF", "knowledge_type_unsupported"),
        ("../thesis.txt", b"text", "knowledge_filename_invalid"),
        (".env", b"not a credential", "knowledge_filename_invalid"),
        ("credentials.txt", b"synthetic", "knowledge_filename_invalid"),
        ("id_rsa.md", b"synthetic", "knowledge_filename_invalid"),
        ("private.key.txt", b"synthetic", "knowledge_filename_invalid"),
        ("thesis.txt", b"\xff", "knowledge_parse_failed"),
        ("thesis.txt", b"\x00binary", "knowledge_parse_failed"),
        ("thesis.txt", b"a" * 1_000_001, "knowledge_upload_too_large"),
    ],
)
def test_failed_intake_is_typed_and_does_not_install_a_source(
    tmp_path: Path, filename: str, contents: bytes, code: str
) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={"name": "Research"}).json()
        url = f"/api/v1/projects/{project['project_id']}/knowledge"
        manifest_path = Path(project["root_path"]) / "project.vproject.yaml"
        original_manifest = manifest_path.read_bytes()
        response = client.post(f"{url}/ingest", files={"file": (filename, contents)})
        assert response.status_code == 422, response.text
        assert response.json()["code"] == code
        assert client.get(url).json()["knowledge"] == []
        assert manifest_path.read_bytes() == original_manifest
        assert list((Path(project["root_path"]) / "knowledge").iterdir()) == []


def test_empty_upload_is_not_replaced_with_demo_text(tmp_path: Path) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={"name": "Empty"}).json()
        response = client.post(
            f"/api/v1/projects/{project['project_id']}/knowledge/ingest",
            files={"file": ("empty.txt", b"")},
        )
        assert response.status_code == 201, response.text
        assert response.json()["text"] == ""
        assert response.json()["processing"]["index_status"] == "not_indexed"


def test_intake_rejects_windows_paths_before_storage() -> None:
    # Multipart normalizes legacy browser paths; the service also rejects raw paths.
    with pytest.raises(KnowledgeIntakeError) as error:
        parse_upload("C:\\thesis.txt", b"text")
    assert error.value.code == "knowledge_filename_invalid"


@pytest.mark.parametrize("failed_file", ["source.json", "project.vproject.yaml"])
def test_ingest_write_failure_rolls_back_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed_file: str
) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        project = client.post("/api/v1/projects", json={"name": "Rollback"}).json()
        root = Path(project["root_path"])
        manifest_path = root / "project.vproject.yaml"
        original_manifest = manifest_path.read_bytes()
        atomic_write = app.state.projects.atomic_write
        failed = False

        def fail_after_replace(path: Path, contents: str) -> None:
            nonlocal failed
            atomic_write(path, contents)
            if path.name == failed_file and not failed:
                failed = True
                raise ProjectError("Injected post-replace write failure")

        monkeypatch.setattr(app.state.projects, "atomic_write", fail_after_replace)
        url = f"/api/v1/projects/{project['project_id']}/knowledge"
        response = client.post(
            f"{url}/ingest", files={"file": ("thesis.txt", b"ORBIT-731")}
        )
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "project_invalid"
        assert manifest_path.read_bytes() == original_manifest
        assert list((root / "knowledge").iterdir()) == []
        assert client.get(url).json()["knowledge"] == []


def test_ingest_uses_existing_slug_allocation_and_rejects_symlinks(
    tmp_path: Path,
) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={"name": "Paths"}).json()
        url = f"/api/v1/projects/{project['project_id']}/knowledge"
        root = Path(project["root_path"])
        first = client.post(
            f"{url}/ingest", files={"file": ("thesis.txt", b"First")}
        ).json()
        second = client.post(
            f"{url}/ingest", files={"file": ("thesis.txt", b"Second")}
        ).json()
        assert first["knowledge_id"] != second["knowledge_id"]
        assert first["slug"] == "new-knowledge"
        assert second["slug"] == "new-knowledge-1"
        assert client.get(f"{url}/{first['knowledge_id']}").json() == first
        original_manifest = (root / "project.vproject.yaml").read_bytes()
        outside = tmp_path / "outside"
        outside.mkdir()
        (root / "knowledge" / "new-knowledge-2").symlink_to(outside)
        response = client.post(
            f"{url}/ingest", files={"file": ("thesis.txt", b"Rejected")}
        )
        assert response.status_code == 422
        assert response.json()["code"] == "project_invalid"
        assert list(outside.iterdir()) == []
        assert (root / "project.vproject.yaml").read_bytes() == original_manifest
        origin = root / first["source_path"]
        (origin.parent / "source.json").rename(outside / "source.json")
        (origin.parent / "source.json").symlink_to(outside / "source.json")
        response = client.get(f"{url}/{first['knowledge_id']}")
        assert response.status_code == 422
        assert response.json()["code"] == "project_invalid"
