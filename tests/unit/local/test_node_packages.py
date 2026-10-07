from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from veyra_agent_platform.local.resources import (
    NodePackageError,
    ResourceCatalog,
    default_nodes_root,
    load_node_packages,
    node_definition,
)


def test_platform_tools_and_skills_declare_resolver_capabilities() -> None:
    packages = load_node_packages()
    by_id = {
        package.definition["resource_id"]: package.definition for package in packages
    }
    assert by_id["veyra.tool.web.search"]["capabilities"] == ["web_search"]
    assert by_id["veyra.tool.filesystem.read"]["capabilities"] == ["workspace_read"]
    assert by_id["veyra.skill.research-brief"]["capabilities"] == ["research_planning"]
    assert by_id["veyra.template.starter-agent"]["loop_compatible"] is False


def test_platform_node_packages_are_the_only_catalog_source() -> None:
    root = default_nodes_root()
    packages = load_node_packages()

    assert not (root / "catalog.v1.json").exists()
    assert len(packages) == 41
    assert node_definition("veyra.tool.entity.query", "1.0.0")["capabilities"] == [
        "entity_query"
    ]
    assert {package.path.name for package in packages} == {"node.yaml"}
    assert node_definition("veyra.tool.filesystem.read", "1.0.0")["kind"] == "tool"
    with pytest.raises(NodePackageError, match="unknown node package"):
        node_definition("veyra.tool.missing", "1.0.0")


def test_content_hash_ignores_palette_ui(tmp_path: Path) -> None:
    original = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    clone = tmp_path / "nodes"
    shutil.copytree(
        default_nodes_root(),
        clone,
        ignore=shutil.ignore_patterns("*.json", "README.md"),
    )
    target = clone / "filesystem" / "read" / "node.yaml"
    target.write_text(
        target.read_text(encoding="utf-8").replace("file-text", "file-search"),
        encoding="utf-8",
    )
    mutated = ResourceCatalog(clone).detail("veyra.tool.filesystem.read", "1.0.0")

    assert original["content_hash"] == mutated["content_hash"]
    assert mutated["spec"]["ui"]["icon"] == "file-search"


def test_content_hash_tracks_behavior_text(tmp_path: Path) -> None:
    original = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    clone = tmp_path / "nodes"
    shutil.copytree(
        default_nodes_root(),
        clone,
        ignore=shutil.ignore_patterns("*.json", "README.md"),
    )
    target = clone / "filesystem" / "read" / "node.yaml"
    target.write_text(
        target.read_text(encoding="utf-8").replace(
            "Read a bounded Project path and return file contents.",
            "Read a bounded Project path.",
        ),
        encoding="utf-8",
    )
    mutated = ResourceCatalog(clone).detail("veyra.tool.filesystem.read", "1.0.0")
    assert original["content_hash"] != mutated["content_hash"]


def test_invalid_node_package_is_rejected(tmp_path: Path) -> None:
    clone = tmp_path / "nodes"
    shutil.copytree(
        default_nodes_root(),
        clone,
        ignore=shutil.ignore_patterns("*.json", "README.md"),
    )
    target = clone / "filesystem" / "read" / "node.yaml"
    target.write_text(
        target.read_text(encoding="utf-8") + "extra: true\n",
        encoding="utf-8",
    )

    with pytest.raises(NodePackageError, match="unsupported fields"):
        load_node_packages(clone)


def test_empty_node_root_is_rejected(tmp_path: Path) -> None:
    empty = tmp_path / "nodes"
    empty.mkdir()
    with pytest.raises(NodePackageError, match="no node.yaml packages"):
        load_node_packages(empty)
