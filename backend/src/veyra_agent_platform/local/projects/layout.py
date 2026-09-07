"""On-disk Project layout: one folder per resource kind.

`resources/` remains a legacy raw-file bucket so existing file tools keep
working. New raw files belong in `assets/`; documents belong in `knowledge/`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.contracts.resource import ResourceKind, ResourceManifest
from veyra_agent_platform.contracts.workflow import WorkflowSource

PROJECT_LAYOUT_DIRECTORIES: tuple[Path, ...] = (
    Path("agents"),
    Path("workflows"),
    Path("components") / "primitive",
    Path("components") / "composite",
    Path("knowledge"),
    Path("assets"),
    Path("tests"),
    Path("resources"),
)

INDEXED_ROOT_DIRECTORIES: tuple[Path, ...] = (
    Path("workflows"),
    Path("components"),
    Path("knowledge"),
    Path("assets"),
    Path("tests"),
    Path("resources"),
)

ARCHIVE_PREFIXES: tuple[str, ...] = (
    "agents/",
    "workflows/",
    "components/",
    "knowledge/",
    "assets/",
    "tests/",
    "resources/",
)


def ensure_project_layout(root: Path, *, mode: int = 0o700) -> None:
    for relative in PROJECT_LAYOUT_DIRECTORIES:
        path = root / relative
        path.mkdir(mode=mode, parents=True, exist_ok=True)


def agent_resource_manifest(source: AgentSource) -> dict[str, str]:
    return ResourceManifest(
        schema_version=source.schema_version,
        kind=ResourceKind.AGENT,
        resource_id=source.agent_id,
        version=source.version,
        slug=source.slug,
        name=source.name,
        description=source.description,
    ).to_dict()


def workflow_resource_manifest(source: WorkflowSource) -> dict[str, str]:
    return ResourceManifest(
        schema_version=source.schema_version,
        kind=ResourceKind.WORKFLOW,
        resource_id=source.workflow_id,
        version=source.version,
        slug=source.slug,
        name=source.name,
        description=source.description,
    ).to_dict()


def knowledge_resource_manifest(
    *,
    resource_id: str,
    slug: str,
    name: str,
    description: str,
    version: str = "1.0.0",
) -> dict[str, str]:
    return ResourceManifest(
        schema_version="1.0",
        kind=ResourceKind.KNOWLEDGE,
        resource_id=resource_id,
        version=version,
        slug=slug,
        name=name,
        description=description,
    ).to_dict()


def blank_knowledge_document(name: str) -> str:
    return f"# {name}\n\n"


def blank_workflow_source(
    *,
    workflow_id: str | None = None,
    slug: str = "new-workflow",
    name: str = "New Workflow",
    description: str = "A blank Workflow that orchestrates Agents.",
) -> WorkflowSource:
    start = {"id": "start", "component_type": "Start"}
    output = {"id": "output", "component_type": "Output", "output_name": "result"}
    return WorkflowSource.from_dict(
        {
            "schema_version": "1.0",
            "component_type": "Workflow",
            "workflow_id": workflow_id or new_uuid7(),
            "slug": slug,
            "name": name,
            "description": description,
            "version": "1.0.0",
            "inputs": {"prompt": "string"},
            "outputs": {"result": "string"},
            "nodes": [start, output],
            "transitions": [{"from": "start", "port": "next", "to": "output"}],
            "extensions": {
                "veyra": {
                    "permissions": {"network_hosts": [], "tools": []},
                    "verification": {"required": False, "checks": []},
                }
            },
            "ui": {
                "positions": {
                    "start": {"x": 90, "y": 80},
                    "output": {"x": 330, "y": 80},
                }
            },
            "lock": {},
        }
    )


def resource_yaml_path(entry_path: str) -> str:
    return f"{entry_path}/resource.yaml"


def listed_archive_prefixes(entries: list[Any]) -> tuple[str, ...]:
    return tuple(f"{entry.path}/" for entry in entries)
