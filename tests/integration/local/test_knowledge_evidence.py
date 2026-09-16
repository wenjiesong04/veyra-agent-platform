import json
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.canonical import file_hash
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings

from .test_knowledge_retrieval import bind
from .test_runtime_routes import (
    ScriptedRuntimeTransport,
    _agent_source,
    _run_until_settled,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(socket.socket, "connect", denied)


def retrieval(run):
    return next(
        event["payload"]
        for event in run["events"]
        if event["kind"] == "tool.completed"
        and event["payload"].get("tool_reference") == "knowledge.context"
    )


def test_historical_run_evidence_and_explicit_excerpt_survive_reload(tmp_path):
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    transport = ScriptedRuntimeTransport("Answer")
    with TestClient(create_app(settings, runtime_transport=transport)) as client:
        project = client.post(
            "/api/v1/projects", json={"agents": [_agent_source()]}
        ).json()
        p, a = project["project_id"], project["agents"][0]["agent_id"]
        url = f"/api/v1/projects/{p}/agents/{a}"
        knowledge = f"/api/v1/projects/{p}/knowledge"
        doc = client.post(
            f"{knowledge}/ingest",
            files={
                "file": (
                    "evidence.md",
                    b"marker ORBIT-731\nsecond line\n\nmarker original second chunk",
                )
            },
        ).json()
        detail = f"{knowledge}/{doc['knowledge_id']}"
        assert client.post(f"{detail}/index").status_code == 200
        bind(client, url, [doc])
        run = _run_until_settled(client, f"{url}/run", {"request": "marker"})
        assert run["status"] == "unverified", run
        evidence = retrieval(run)
        assert evidence["hit_count"] == 2
        assert evidence["query_hash"] == file_hash(json.dumps(["marker"]))
        assert [hit["rank"] for hit in evidence["receipts"]] == [1, 2]
        assert [
            (hit["line_start"], hit["line_end"]) for hit in evidence["receipts"]
        ] == [(1, 2), (4, 4)]
        assert all(
            hit["source_file_hash"] == doc["source_file_hash"]
            for hit in evidence["receipts"]
        )
        assert "ORBIT-731" not in json.dumps(run)
        assert "second line" not in json.dumps(run)
        assert "query" not in evidence
        hit = evidence["receipts"][0]
        excerpt_url = f"{detail}/chunks/{hit['chunk_id']}"
        params = {"source_file_hash": hit["source_file_hash"]}
        preview = client.get(excerpt_url, params=params)
        assert preview.status_code == 200, preview.text
        assert preview.json() == {
            "schema_version": "1.0",
            "project_id": p,
            "reference": hit["reference"],
            "source_file_hash": hit["source_file_hash"],
            "chunk_id": hit["chunk_id"],
            "line_start": 1,
            "line_end": 2,
            "text": "marker ORBIT-731\nsecond line",
        }
        empty = _run_until_settled(
            client, f"{url}/run", {"request": "xyzzy-private-query"}
        )
        assert retrieval(empty)["hit_count"] == 0
        assert retrieval(empty)["receipts"] == []
        assert "xyzzy-private-query" not in json.dumps(retrieval(empty))
    calls = len(transport.calls)
    with TestClient(create_app(settings, runtime_transport=transport)) as client:
        assert client.get(f"{url}/runs/{run['run_id']}").json() == run
        assert client.get(f"{url}/runs/{empty['run_id']}").json() == empty
        assert (
            client.patch(detail, json={"text": "marker NEW SOURCE"}).status_code == 200
        )
        for rebuild in (False, True):
            if rebuild:
                assert client.post(f"{detail}/index").status_code == 200
            response = client.get(excerpt_url, params=params)
            assert response.status_code == 422
            assert response.json()["code"] == "knowledge_source_mismatch"
            assert "NEW SOURCE" not in response.text
            assert client.get(f"{url}/runs/{run['run_id']}").json() == run
        document = Path(project["root_path"]) / doc["source_path"]
        document.unlink()
        assert (
            client.get(excerpt_url, params=params).json()["code"]
            == "knowledge_source_missing"
        )
        assert client.get(f"{url}/runs/{run['run_id']}").json() == run
        assert len(transport.calls) == calls
    with TestClient(create_app(settings, runtime_transport=transport)) as client:
        assert client.get(f"{url}/runs/{run['run_id']}").json() == run
        assert client.get(f"{url}/runs/{empty['run_id']}").json() == empty
        assert len(transport.calls) == calls


@pytest.mark.parametrize(
    "state,code",
    [
        ("matching", None),
        ("stale", "knowledge_source_mismatch"),
        ("missing", "knowledge_source_missing"),
        ("cross_project", "knowledge_source_missing"),
        ("not_indexed", "knowledge_not_indexed"),
        ("malformed", "knowledge_index_invalid"),
        ("index_stale", "knowledge_index_stale"),
        ("unknown_chunk", "knowledge_chunk_missing"),
        ("source_symlink", "knowledge_source_missing"),
        ("index_symlink", "knowledge_index_invalid"),
        ("oversize", "knowledge_index_too_large"),
        ("io_failure", "knowledge_source_invalid"),
    ],
)
def test_excerpt_is_project_scoped_safe_bounded_and_hash_gated(
    tmp_path, monkeypatch, state, code
):
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={}).json()
        p = project["project_id"]
        url = f"/api/v1/projects/{p}/knowledge"
        doc = client.post(url, json={"text": "中" * 5000}).json()
        detail = f"{url}/{doc['knowledge_id']}"
        assert client.post(f"{detail}/index").status_code == 200
        document = Path(project["root_path"]) / doc["source_path"]
        artifact = document.parent / "index.json"
        saved = json.loads(artifact.read_text())
        chunk = saved["chunks"][0]
        params = {"source_file_hash": doc["source_file_hash"]}
        chunk_id = chunk["chunk_id"]
        if state == "stale":
            params["source_file_hash"] = "0" * 64
        elif state == "missing":
            document.unlink()
        elif state == "cross_project":
            other = client.post("/api/v1/projects", json={}).json()
            detail = (
                f"/api/v1/projects/{other['project_id']}/knowledge/"
                f"{doc['knowledge_id']}"
            )
        elif state == "not_indexed":
            artifact.unlink()
        elif state == "malformed":
            artifact.write_text("{}")
        elif state == "index_stale":
            document.write_text("new text")
            params["source_file_hash"] = file_hash("new text")
        elif state == "unknown_chunk":
            chunk_id = "0" * 64
        elif state in {"source_symlink", "index_symlink"}:
            target = document if state == "source_symlink" else artifact
            outside = tmp_path / "private.txt"
            outside.write_text("PRIVATE_SENTINEL")
            target.unlink()
            target.symlink_to(outside)
        elif state == "oversize":
            document.write_bytes(b"x" * 1_000_001)
        elif state == "io_failure":
            original_open = Path.open

            def denied(path, *args, **kwargs):
                if path == document:
                    raise PermissionError(f"{tmp_path}/PRIVATE_SENTINEL")
                return original_open(path, *args, **kwargs)

            monkeypatch.setattr(Path, "open", denied)
        before = artifact.read_bytes() if artifact.exists() else None
        response = client.get(f"{detail}/chunks/{chunk_id}", params=params)
        if code:
            assert response.status_code == 422, response.text
            assert response.json()["code"] == code
        else:
            assert response.status_code == 200, response.text
            assert response.json()["text"] == chunk["text"]
            assert len(response.json()["text"]) == 2000
            assert len(response.json()["text"].encode()) <= 8000
        assert str(tmp_path) not in response.text
        assert "PRIVATE_SENTINEL" not in response.text
        assert (artifact.read_bytes() if artifact.exists() else None) == before
        assert client.get(f"{detail}/chunks/{chunk_id}").status_code == 422
        assert (
            client.get(
                f"{detail}/chunks/{chunk_id}",
                params={"source_file_hash": "/etc/passwd"},
            ).status_code
            == 422
        )
        for unsafe in ("%2Fetc%2Fpasswd", "%2E%2E%2Fdocument.md"):
            response = client.get(f"{detail}/chunks/{unsafe}", params=params)
            assert response.status_code != 200
            assert "PRIVATE_SENTINEL" not in response.text
