from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from veyra_agent_platform.local.projects.packaging import (
    ProjectPackageError,
    unpack_project_archive,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_AGENTS = ROOT / "contracts" / "fixtures" / "project" / "agents"


def _source(slug: str) -> bytes:
    return (FIXTURE_AGENTS / slug / "agent.vagent.yaml").read_bytes()


def _manifest(*, parent: bool = False) -> bytes:
    parent_agent_id = "01a03795-a5b0-7b1c-bad0-e07ac7dda22b"
    child_agent_id = "01a03795-a5b0-72d3-8204-6f66a60073db"
    child = {
        "agent_id": child_agent_id,
        "slug": "release-summary",
        "path": "agents/release-summary",
    }
    if parent:
        child["parent_agent_id"] = parent_agent_id
    payload = {
        "schema_version": "1.0",
        "project_version": "1",
        "project_id": "01a03795-a5b0-7234-ba76-5c5f0e029334",
        "name": "Packaged Project",
        "description": "Portable fixture",
        "default_agent_id": parent_agent_id,
        "resource_policy": {
            "max_concurrent_runs": 1,
            "max_nodes_per_run": 32,
            "max_run_seconds": 900,
        },
        "agents": [
            {
                "agent_id": parent_agent_id,
                "slug": "github-triage",
                "path": "agents/github-triage",
            },
            child,
        ],
    }
    return json.dumps(payload).encode("utf-8")


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _valid_entries(**extra: bytes) -> dict[str, bytes]:
    entries = {
        "project.vproject.yaml": _manifest(parent=True),
        "agents/github-triage/agent.vagent.yaml": _source("github-triage"),
        "agents/release-summary/agent.vagent.yaml": _source("release-summary"),
        "agents/github-triage/README.md": b"# GitHub Triage\n",
        "resources/note.md": b"keep this resource\n",
    }
    entries.update(extra)
    return entries


def test_unpack_remaps_identities_and_preserves_parent_and_resources() -> None:
    archive = unpack_project_archive("team.vproject.zip", _zip_bytes(_valid_entries()))
    source_ids = {source.agent_id for source in archive.sources}
    assert "01a03795-a5b0-7b1c-bad0-e07ac7dda22b" not in source_ids
    assert archive.default_agent_id in source_ids
    assert len(archive.parents) == 1
    child_id, parent_id = next(iter(archive.parents.items()))
    assert child_id in source_ids
    assert parent_id == archive.default_agent_id
    assert archive.extra_files["resources/note.md"] == b"keep this resource\n"
    assert archive.extra_files["agents/github-triage/README.md"].startswith(b"#")


def test_unpack_rejects_zip_slip_and_secret_files() -> None:
    with pytest.raises(ProjectPackageError, match="escapes"):
        unpack_project_archive(
            "evil.zip",
            _zip_bytes({"../secret.md": b"nope\n", **_valid_entries()}),
        )
    with pytest.raises(ProjectPackageError, match="secrets"):
        unpack_project_archive(
            "evil.zip",
            _zip_bytes(_valid_entries(**{"resources/.env": b"TOKEN=1\n"})),
        )


def test_unpack_rejects_disallowed_type_and_oversized_member() -> None:
    with pytest.raises(ProjectPackageError, match="disallowed file type"):
        unpack_project_archive(
            "evil.zip",
            _zip_bytes(_valid_entries(**{"resources/note.bin": b"nope"})),
        )
    with pytest.raises(ProjectPackageError, match="indexing"):
        unpack_project_archive(
            "huge.zip",
            _zip_bytes(_valid_entries(**{"resources/huge.md": b"x" * 1_000_001})),
        )


def test_unpack_rejects_orphaned_agent_path() -> None:
    with pytest.raises(ProjectPackageError, match="disallowed path"):
        unpack_project_archive(
            "orphan.zip",
            _zip_bytes(_valid_entries(**{"agents/not-listed/README.md": b"# x\n"})),
        )
