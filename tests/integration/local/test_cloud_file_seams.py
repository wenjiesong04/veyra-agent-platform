from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings


def _client(tmp_path: Path) -> TestClient:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    return TestClient(create_app(settings))


def test_local_cloud_file_materialize_is_streamed_and_project_safe(
    tmp_path: Path,
) -> None:
    content = b"downloaded from the private Cloud File\n"
    digest = hashlib.sha256(content).hexdigest()
    with _client(tmp_path) as client:
        project = client.post("/api/v1/projects", json={"name": "Materialize"}).json()
        project_id = project["project_id"]
        response = client.post(
            f"/api/v1/projects/{project_id}/files/materialize",
            data={
                "relative_path": "assets/downloaded.txt",
                "expected_sha256": digest,
                "expected_size": str(len(content)),
            },
            files={"file": ("untrusted-name.txt", content, "text/plain")},
        )
        assert response.status_code == 201, response.text
        assert response.json()["relative_path"] == "assets/downloaded.txt"
        target = Path(project["root_path"]) / "assets" / "downloaded.txt"
        assert target.read_bytes() == content

        for relative_path in (
            "../escape.txt",
            "/tmp/escape.txt",
            "assets/../escape.txt",
        ):
            rejected = client.post(
                f"/api/v1/projects/{project_id}/files/materialize",
                data={"relative_path": relative_path},
                files={"file": ("file.txt", b"x", "text/plain")},
            )
            assert rejected.status_code == 422, (relative_path, rejected.text)

        outside = tmp_path / "outside"
        outside.write_text("outside", encoding="utf-8")
        (Path(project["root_path"]) / "assets" / "escape-link").symlink_to(outside)
        symlink_rejected = client.post(
            f"/api/v1/projects/{project_id}/files/materialize",
            data={"relative_path": "assets/escape-link/file.txt"},
            files={"file": ("file.txt", b"x", "text/plain")},
        )
        assert symlink_rejected.status_code == 422
        assert outside.read_text(encoding="utf-8") == "outside"


def test_knowledge_cloud_file_reference_is_metadata_only_and_portable(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        project = client.post("/api/v1/projects", json={"name": "Knowledge Ref"}).json()
        project_id = project["project_id"]
        knowledge = client.post(
            f"/api/v1/projects/{project_id}/knowledge",
            json={"name": "Cloud Source", "text": "local source remains local"},
        ).json()
        file_id = new_uuid7()
        bound = client.post(
            f"/api/v1/projects/{project_id}/knowledge/{knowledge['knowledge_id']}/source-ref",
            json={"file_id": file_id},
        )
        assert bound.status_code == 200, bound.text
        assert bound.json()["source_ref"] == {"kind": "cloud_file", "file_id": file_id}
        assert bound.json()["processing"]["index_status"] == "not_indexed"
        assert bound.json()["text"] == "local source remains local"

        manifest = client.get(
            f"/api/v1/projects/{project_id}/artifact-sync/manifest"
        ).json()
        knowledge_artifact = next(
            item
            for item in manifest["artifacts"]
            if item["artifact_kind"] == "knowledge_metadata"
        )
        artifact = client.get(
            f"/api/v1/projects/{project_id}/artifact-sync/knowledge_metadata/"
            f"{knowledge_artifact['artifact_id']}"
        )
        assert artifact.status_code == 200
        payload = artifact.json()["artifact"]["payload"]
        assert payload["source_ref"] == {"kind": "cloud_file", "file_id": file_id}
        assert "local source remains local" not in artifact.text
