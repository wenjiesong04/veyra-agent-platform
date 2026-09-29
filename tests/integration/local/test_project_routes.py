from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.storage.bootstrap import HEAD_REVISION

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
        assert project["workflows"] == []
        assert project["workflow_count"] == 0
        assert project["indexed_at"]
        root = Path(project["root_path"])
        assert root.is_relative_to(managed_root)
        assert root.name == "Empty"
        assert preserved.read_text(encoding="utf-8") == "keep"

        duplicate = client.post(
            "/api/v1/projects",
            json={"name": "Empty"},
        )
        assert duplicate.status_code == 201
        assert Path(duplicate.json()["root_path"]).name == "Empty(1)"
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

        nested = root / "assets"
        opened_nested = client.post(
            "/api/v1/projects/open", json={"root_path": str(nested)}
        )
        assert opened_nested.status_code == 422
        assert opened_nested.json()["code"] == "not_a_project"
        assert not (nested / "agents").exists()
        assert not (nested / "project.vproject.yaml").exists()


def test_project_resources_are_separate_from_global_catalog(tmp_path: Path) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/v1/projects", json={"name": "Resource scope"})
        assert created.status_code == 201
        project_id = created.json()["project_id"]

        catalog = client.get("/api/v1/resources")
        assert catalog.status_code == 200
        candidate = next(
            item
            for item in catalog.json()["resources"]
            if item["kind"] in {"tool", "skill", "policy", "template"}
        )

        project_resources = client.get(f"/api/v1/projects/{project_id}/resources")
        assert project_resources.status_code == 200
        assert project_resources.json()["project_count"] == 0
        assert any(
            item["scope"] == "builtin" for item in project_resources.json()["resources"]
        )

        added = client.post(
            f"/api/v1/projects/{project_id}/resources",
            json={"reference": candidate["reference"]},
        )
        assert added.status_code == 201
        assert added.json()["project_count"] == 1
        selected = next(
            item
            for item in added.json()["resources"]
            if item["reference"] == candidate["reference"]
        )
        assert selected["scope"] == "project"
        assert selected["binding_source"] == "manual"
        assert selected["binding_status"] == "current"

        manifest = Path(created.json()["root_path"]) / "project.vproject.yaml"
        assert candidate["reference"] in manifest.read_text(encoding="utf-8")

        removed = client.delete(
            f"/api/v1/projects/{project_id}/resources/"
            f"{candidate['resource_id']}/versions/{candidate['version']}"
        )
        assert removed.status_code == 200
        assert removed.json()["project_count"] == 0

        primitive = next(
            item for item in catalog.json()["resources"] if item["kind"] == "component"
        )
        rejected = client.post(
            f"/api/v1/projects/{project_id}/resources",
            json={"reference": primitive["reference"]},
        )
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "resource_builtin"


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
        assert Path(reopened.json()["root_path"]) == external_root.resolve()
        listed = client.get("/api/v1/projects")
        assert listed.status_code == 200
        listed_projects = listed.json()["projects"]
        listed_ids = {item["project_id"] for item in listed_projects}
        assert listed_ids == {external["project_id"]}
        assert Path(listed_projects[0]["root_path"]) == external_root.resolve()


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
        assert health.json()["database_revision"] == HEAD_REVISION
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
        agent_source_path = (
            Path(project["root_path"]) / project["agents"][0]["source_path"]
        )
        private_comment = "Project-only comment; do not share this text."
        agent_source_path.write_text(
            f"# {private_comment}\n" + agent_source_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        exported = client.get(
            f"/api/v1/projects/{project['project_id']}/agents/{agent_id}/export"
        )
        export_payload = exported.json()
        assert exported.json()["source"]["agent_id"] == agent_id
        assert exported.json()["kind"] == "agent"
        assert exported.json()["version"]
        assert exported.json()["dependencies"] == sorted(
            exported.json()["source"]["lock"]
        )
        assert private_comment in export_payload["source_text"]
        community_package = export_payload["community_package"]
        assert private_comment not in community_package["source_text"]
        assert json.loads(community_package["source_text"]) == export_payload["source"]
        assert community_package["source_hash"]
        assert community_package["behavior_hash"]
        assert community_package["lock_hash"]


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


def test_project_export_import_files_and_parent_remap(tmp_path: Path) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "application-data" / "projects",
    )
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/v1/projects", json={"name": "Team"}).json()
        project_id = created["project_id"]
        parent = client.post(
            f"/api/v1/projects/{project_id}/agents",
            json={"mode": "blank", "name": "Coordinator"},
        )
        child = client.post(
            f"/api/v1/projects/{project_id}/agents",
            json={
                "mode": "blank",
                "name": "Worker",
                "parent_agent_id": parent.json()["agent_id"],
            },
        )
        assert parent.status_code == child.status_code == 201
        root = Path(created["root_path"])
        (root / "resources" / "note.md").write_text("shared note\n", encoding="utf-8")
        (root / "agents" / parent.json()["slug"] / "tests" / "check.md").write_text(
            "ok\n", encoding="utf-8"
        )
        indexed = client.post("/api/v1/projects/open", json={"root_path": str(root)})
        assert indexed.status_code == 200
        listed = client.get(f"/api/v1/projects/{project_id}/files")
        assert listed.status_code == 200
        paths = {item["path"] for item in listed.json()["files"]}
        assert "project.vproject.yaml" in paths
        assert "resources/note.md" in paths
        preview = client.get(
            f"/api/v1/projects/{project_id}/files/content",
            params={"path": "resources/note.md"},
        )
        assert preview.status_code == 200
        assert preview.json()["text"] == "shared note\n"
        escaped = client.get(
            f"/api/v1/projects/{project_id}/files/content",
            params={"path": "../secret.md"},
        )
        assert escaped.status_code == 422

        exported = client.get(f"/api/v1/projects/{project_id}/export")
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith("application/zip")
        assert "Team.vproject.zip" in exported.headers["content-disposition"]

        imported = client.post(
            "/api/v1/projects/import",
            files={
                "file": (
                    "team.vproject.zip",
                    exported.content,
                    "application/zip",
                )
            },
        )
        assert imported.status_code == 201
        payload = imported.json()
        assert payload["project_id"] != project_id
        assert {agent["agent_id"] for agent in payload["agents"]}.isdisjoint(
            {parent.json()["agent_id"], child.json()["agent_id"]}
        )
        imported_child = next(
            agent for agent in payload["agents"] if agent["parent_agent_id"]
        )
        imported_parent = next(
            agent
            for agent in payload["agents"]
            if agent["agent_id"] == imported_child["parent_agent_id"]
        )
        assert imported_parent["name"] == "Coordinator"
        assert imported_child["name"] == "Worker"
        imported_root = Path(payload["root_path"])
        assert (imported_root / "resources" / "note.md").read_text(
            encoding="utf-8"
        ) == "shared note\n"
        assert (
            imported_root / "agents" / imported_parent["slug"] / "tests" / "check.md"
        ).read_text(encoding="utf-8") == "ok\n"
        archive_path = tmp_path / "reimport.vproject.zip"
        archive_path.write_bytes(exported.content)
        imported_from_path = client.post(
            "/api/v1/projects/import-path",
            json={"path": str(archive_path)},
        )
        assert imported_from_path.status_code == 201
        assert imported_from_path.json()["project_id"] not in {
            project_id,
            payload["project_id"],
        }
        missing_archive = client.post(
            "/api/v1/projects/import-path",
            json={"path": str(tmp_path / "missing.vproject.zip")},
        )
        assert missing_archive.status_code == 422
        assert missing_archive.json()["code"] == "project_package_invalid"
        rejected = client.post(
            "/api/v1/projects/import",
            files={"file": ("notes.txt", b"not a zip", "text/plain")},
        )
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "project_package_invalid"


def test_workflow_routes_create_draft_and_remove(tmp_path: Path) -> None:
    managed_root = tmp_path / "application-data" / "projects"
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=managed_root,
    )
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/v1/projects", json={"name": "Workflows"})
        assert created.status_code == 201
        project_id = created.json()["project_id"]
        created_workflow = client.post(
            f"/api/v1/projects/{project_id}/workflows",
            json={"name": "Review path"},
        )
        assert created_workflow.status_code == 201
        workflow = created_workflow.json()
        workflow_id = workflow["workflow_id"]
        assert workflow["name"] == "Review path"
        listed = client.get(f"/api/v1/projects/{project_id}/workflows")
        assert listed.status_code == 200
        assert [item["workflow_id"] for item in listed.json()["workflows"]] == [
            workflow_id
        ]
        draft = client.get(
            f"/api/v1/projects/{project_id}/workflows/{workflow_id}/draft"
        )
        assert draft.status_code == 200
        source = draft.json()["source"]
        source["description"] = "Saved from Studio."
        saved = client.patch(
            f"/api/v1/projects/{project_id}/workflows/{workflow_id}/draft",
            json={"source": source, "expected_revision": draft.json()["revision"]},
            headers={
                "If-Match": draft.headers["etag"],
                "Idempotency-Key": new_uuid7(),
            },
        )
        assert saved.status_code == 200
        assert saved.json()["revision"] == 1
        assert saved.json()["source"]["description"] == "Saved from Studio."
        removed = client.delete(
            f"/api/v1/projects/{project_id}/workflows/{workflow_id}"
        )
        assert removed.status_code == 200
        assert removed.json()["disposition"] == "trashed"
        assert removed.json()["project"]["workflow_count"] == 0
        assert (
            client.get(
                f"/api/v1/projects/{project_id}/workflows/{workflow_id}/draft"
            ).status_code
            == 422
        )


def test_unhandled_workflow_create_error_returns_typed_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from veyra_agent_platform.local.projects.service import ProjectService

    def boom(self: ProjectService, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("workflow index exploded")

    monkeypatch.setattr(ProjectService, "create_workflow", boom)
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "application-data" / "projects",
    )
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/v1/projects", json={"name": "Broken"})
        assert created.status_code == 201
        response = client.post(
            f"/api/v1/projects/{created.json()['project_id']}/workflows",
            json={"name": "Review path"},
        )
        assert response.status_code == 500
        body = response.json()
        assert body["code"] == "local_internal_error"
        assert "workflow index exploded" in body["message"]
        assert body["request_id"]


def test_workflow_validate_and_commit(tmp_path: Path) -> None:
    managed_root = tmp_path / "application-data" / "projects"
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=managed_root,
    )
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/v1/projects", json={"name": "Workflow commit"})
        assert created.status_code == 201
        project_id = created.json()["project_id"]
        created_workflow = client.post(
            f"/api/v1/projects/{project_id}/workflows",
            json={"name": "Blank path"},
        )
        assert created_workflow.status_code == 201
        workflow_id = created_workflow.json()["workflow_id"]
        draft = client.get(
            f"/api/v1/projects/{project_id}/workflows/{workflow_id}/draft"
        )
        assert draft.status_code == 200
        validated = client.post(
            f"/api/v1/projects/{project_id}/workflows/{workflow_id}/validate"
        )
        assert validated.status_code == 200
        assert validated.json()["valid"] is True
        committed = client.post(
            f"/api/v1/projects/{project_id}/workflows/{workflow_id}/commit",
            json={"expected_revision": draft.json()["revision"]},
            headers={
                "If-Match": draft.headers["etag"],
                "Idempotency-Key": new_uuid7(),
            },
        )
        assert committed.status_code == 200
        assert committed.json()["workflow_id"] == workflow_id
        assert committed.json()["version_id"]


def test_knowledge_routes_create_read_and_remove(tmp_path: Path) -> None:
    managed_root = tmp_path / "application-data" / "projects"
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=managed_root,
    )
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/v1/projects", json={"name": "Knowledge"})
        assert created.status_code == 201
        project_id = created.json()["project_id"]
        created_knowledge = client.post(
            f"/api/v1/projects/{project_id}/knowledge",
            json={"name": "Brief", "text": "# Brief\n"},
        )
        assert created_knowledge.status_code == 201
        knowledge = created_knowledge.json()
        knowledge_id = knowledge["knowledge_id"]
        assert knowledge["name"] == "Brief"
        assert knowledge["text"] == "# Brief\n"
        listed = client.get(f"/api/v1/projects/{project_id}/knowledge")
        assert listed.status_code == 200
        assert [item["knowledge_id"] for item in listed.json()["knowledge"]] == [
            knowledge_id
        ]
        fetched = client.get(f"/api/v1/projects/{project_id}/knowledge/{knowledge_id}")
        assert fetched.status_code == 200
        assert fetched.json()["text"] == "# Brief\n"
        patched = client.patch(
            f"/api/v1/projects/{project_id}/knowledge/{knowledge_id}",
            json={"text": "# Updated\n"},
        )
        assert patched.status_code == 200
        assert patched.json()["text"] == "# Updated\n"
        removed = client.delete(
            f"/api/v1/projects/{project_id}/knowledge/{knowledge_id}"
        )
        assert removed.status_code == 200
        assert removed.json()["disposition"] == "trashed"
        assert removed.json()["project"]["knowledge_count"] == 0
