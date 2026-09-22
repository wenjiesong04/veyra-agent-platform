from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.typed_io import looks_like_artifact_ref
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.artifacts.media import (
    ArtifactIntakeError,
    inspect_artifact,
    sanitize_filename,
)
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.storage.objects import object_path, read_object

_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)
_PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def test_filename_sanitize_strips_paths() -> None:
    assert sanitize_filename("../secret.png") == "secret.png"
    assert sanitize_filename("nested/photo.png") == "photo.png"
    assert sanitize_filename("product.png") == "product.png"
    with pytest.raises(ArtifactIntakeError, match="filename"):
        sanitize_filename(".hidden.png")
    with pytest.raises(ArtifactIntakeError, match="filename"):
        sanitize_filename("bad\x00.png")


def test_sniff_rejects_extension_mismatch() -> None:
    with pytest.raises(ArtifactIntakeError, match="match"):
        inspect_artifact("report.pdf", _PNG)


def test_png_and_pdf_kinds() -> None:
    assert inspect_artifact("photo.png", _PNG) == ("image/png", "image")
    assert inspect_artifact("report.pdf", _PDF) == ("application/pdf", "pdf")
    assert inspect_artifact("notes.txt", b"hello") == ("text/plain", "document")


def _client(tmp_path: Path) -> TestClient:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'db' / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    return TestClient(create_app(settings))


def test_upload_returns_artifact_ref_without_host_path(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project = client.post("/api/v1/projects", json={"name": "Shop"}).json()
        response = client.post(
            f"/api/v1/projects/{project['project_id']}/artifacts",
            files={"file": ("product.png", _PNG, "image/png")},
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["kind"] == "artifact"
        assert payload["filename"] == "product.png"
        assert payload["media_type"] == "image/png"
        assert payload["storage_ref"].startswith("sha256/")
        blob = str(payload)
        assert str(tmp_path) not in blob
        assert "application-data" not in blob
        fetched = client.get(
            f"/api/v1/projects/{project['project_id']}/artifacts/{payload['artifact_id']}"
        )
        assert fetched.status_code == 200
        content = client.get(
            f"/api/v1/projects/{project['project_id']}/artifacts/{payload['artifact_id']}/content"
        )
        assert content.status_code == 200
        assert content.content == _PNG


def test_artifact_is_project_scoped(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        first = client.post("/api/v1/projects", json={"name": "A"}).json()
        second = client.post("/api/v1/projects", json={"name": "B"}).json()
        uploaded = client.post(
            f"/api/v1/projects/{first['project_id']}/artifacts",
            files={"file": ("product.png", _PNG, "image/png")},
        ).json()
        missing = client.get(
            f"/api/v1/projects/{second['project_id']}/artifacts/{uploaded['artifact_id']}"
        )
        assert missing.status_code == 404
        assert missing.json()["code"] == "artifact_not_found"
        stolen = client.get(
            f"/api/v1/projects/{second['project_id']}/artifacts/{uploaded['artifact_id']}/content"
        )
        assert stolen.status_code == 404


def test_missing_artifact_and_size_limit(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project = client.post("/api/v1/projects", json={"name": "Limit"}).json()
        missing = client.get(
            f"/api/v1/projects/{project['project_id']}/artifacts/art_missing"
        )
        assert missing.status_code == 404
        huge = client.post(
            f"/api/v1/projects/{project['project_id']}/artifacts",
            files={"file": ("photo.png", _PNG + b"x" * 8_000_001, "image/png")},
        )
        assert huge.status_code == 422
        assert huge.json()["code"] == "artifact_too_large"


def test_upload_rejects_type_confusion_and_dangerous_suffix(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project = client.post("/api/v1/projects", json={"name": "Types"}).json()
        prefix = f"/api/v1/projects/{project['project_id']}/artifacts"
        mismatched = client.post(
            prefix, files={"file": ("report.pdf", _PNG, "application/pdf")}
        )
        assert mismatched.status_code == 422
        assert mismatched.json()["code"] == "artifact_type_mismatch"
        html = client.post(
            prefix, files={"file": ("page.html", b"<html>", "text/html")}
        )
        assert html.status_code == 422
        assert html.json()["code"] == "artifact_filename_invalid"
        empty = client.post(prefix, files={"file": ("notes.txt", b"", "text/plain")})
        assert empty.status_code == 422
        assert empty.json()["code"] == "artifact_empty"


def test_upload_reuses_object_store_and_ref_has_no_bytes(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project = client.post("/api/v1/projects", json={"name": "Store"}).json()
        response = client.post(
            f"/api/v1/projects/{project['project_id']}/artifacts",
            files={"file": ("report.pdf", _PDF, "application/pdf")},
        )
        payload = response.json()
        assert response.status_code == 201
        assert looks_like_artifact_ref(payload)
        assert "bytes" not in payload
        assert "base64" not in payload
        digest = hashlib.sha256(_PDF).hexdigest()
        assert payload["sha256"] == digest
        stored = object_path(client.app.state.artifacts.object_root, digest)
        assert stored.read_bytes() == _PDF
        assert read_object(client.app.state.artifacts.object_root, digest) == _PDF
