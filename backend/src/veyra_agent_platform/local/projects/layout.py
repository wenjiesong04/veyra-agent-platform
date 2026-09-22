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

DEFAULT_CANVAS_NOTE_ID = "note_intro"
DEFAULT_CANVAS_NOTE_X = 0
DEFAULT_CANVAS_NOTE_Y = -220
DEFAULT_CANVAS_NOTE_WIDTH = 420
BLANK_AGENT_NOTE_TEXT = "描述此 Agent 的用途、输入、输出和使用说明。"
BLANK_WORKFLOW_NOTE_TEXT = "描述此 Workflow 的用途、编排的 Agent，以及何时运行。"

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
                },
                "notes": {
                    DEFAULT_CANVAS_NOTE_ID: default_canvas_note(
                        BLANK_WORKFLOW_NOTE_TEXT
                    )
                },
            },
            "lock": {},
        }
    )


def resource_yaml_path(entry_path: str) -> str:
    return f"{entry_path}/resource.yaml"


def listed_archive_prefixes(entries: list[Any]) -> tuple[str, ...]:
    return tuple(f"{entry.path}/" for entry in entries)


def default_canvas_note(text: str, *, color: str = "amber") -> dict[str, Any]:
    """Return a canvas-only note that is default, optional, and not runtime."""

    return {
        "x": DEFAULT_CANVAS_NOTE_X,
        "y": DEFAULT_CANVAS_NOTE_Y,
        "text": text[:4000],
        "color": color,
        "width": DEFAULT_CANVAS_NOTE_WIDTH,
        "manual_position": False,
    }


def attach_default_canvas_note(ui: dict[str, Any], text: str) -> dict[str, Any]:
    next_ui = dict(ui)
    notes = dict(next_ui.get("notes") or {})
    if DEFAULT_CANVAS_NOTE_ID not in notes:
        notes[DEFAULT_CANVAS_NOTE_ID] = default_canvas_note(text)
    next_ui["notes"] = notes
    return next_ui
