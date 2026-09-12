from __future__ import annotations

import io
import zipfile
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings


def _generic_yaml() -> bytes:
    return yaml.safe_dump(
        {
            "name": "Research Import",
            "description": "An external research assistant.",
            "model": {"provider": "openai", "model": "gpt-5"},
            "instructions": "Research the request and return a concise result.",
            "inputs": {"topic": "string"},
            "outputs": {"result": "string"},
            "tools": ["filesystem.read", "python_executor"],
            "skills": [
                {
                    "name": "Evidence style",
                    "instruction": "Separate claims from evidence.",
                }
            ],
        },
        sort_keys=False,
    ).encode("utf-8")


def _folder_archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "research/agent.yaml",
            "name: Folder Research\ninstructions:\n  file: prompts/system.md\n",
        )
        archive.writestr("research/prompts/system.md", "Use the attached evidence.\n")
        archive.writestr("research/knowledge/notes.md", "Bounded notes.\n")
    return buffer.getvalue()


def test_external_agent_import_analyzes_yaml_zip_and_folder_then_applies(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "folder-agent"
    (folder / "prompts").mkdir(parents=True)
    (folder / "knowledge").mkdir()
    (folder / "agent.yaml").write_text(
        "name: Folder Research\ninstructions:\n  file: prompts/system.md\n",
        encoding="utf-8",
    )
    (folder / "prompts/system.md").write_text(
        "Use the attached evidence.\n", encoding="utf-8"
    )
    (folder / "knowledge/notes.md").write_text("Bounded notes.\n", encoding="utf-8")
    with TestClient(
        create_app(
            LocalSettings(
                database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
                project_storage_root=tmp_path / "projects",
            )
        )
    ) as client:
        project = client.post("/api/v1/projects", json={"name": "Imported Agents"})
        assert project.status_code == 201, project.text
        project_id = project.json()["project_id"]

        yaml_import = client.post(
            "/api/v1/agent-imports",
            files={"file": ("research.yaml", _generic_yaml(), "text/yaml")},
        )
        assert yaml_import.status_code == 201, yaml_import.text
        analyzed = yaml_import.json()
        assert analyzed["detected_format"] == "generic_yaml"
        assert analyzed["preview"]["name"] == "Research Import"
        assert analyzed["preview"]["instructions"].startswith("Research the request")
        assert analyzed["compatibility"] < 1
        assert any(
            item["status"] == "unsupported" and item["original"] == "python_executor"
            for item in analyzed["capabilities"]
        )
        assert (
            any(
                item["code"] == "tool_approval_path_required"
                for item in analyzed["warnings"]
            )
            is False
        )

        fetched = client.get(f"/api/v1/agent-imports/{analyzed['import_id']}")
        assert fetched.status_code == 200
        assert fetched.json()["generated_source"]["component_type"] == "Flow"

        refused = client.post(
            f"/api/v1/agent-imports/{analyzed['import_id']}/apply",
            json={"project_id": project_id, "confirm": False},
        )
        assert refused.status_code == 422

        applied = client.post(
            f"/api/v1/agent-imports/{analyzed['import_id']}/apply",
            json={"project_id": project_id, "confirm": True},
        )
        assert applied.status_code == 200, applied.text
        agent = applied.json()["agent"]
        assert agent["name"] == "Research Import"
        assert (
            Path(project.json()["root_path"])
            / Path(agent["source_path"]).parent
            / "import/manifest.json"
        ).is_file()
        assert (
            client.get(f"/api/v1/agent-imports/{analyzed['import_id']}").json()["state"]
            == "applied"
        )

        zip_import = client.post(
            "/api/v1/agent-imports",
            files={"file": ("folder-agent.zip", _folder_archive(), "application/zip")},
        )
        assert zip_import.status_code == 201, zip_import.text
        assert zip_import.json()["source_kind"] == "zip"
        assert (
            zip_import.json()["preview"]["instructions"] == "Use the attached evidence."
        )
        assert zip_import.json()["preview"]["knowledge_files"] == [
            "research/knowledge/notes.md"
        ]
        zip_applied = client.post(
            f"/api/v1/agent-imports/{zip_import.json()['import_id']}/apply",
            json={"project_id": project_id, "confirm": True},
        )
        assert zip_applied.status_code == 200, zip_applied.text
        zip_agent = zip_applied.json()["agent"]
        zip_agent_root = (
            Path(project.json()["root_path"]) / Path(zip_agent["source_path"]).parent
        )
        assert (zip_agent_root / "import/files/research/prompts/system.md").read_text(
            encoding="utf-8"
        ) == "Use the attached evidence.\n"
        assert (zip_agent_root / "import/files/research/knowledge/notes.md").read_text(
            encoding="utf-8"
        ) == "Bounded notes.\n"

        folder_import = client.post(
            "/api/v1/agent-imports",
            data={"path": str(folder)},
        )
        assert folder_import.status_code == 201, folder_import.text
        assert folder_import.json()["source_kind"] == "folder"
        assert (
            folder_import.json()["preview"]["instructions"]
            == "Use the attached evidence."
        )
        assert folder_import.json()["preview"]["knowledge_files"] == [
            "knowledge/notes.md"
        ]
