from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings

ROOT = Path(__file__).resolve().parents[3]


def test_project_routes_create_open_list_and_get_empty_project(tmp_path: Path) -> None:
    managed_root = tmp_path / "application-data" / "projects"
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=managed_root,
    )
    parent = tmp_path / "Downloads"
    parent.mkdir()
    preserved = parent / "existing-download.txt"
    preserved.write_text("keep", encoding="utf-8")
    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/api/v1/projects",
            json={"name": "Empty"},
        )
        assert created.status_code == 201
        project = created.json()
        assert project["manifest_hash"]
        assert project["agents"] == []
        assert project["agent_count"] == 0
        assert project["indexed_at"]
        root = Path(project["root_path"])
        assert root.is_relative_to(managed_root)
        assert preserved.read_text(encoding="utf-8") == "keep"

        duplicate = client.post(
            "/api/v1/projects",
            json={"name": "Empty"},
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["root_path"] != project["root_path"]

        rejected_parent = client.post(
            "/api/v1/projects",
            json={"name": "No parent", "parent_path": str(parent)},
        )
        assert rejected_parent.status_code == 422
        rejected_root = client.post(
            "/api/v1/projects",
            json={"name": "No root", "root_path": str(parent)},
        )
        assert rejected_root.status_code == 422

        reopened = client.post("/api/v1/projects/open", json={"root_path": str(root)})
        assert reopened.status_code == 200
        assert reopened.json()["project_id"] == project["project_id"]
        listed = client.get("/api/v1/projects")
        assert listed.status_code == 200
        assert {item["project_id"] for item in listed.json()["projects"]} == {
            project["project_id"],
            duplicate.json()["project_id"],
        }
        fetched = client.get(f"/api/v1/projects/{project['project_id']}")
        assert fetched.status_code == 200
        assert fetched.json() == reopened.json()


def test_project_metadata_description_pinning_and_closed_patch_body(
    tmp_path: Path,
) -> None:
    managed_root = tmp_path / "application-data" / "projects"
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=managed_root,
    )
    with TestClient(create_app(settings)) as client:
        first = client.post(
            "/api/v1/projects",
            json={
                "name": "First",
                "description": "  Cafe\u0301 Project  ",
            },
        )
        assert first.status_code == 201
        first_project = first.json()
        assert first_project["description"] == "Café Project"
        assert first_project["pinned"] is False
        assert first_project["pinned_at"] is None
        first_root = Path(first_project["root_path"])
        manifest = json.loads((first_root / "project.vproject.yaml").read_text())
        assert manifest["description"] == "Café Project"

        second = client.post(
            "/api/v1/projects",
            json={"name": "Second"},
        )
        assert second.status_code == 201
        pinned = client.patch(
            f"/api/v1/projects/{first_project['project_id']}", json={"pinned": True}
        )
        assert pinned.status_code == 200
        assert pinned.json()["pinned"] is True
        assert pinned.json()["pinned_at"]
        listed = client.get("/api/v1/projects").json()["projects"]
        assert [item["project_id"] for item in listed] == [
            first_project["project_id"],
            second.json()["project_id"],
        ]
        unpinned = client.patch(
            f"/api/v1/projects/{first_project['project_id']}", json={"pinned": False}
        )
        assert unpinned.status_code == 200
        assert unpinned.json()["pinned_at"] is None
        invalid = client.patch(
            f"/api/v1/projects/{first_project['project_id']}",
            json={"pinned": True, "other": True},
        )
        assert invalid.status_code == 422
        repinned = client.patch(
            f"/api/v1/projects/{first_project['project_id']}", json={"pinned": True}
        )
        assert repinned.status_code == 200
        assert "pinned_at" not in json.loads(
            (first_root / "project.vproject.yaml").read_text()
        )

    with TestClient(create_app(settings)) as restarted_client:
        restarted = restarted_client.get(
            f"/api/v1/projects/{first_project['project_id']}"
        )
    assert restarted.status_code == 200
    assert restarted.json()["pinned"] is True
    assert restarted.json()["pinned_at"] == repinned.json()["pinned_at"]


def test_project_agent_creation_templates_and_import(tmp_path: Path) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "application-data" / "projects",
    )
    fixture = (
        ROOT
        / "contracts"
        / "fixtures"
        / "project"
        / "agents"
        / "github-triage"
        / "agent.vagent.yaml"
    )
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={}).json()
        project_id = project["project_id"]

        templates = client.get(f"/api/v1/projects/{project_id}/agent-templates")
        assert templates.status_code == 200
        listed = templates.json()["templates"]
        by_id = {item["template_id"]: item for item in listed}
        assert listed[0] == {
            "template_id": "veyra.starter-agent@1.0.0",
            "name": "Starter Agent",
            "description": "A safe local-first starting point for a new Agent.",
            "default_slug": "starter-agent",
        }
        assert by_id["veyra.document-distiller@1.0.0"]["name"] == "文档提炼"
        assert by_id["veyra.question-researcher@1.0.0"]["name"] == "问题研究"
        assert by_id["veyra.file-sort-planner@1.0.0"]["name"] == "文件整理"
        template = listed[0]

        blank = client.post(
            f"/api/v1/projects/{project_id}/agents",
            json={"mode": "blank", "name": "  ", "description": "  "},
        )
        suffix = client.post(
            f"/api/v1/projects/{project_id}/agents", json={"mode": "blank"}
        )
        created_template = client.post(
            f"/api/v1/projects/{project_id}/agents",
            json={"mode": "template", "template_id": template["template_id"]},
        )
        assert (
            blank.status_code
            == suffix.status_code
            == created_template.status_code
            == 201
        )
        assert (blank.json()["name"], blank.json()["slug"]) == (
            "New Agent",
            "new-agent",
        )
        assert blank.json()["project_id"] == project_id
        assert (suffix.json()["name"], suffix.json()["slug"]) == (
            "New Agent(1)",
            "new-agent-1",
        )
        assert (created_template.json()["name"], created_template.json()["slug"]) == (
            "Starter Agent",
            "starter-agent",
        )

        imported = client.post(
            f"/api/v1/projects/{project_id}/agents/import",
            files={
                "file": (
                    "github-triage.yml",
                    fixture.read_bytes(),
                    "application/yaml",
                )
            },
        )
        assert imported.status_code == 201
        assert (imported.json()["name"], imported.json()["slug"]) == (
            "GitHub Triage",
            "github-triage",
        )
        agent_root = Path(project["root_path"]) / imported.json()["source_path"]
        assert (agent_root.parent / "README.md").is_file()
        assert (agent_root.parent / "tests").is_dir()

        oversized = client.post(
            f"/api/v1/projects/{project_id}/agents/import",
            files={
                "file": (
                    "too-large.vagent.yaml",
                    b"#" * 1_000_001,
                    "application/yaml",
                )
            },
        )
        assert oversized.status_code == 422
        assert oversized.json()["code"] == "project_invalid"


def test_agent_pin_and_recoverable_delete_keep_sidebar_state_and_history(
    tmp_path: Path,
) -> None:
    source = json.loads(
        (
            ROOT / "contracts/fixtures/project/agents/github-triage/agent.vagent.yaml"
        ).read_text()
    )
    managed_root = tmp_path / "application-data" / "projects"
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=managed_root,
    )
    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/api/v1/projects", json={"name": "Agent lifecycle", "agents": [source]}
        )
        assert created.status_code == 201
        project = created.json()
        project_id = project["project_id"]
        first_agent = project["agents"][0]
        second = client.post(
            f"/api/v1/projects/{project_id}/agents",
            json={"mode": "blank", "name": "Review helper"},
        )
        assert second.status_code == 201
        second_agent = second.json()
        second_base = f"/api/v1/projects/{project_id}/agents/{second_agent['agent_id']}"

        pinned = client.patch(second_base, json={"pinned": True})
        assert pinned.status_code == 200
        assert pinned.json()["default_agent_id"] == second_agent["agent_id"]
        assert pinned.json()["agents"][0]["agent_id"] == second_agent["agent_id"]
        assert pinned.json()["agents"][0]["pinned"] is True
        assert pinned.json()["agents"][1]["pinned"] is False

        draft = client.get(second_base + "/draft")
        assert draft.status_code == 200
        committed = client.post(
            second_base + "/commit",
            json={"expected_revision": draft.json()["revision"]},
            headers={"If-Match": draft.headers["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert committed.status_code == 200

        removed = client.delete(second_base)
        assert removed.status_code == 200
        payload = removed.json()
        assert payload["disposition"] == "trashed"
        assert payload["project"]["agent_count"] == 1
        assert [agent["agent_id"] for agent in payload["project"]["agents"]] == [
            first_agent["agent_id"]
        ]
        assert not (Path(project["root_path"]) / second_agent["source_path"]).exists()
        trash_path = (
            managed_root.parent
            / "trash"
            / "agents"
            / project_id
            / second_agent["agent_id"]
        )
        assert trash_path.is_dir()
        assert client.get(second_base + "/draft").status_code == 422
        assert (
            client.get(f"/api/v1/projects/{project_id}").json()["agents"]
            == payload["project"]["agents"]
        )

        with client.app.state.repository._connect() as connection:
            history = connection.execute(
                "SELECT COUNT(*) FROM agent_versions WHERE agent_id = ?",
                (second_agent["agent_id"],),
            ).fetchone()[0]
        assert history == 1

    with TestClient(create_app(settings)) as restarted_client:
        restarted = restarted_client.get(f"/api/v1/projects/{project_id}")
        assert restarted.status_code == 200
        assert restarted.json()["agent_count"] == 1
        assert restarted.json()["default_agent_id"] == first_agent["agent_id"]


def test_project_names_edit_manifest_and_exclusive_pin(tmp_path: Path) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "application-data" / "projects",
    )
    with TestClient(create_app(settings)) as client:
        default = client.post("/api/v1/projects", json={})
        suffix = client.post("/api/v1/projects", json={"name": " new project "})
        second = client.post("/api/v1/projects", json={"name": "Second"})
        assert default.status_code == suffix.status_code == second.status_code == 201
        first_project = default.json()
        suffix_project = suffix.json()
        assert first_project["name"] == "New project"
        assert suffix_project["name"] == "new project(1)"

        edited = client.patch(
            f"/api/v1/projects/{second.json()['project_id']}",
            json={"name": "NEW PROJECT", "description": "  Renamed  "},
        )
        assert edited.status_code == 200
        assert edited.json()["name"] == "NEW PROJECT(2)"
        manifest = json.loads(
            (Path(edited.json()["root_path"]) / "project.vproject.yaml").read_text()
        )
        assert manifest["name"] == "NEW PROJECT(2)"
        assert manifest["description"] == "Renamed"

        assert (
            client.patch(
                f"/api/v1/projects/{first_project['project_id']}", json={"pinned": True}
            ).json()["pinned"]
            is True
        )
        assert (
            client.patch(
                f"/api/v1/projects/{suffix_project['project_id']}",
                json={"pinned": True},
            ).json()["pinned"]
            is True
        )
        listed = {
            item["project_id"]: item
            for item in client.get("/api/v1/projects").json()["projects"]
        }
        assert listed[first_project["project_id"]]["pinned"] is False
        assert listed[suffix_project["project_id"]]["pinned"] is True


def test_project_delete_trashes_managed_and_unlinks_external(tmp_path: Path) -> None:
    managed_root = tmp_path / "application-data" / "projects"
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=managed_root,
    )
    external_root = tmp_path / "external"
    with TestClient(create_app(settings)) as client:
        managed = client.post("/api/v1/projects", json={"name": "Managed"}).json()
        external = client.app.state.projects.create(
            root_path=external_root, name="External"
        )
        removed_managed = client.delete(f"/api/v1/projects/{managed['project_id']}")
        removed_external = client.delete(f"/api/v1/projects/{external['project_id']}")
        assert removed_managed.json()["disposition"] == "trashed"
        assert removed_external.json()["disposition"] == "unlinked"
        assert not Path(managed["root_path"]).exists()
        assert (
            managed_root.parent / "trash" / "projects" / managed["project_id"]
        ).is_dir()
        assert external_root.is_dir()
        assert (
            client.get(f"/api/v1/projects/{managed['project_id']}").status_code == 422
        )
        assert (
            client.get(f"/api/v1/projects/{external['project_id']}").status_code == 422
        )
        reopened = client.post(
            "/api/v1/projects/open", json={"root_path": str(external_root)}
        )
        assert reopened.status_code == 200
        assert reopened.json()["project_id"] == external["project_id"]


def test_project_description_length_returns_typed_contract_error(
    tmp_path: Path,
) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "application-data" / "projects",
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/projects",
            json={
                "name": "Too long",
                "description": "x" * 501,
            },
        )
    assert response.status_code == 422
    assert response.json()["code"] == "contract_invalid"


def test_nested_project_agent_routes_create_draft_validate_commit_and_export(
    tmp_path: Path,
) -> None:
    fixture_root = ROOT / "contracts" / "fixtures" / "project" / "agents"
    agents = [
        json.loads((fixture_root / slug / "agent.vagent.yaml").read_text())
        for slug in ("github-triage", "release-summary")
    ]
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "application-data" / "projects",
    )
    with TestClient(create_app(settings)) as client:
        health = client.get("/api/v1/health")
        assert health.json()["database_ready"] is True
        assert health.json()["database_revision"] == "local_0008_factory_sessions"
        created = client.post(
            "/api/v1/projects",
            json={
                "name": "Example",
                "agents": agents,
            },
        )
        assert created.status_code == 201
        project = created.json()
        agent_id = project["agents"][0]["agent_id"]
        assert project["agents"][0]["source_file_hash"]
        draft = client.get(
            f"/api/v1/projects/{project['project_id']}/agents/{agent_id}/draft"
        )
        assert draft.status_code == 200
        assert draft.headers["etag"] == draft.json()["etag"]
        assert (
            client.post(
                f"/api/v1/projects/{project['project_id']}/agents/{agent_id}/validate"
            ).json()["valid"]
            is True
        )
        committed = client.post(
            f"/api/v1/projects/{project['project_id']}/agents/{agent_id}/commit",
            json={"expected_revision": draft.json()["revision"]},
            headers={"Idempotency-Key": new_uuid7(), "If-Match": draft.headers["etag"]},
        )
        assert committed.status_code == 200
        exported = client.get(
            f"/api/v1/projects/{project['project_id']}/agents/{agent_id}/export"
        )
        assert exported.json()["source"]["agent_id"] == agent_id


def test_commit_requires_current_revision_and_etag(tmp_path: Path) -> None:
    source = json.loads(
        (
            ROOT / "contracts/fixtures/project/agents/github-triage/agent.vagent.yaml"
        ).read_text()
    )
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        agent_id = project["agents"][0]["agent_id"]
        base = f"/api/v1/projects/{project['project_id']}/agents/{agent_id}"
        draft = client.get(base + "/draft")
        stale = client.post(
            base + "/commit",
            json={"expected_revision": draft.json()["revision"] + 1},
            headers={"If-Match": draft.headers["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert stale.status_code == 409
        assert stale.json()["code"] == "draft_conflict"
