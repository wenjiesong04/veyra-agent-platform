from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest

from veyra_agent_platform.contracts.agent import AgentSource, ComponentType
from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.agent_loop import _tool_input_error
from veyra_agent_platform.local.runtime.tools import ToolRuntime, ToolRuntimeError
from veyra_agent_platform.local.state import EntityStore, EntityStoreError
from veyra_agent_platform.local.storage.bootstrap import migrate_local_database


@pytest.fixture
def store(tmp_path: Path) -> EntityStore:
    database = tmp_path / "entities.sqlite3"
    migrate_local_database(database)
    return EntityStore(database)


def _record(store: EntityStore, project: str, title: str, **data: Any) -> dict:
    return store.write(
        project_id=project,
        entity_type="Task",
        payload={"title": title, **data},
        status="open",
    )


def _counts(store: EntityStore) -> tuple[int, int]:
    with sqlite3.connect(store.database_path) as connection:
        return (
            connection.execute("SELECT COUNT(*) FROM entity_records").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM entity_events").fetchone()[0],
        )


def _source(catalog: ResourceCatalog, tool_id: str) -> AgentSource:
    resource = catalog.detail(tool_id, "1.0.0")
    return AgentSource.from_dict(
        {
            "schema_version": "1.0",
            "agentspec_version": "26.1",
            "component_type": "Flow",
            "agent_id": "01a03795-a5b0-7f61-a971-4c55cead5f27",
            "slug": "entity-query",
            "name": "Entity query fixture",
            "description": "Queries controlled project records.",
            "inputs": {"request": "string"},
            "outputs": {"result": "object"},
            "nodes": [
                {"id": "start", "component_type": "Start"},
                {
                    "id": "entity",
                    "component_type": "Tool",
                    "uses": resource["reference"],
                },
                {"id": "output", "component_type": "Output", "output_name": "result"},
            ],
            "transitions": [
                {"from": "start", "port": "next", "to": "entity"},
                {"from": "entity", "port": "next", "to": "output"},
            ],
            "extensions": {
                "veyra": {
                    "runtime_profile": "veyra-runtime-profile/1",
                    "secret_refs": [],
                    "permissions": {"network_hosts": [], "tools": [tool_id]},
                    "verification": {"required": False, "checks": []},
                }
            },
            "ui": {
                "positions": {
                    "start": {"x": 0, "y": 0},
                    "entity": {"x": 200, "y": 0},
                    "output": {"x": 400, "y": 0},
                }
            },
            "lock": {resource["reference"]: resource["content_hash"]},
        }
    )


def test_query_preserves_multiple_matches_and_stays_project_and_type_scoped(
    store: EntityStore,
) -> None:
    first = _record(store, "project-a", "Same title", done=False)
    second = _record(store, "project-a", "Same title", done=True)
    _record(store, "project-b", "Same title", private="other project")
    store.write(
        project_id="project-a",
        entity_type="Note",
        payload={"title": "Same title"},
        status="open",
    )
    counts = _counts(store)
    result = store.query(
        project_id="project-a", entity_type="Task", filters={"title": "Same title"}
    )
    assert [item["entity_id"] for item in result["records"]] == [
        second["entity_id"],
        first["entity_id"],
    ]
    assert result["records"][0]["data"] == {"title": "Same title", "done": True}
    assert all(item["entity_type"] == "Task" for item in result["records"])
    assert all(item["revision"] == 1 for item in result["records"])
    assert result["truncated"] is False
    assert "other project" not in json.dumps(result)
    assert store.query(project_id="empty-project", entity_type="Task")["records"] == []
    assert _counts(store) == counts


def test_query_matches_literal_field_names_and_json_types(store: EntityStore) -> None:
    boolean = _record(store, "project-a", "boolean", flag=True, nested={"v": [True]})
    _record(store, "project-a", "number", flag=1, nested={"v": [1]})
    literal_name = "title' OR 1=1 --"
    literal = _record(store, "project-a", "literal", **{literal_name: "needle"})
    assert [
        item["entity_id"]
        for item in store.query(
            project_id="project-a", entity_type="Task", filters={"flag": True}
        )["records"]
    ] == [boolean["entity_id"]]
    assert [
        item["entity_id"]
        for item in store.query(
            project_id="project-a",
            entity_type="Task",
            filters={"nested": {"v": [True]}},
        )["records"]
    ] == [boolean["entity_id"]]
    assert [
        item["entity_id"]
        for item in store.query(
            project_id="project-a", entity_type="Task", filters={literal_name: "needle"}
        )["records"]
    ] == [literal["entity_id"]]
    assert (
        store.query(
            project_id="project-a", entity_type="Task", filters={"missing": None}
        )["records"]
        == []
    )


def test_query_returns_bounded_results_and_marks_partial_scans(
    store: EntityStore,
) -> None:
    with sqlite3.connect(store.database_path) as connection:
        connection.executemany(
            """INSERT INTO entity_records(
                entity_id, project_id, entity_type, payload_json, status, revision,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    f"task-{index}",
                    "project-a",
                    "Task",
                    json.dumps({"title": str(index)}),
                    "open",
                    1,
                    "2026-10-05T00:00:00Z",
                    "2026-10-05T00:00:00Z",
                )
                for index in range(501)
            ],
        )
    result = store.query(project_id="project-a", entity_type="Task", limit=50)
    assert len(result["records"]) == 50
    assert result["scanned"] == 50
    assert result["truncated"] is True
    older = store.query(
        project_id="project-a", entity_type="Task", filters={"title": "0"}, limit=50
    )
    assert older == {"records": [], "scanned": 500, "truncated": True}


def test_query_bounds_total_payload_read_bytes(store: EntityStore) -> None:
    _record(store, "project-a", "large-1", content="x" * 600_000)
    _record(store, "project-a", "large-2", content="y" * 600_000)
    result = store.query(project_id="project-a", entity_type="Task", limit=50)
    assert len(result["records"]) == 1
    assert result["scanned"] == 1
    assert result["truncated"] is True
    assert len(json.dumps(result).encode()) < 1_000_000


@pytest.mark.parametrize(
    "options",
    [
        {"limit": 0},
        {"limit": 51},
        {"limit": True},
        {"limit": 1.5},
        {"entity_type": ""},
        {"entity_type": None},
        {"filters": []},
        {"filters": {str(index): index for index in range(9)}},
        {"filters": {"title": "x" * 4_097}},
        {"filters": {"value": float("nan")}},
    ],
)
def test_query_rejects_invalid_or_unbounded_inputs(
    store: EntityStore, options: dict
) -> None:
    with pytest.raises(EntityStoreError) as error:
        store.query(**{"project_id": "project-a", "entity_type": "Task", **options})
    assert error.value.code == "entity_query_invalid"


def test_type_schema_read_is_project_scoped_and_cannot_mutate_definition(
    store: EntityStore,
) -> None:
    schema = {"entity": "Task", "fields": {"title": "string"}}
    store.define_type("project-a", "Task", schema)
    store.define_type("project-b", "Task", {"fields": {"owner": "string"}})
    loaded = store.read_type_schema("project-a", "Task")
    assert loaded == schema
    loaded["fields"]["title"] = "integer"
    assert store.read_type_schema("project-a", "Task") == schema
    assert store.read_type_schema("project-b", "Task") != schema
    assert store.read_type_schema("missing-project", "Task") is None


def test_ensure_type_preserves_existing_definition_and_allows_canonical_replay(
    store: EntityStore,
) -> None:
    original = {"entity": "Task", "fields": {"title": "string"}}
    store.define_type("project-a", "Task", original)
    store.ensure_type(
        "project-a", "Task", {"fields": {"title": "string"}, "entity": "Task"}
    )
    with pytest.raises(EntityStoreError) as error:
        store.ensure_type("project-a", "Task", {"fields": {"title": "integer"}})
    assert error.value.code == "entity_schema_conflict"
    assert store.read_type_schema("project-a", "Task") == original
    store.ensure_type("project-b", "Task", {"fields": {"title": "integer"}})
    assert store.read_type_schema("project-b", "Task") == {
        "fields": {"title": "integer"}
    }


def test_concurrent_ensure_type_never_replaces_another_definition(
    store: EntityStore,
) -> None:
    barrier = Barrier(2)
    choices = ({"fields": {"title": "string"}}, {"fields": {"title": "integer"}})

    def ensure(schema: dict) -> str:
        barrier.wait(timeout=5)
        try:
            store.ensure_type("project-a", "Task", schema)
        except EntityStoreError as exc:
            return exc.code
        return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(ensure, choices))
    assert sorted(results) == ["created", "entity_schema_conflict"]
    winner = choices[results.index("created")]
    assert store.read_type_schema("project-a", "Task") == winner


def test_query_adapter_has_permissions_receipt_and_authoritative_project_scope(
    store: EntityStore,
    tmp_path: Path,
) -> None:
    owned = _record(store, "project-a", "owned")
    _record(store, "project-b", "private")
    catalog = ResourceCatalog()
    descriptor = catalog.detail("veyra.tool.entity.query", "1.0.0")
    assert descriptor["capabilities"] == ["entity_query"]
    assert descriptor["spec"]["output_schema"] == {
        "records": "array",
        "scanned": "integer",
        "truncated": "boolean",
    }
    assert _tool_input_error(descriptor, {"entity_type": "Task"}) is None
    source = _source(catalog, "veyra.tool.entity.query")
    node = next(
        item for item in source.nodes if item.component_type is ComponentType.TOOL
    )
    runtime = ToolRuntime(catalog, entity_store=store)
    values = {"entity_type": "Task", "project_id": "project-b"}
    authorization = runtime.authorize(source=source, node=node, values=values)
    assert authorization.decision == "allowed"
    assert authorization.approval_required is False
    execution = runtime.execute(
        project_root=tmp_path,
        source=source,
        node=node,
        values=values,
        authorization=authorization,
        approved=False,
        project_id="project-a",
    )
    assert [item["entity_id"] for item in execution.output["records"]] == [
        owned["entity_id"]
    ]
    assert execution.receipt["authorization"] == "allowed"
    assert execution.receipt["output_digest"] == sha256_digest(execution.output)
    assert execution.receipt["adapter"] == "veyra.runtime.entity.query"
    with pytest.raises(ToolRuntimeError, match="current Project"):
        runtime.execute(
            project_root=tmp_path,
            source=source,
            node=node,
            values=values,
            authorization=authorization,
            approved=False,
        )
    denied_source = replace(source, permissions=replace(source.permissions, tools=()))
    denied = runtime.authorize(source=denied_source, node=node, values=values)
    assert denied.decision == "denied"
    assert denied.code == "tool_permission_denied"
    assert runtime._call_project_id.get() is None


@pytest.mark.parametrize(
    "tool_id",
    ["veyra.tool.entity.query", "veyra.tool.entity.read", "veyra.tool.entity.write"],
)
def test_entity_adapters_keep_concurrent_project_scope_separate(
    store: EntityStore,
    tmp_path: Path,
    tool_id: str,
) -> None:
    owned = {
        project: _record(store, project, project)
        for project in ("project-a", "project-b")
    }
    catalog = ResourceCatalog()
    source = _source(catalog, tool_id)
    node = next(
        item for item in source.nodes if item.component_type is ComponentType.TOOL
    )
    runtime = ToolRuntime(catalog, entity_store=store)
    adapter_name = catalog.detail(tool_id, "1.0.0")["spec"]["adapter"]
    original = runtime._adapters[adapter_name]
    barrier = Barrier(2)

    def concurrent_adapter(**kwargs: Any):
        barrier.wait(timeout=5)
        return original(**kwargs)

    runtime._adapters[adapter_name] = concurrent_adapter

    def execute(project: str) -> dict:
        values = (
            {"entity_type": "Task"}
            if tool_id.endswith("query")
            else {"entity_id": owned[project]["entity_id"]}
            if tool_id.endswith("read")
            else {
                "entity_type": "Task",
                "payload": {"owner": project},
                "status": "open",
            }
        )
        authorization = runtime.authorize(source=source, node=node, values=values)
        result = runtime.execute(
            project_root=tmp_path,
            source=source,
            node=node,
            values=values,
            authorization=authorization,
            approved=False,
            project_id=project,
        )
        assert runtime._call_project_id.get() is None
        return result.output

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(execute, ("project-a", "project-b")))
    for project, result in zip(("project-a", "project-b"), results, strict=True):
        if tool_id.endswith("query"):
            assert [row["data"]["title"] for row in result["records"]] == [project]
        elif tool_id.endswith("read"):
            assert result["payload"]["title"] == project
        else:
            assert store.read(project, result["entity_id"])["payload"] == {
                "owner": project
            }
