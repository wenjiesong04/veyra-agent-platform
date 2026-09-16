import json
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.canonical import file_hash
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings

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


def bind(client, url, documents):
    draft = client.get(f"{url}/draft").json()
    refs = [f"{doc['knowledge_id']}@{doc['version']}" for doc in documents]
    draft["source"]["extensions"]["veyra"]["knowledge_refs"] = refs
    for ref, doc in zip(refs, documents, strict=True):
        draft["source"]["lock"][ref] = doc["source_file_hash"]
    response = client.patch(
        f"{url}/draft",
        json={"source": draft["source"], "expected_revision": draft["revision"]},
        headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(
    ("filename", "fact", "query"),
    [
        (
            "fact.txt",
            "The acceptance marker is ORBIT-731.",
            "What is the acceptance marker?",
        ),
        ("fact.md", "毕业设计题目是人工智能影视分镜生成系统", "毕业设计题目是什么"),
    ],
)
def test_runtime_bound_only_top_chunks_and_empty(tmp_path, filename, fact, query):
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    transport = ScriptedRuntimeTransport("Answer from retrieved context")
    app = create_app(settings, runtime_transport=transport)
    with TestClient(app) as client:
        project = client.post(
            "/api/v1/projects", json={"agents": [_agent_source()]}
        ).json()
        p, a = project["project_id"], project["agents"][0]["agent_id"]
        url = f"/api/v1/projects/{p}/agents/{a}"
        knowledge_url = f"/api/v1/projects/{p}/knowledge"
        documents = []
        for text in (fact + "\n\nUNRELATED_WEATHER\n" * 3000, fact):
            response = client.post(
                f"{knowledge_url}/ingest", files={"file": (filename, text.encode())}
            )
            assert response.status_code == 201, response.text
            doc = response.json()
            assert (
                client.post(f"{knowledge_url}/{doc['knowledge_id']}/index").status_code
                == 200
            )
            documents.append(doc)
        # Even a matching, indexed document in the same Project is out of scope.
        unbound = client.post(
            knowledge_url, json={"text": fact + " UNBOUND_SENTINEL"}
        ).json()
        assert (
            client.post(f"{knowledge_url}/{unbound['knowledge_id']}/index").status_code
            == 200
        )
        saved = bind(client, url, documents)
        result = _run_until_settled(client, f"{url}/run", {"request": query})
        assert result["status"] == "unverified", result
        messages = json.dumps(transport.calls, ensure_ascii=False)
        assert fact in messages
        assert "UNRELATED_WEATHER" not in messages
        assert "UNBOUND_SENTINEL" not in messages
        context = transport.calls[-1][-1]["content"].split("Project knowledge", 1)[1]
        assert context.count("Document ") == 2
        assert len(context.encode()) < 65_536
        snapshot = dict(app.state.repository.version(result["version_id"]))
        assert json.loads(snapshot["source_json"])["lock"] == saved["source"]["lock"]
        evidence = next(
            event["payload"]
            for event in result["events"]
            if event["kind"] == "tool.completed"
            and event["payload"].get("tool_reference") == "knowledge.context"
        )
        assert evidence["hit_count"] == 2
        assert evidence["query_hash"] == file_hash(
            json.dumps([query], ensure_ascii=False, sort_keys=True)
        )
        assert [hit["rank"] for hit in evidence["receipts"]] == [1, 2]
        assert [hit["reference"] for hit in evidence["receipts"]] == sorted(
            f"{doc['knowledge_id']}@{doc['version']}" for doc in documents
        )
        for hit in evidence["receipts"]:
            owner = next(
                doc
                for doc in documents
                if hit["reference"].startswith(doc["knowledge_id"])
            )
            index_path = Path(project["root_path"]) / owner["source_path"]
            chunk = json.loads((index_path.parent / "index.json").read_text())[
                "chunks"
            ][0]
            assert hit["chunk_id"] == chunk["chunk_id"]
            assert hit["source_file_hash"] == owner["source_file_hash"]
            assert hit["line_start"] == hit["line_end"] == 1
            assert hit["score"] > 0
            assert hit["chunk_index"] == 0
        assert query not in json.dumps(evidence, ensure_ascii=False)
        assert fact not in json.dumps(evidence, ensure_ascii=False)
        for empty_query in ("xyzzy", ""):
            empty = _run_until_settled(client, f"{url}/run", {"request": empty_query})
            assert empty["status"] == "unverified", empty
            message = transport.calls[-1][-1]["content"]
            assert "No relevant Knowledge chunks retrieved." in message
            assert fact not in message
            empty_evidence = next(
                event["payload"]
                for event in empty["events"]
                if event["kind"] == "tool.completed"
            )
            assert empty_evidence["hit_count"] == 0
            assert empty_evidence["receipts"] == []
        # Query evidence is hash-only, even if an input resembles a credential.
        sensitive = "synthetic-private-input-DO-NOT-PERSIST"
        private_run = _run_until_settled(client, f"{url}/run", {"request": sensitive})
        private_evidence = next(
            event["payload"]
            for event in private_run["events"]
            if event["kind"] == "tool.completed"
        )
        assert sensitive not in json.dumps(private_evidence)
        assert set(private_evidence) == {
            "tool_reference",
            "receipts",
            "query_hash",
            "hit_count",
        }
    with TestClient(create_app(settings, runtime_transport=transport)) as client:
        call_count = len(transport.calls)
        reloaded = client.get(f"{url}/runs/{result['run_id']}").json()
        assert reloaded["events"] == result["events"]
        assert len(transport.calls) == call_count


@pytest.mark.parametrize(
    ("state", "code"),
    [
        ("not_indexed", "knowledge_not_indexed"),
        ("stale", "knowledge_index_stale"),
        ("corrupt", "knowledge_index_invalid"),
        ("old_pin", "knowledge_lock_mismatch"),
        ("missing", "project_invalid"),
    ],
)
def test_resolution_fails_before_model_without_fallback(tmp_path, state, code):
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    transport = ScriptedRuntimeTransport("must not run")
    app = create_app(settings, runtime_transport=transport)
    with TestClient(app) as client:
        project = client.post(
            "/api/v1/projects", json={"agents": [_agent_source()]}
        ).json()
        p, a = project["project_id"], project["agents"][0]["agent_id"]
        url = f"/api/v1/projects/{p}/agents/{a}"
        knowledge_url = f"/api/v1/projects/{p}/knowledge"
        doc = client.post(
            knowledge_url, json={"text": "The acceptance marker is ORBIT-731."}
        ).json()
        detail = f"{knowledge_url}/{doc['knowledge_id']}"
        document = Path(project["root_path"]) / doc["source_path"]
        artifact = document.parent / "index.json"
        if state != "not_indexed":
            assert client.post(f"{detail}/index").status_code == 200
        if state == "stale":
            doc = client.patch(
                detail, json={"text": "The acceptance marker is CHANGED."}
            ).json()
        saved = bind(client, url, [doc])
        if state == "old_pin":
            client.patch(detail, json={"text": "The acceptance marker is CHANGED."})
            assert client.post(f"{detail}/index").status_code == 200
        elif state == "corrupt":
            artifact.write_text("{}")
        elif state == "missing":
            document.unlink()
        before = artifact.read_bytes() if artifact.exists() else None
        result = _run_until_settled(
            client, f"{url}/run", {"request": "acceptance marker"}
        )
        assert result["status"] == "failed", result
        assert result["error"]["code"] == code
        assert transport.calls == []
        assert not any(event["kind"] == "tool.completed" for event in result["events"])
        assert (artifact.read_bytes() if artifact.exists() else None) == before
        snapshot = app.state.repository.version(result["version_id"])
        assert json.loads(snapshot["source_json"])["lock"] == saved["source"]["lock"]
