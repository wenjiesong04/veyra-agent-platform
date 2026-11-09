from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config

from tests.unit.local.test_entity_query import _source
from veyra_agent_platform.contracts.agent import ComponentType
from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.task_structure import StateRequirement
from veyra_agent_platform.local.builder.capability_from_plan import (
    derive_plan_capabilities,
)
from veyra_agent_platform.local.builder.execution_planner import compile_execution_plan
from veyra_agent_platform.local.builder.model_requirements import (
    derive_model_requirements,
)
from veyra_agent_platform.local.builder.task_planner import plan_task_structure
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.agent_loop import _tool_input_error
from veyra_agent_platform.local.runtime.tools import ToolRuntime, ToolRuntimeError
from veyra_agent_platform.local.state import EntityStore, EntityStoreError
from veyra_agent_platform.local.state.entity_store import (
    ENTITY_HISTORY_MAX_BYTES,
    ENTITY_HISTORY_MAX_RECORDS,
)
from veyra_agent_platform.local.storage.bootstrap import (
    HEAD_REVISION,
    migrate_local_database,
)


@pytest.fixture
def store(tmp_path: Path) -> EntityStore:
    database = tmp_path / "history.sqlite3"
    migrate_local_database(database)
    return EntityStore(database)


def write(store: EntityStore, value: int, entity_id: str | None = None, **options):
    return store.write(
        project_id="project-a",
        entity_type="Record",
        payload={"value": value},
        status="open",
        entity_id=entity_id,
        **options,
    )


def history(store: EntityStore, entity_id: str, **options):
    return store.history(
        project_id="project-a", entity_type="Record", entity_id=entity_id, **options
    )


def test_new_writes_retain_actual_snapshots_status_time_and_source(
    store: EntityStore,
) -> None:
    first = write(store, 1, source="first-run")
    second = store.write(
        project_id="project-a",
        entity_type="Record",
        entity_id=first["entity_id"],
        payload={"value": 2, "nested": ["changed"]},
        status="done",
        source="next-run",
    )
    second["payload"]["value"] = 999
    result = history(store, first["entity_id"])
    assert result["available_from"] == 1 and result["incomplete"] is False
    assert result["current_revision"] == 2 and result["truncated"] is False
    assert [row["revision"] for row in result["revisions"]] == [2, 1]
    assert [row["data"] for row in result["revisions"]] == [
        {"value": 2, "nested": ["changed"]},
        {"value": 1},
    ]
    assert [row["status"] for row in result["revisions"]] == ["done", "open"]
    assert [row["source"] for row in result["revisions"]] == ["next-run", "first-run"]
    assert all(
        row["snapshot_kind"] == "write" and row["recorded_at"].endswith("Z")
        for row in result["revisions"]
    )
    assert store.read("project-a", first["entity_id"])["payload"]["value"] == 2


def test_0036_upgrade_keeps_only_known_baseline_and_does_not_fabricate_prior_history(
    tmp_path: Path,
) -> None:
    database = tmp_path / "old.sqlite3"
    config = Config("backend/migrations/local/alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    command.upgrade(config, "local_0036_model_capabilities")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO entity_records VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "old",
                "project-a",
                "Record",
                '{"value":4}',
                "open",
                4,
                "created",
                "updated",
            ),
        )
        connection.execute(
            "INSERT INTO entity_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "digest-only",
                "old",
                "payload",
                "old-digest",
                "new-digest",
                "tool",
                "updated",
            ),
        )
    migrate_local_database(database)
    assert HEAD_REVISION == "local_0038_work_item_version_binding"
    store = EntityStore(database)
    result = history(store, "old")
    assert result["available_from"] == 4 and result["incomplete"] is True
    assert result["revisions"] == [
        {
            "revision": 4,
            "data": {"value": 4},
            "status": "open",
            "source": "legacy_baseline",
            "recorded_at": "updated",
            "snapshot_kind": "baseline",
        }
    ]
    write(store, 5, "old", source="new-run")
    result = history(store, "old")
    assert [row["revision"] for row in result["revisions"]] == [5, 4]
    assert result["available_from"] == 4 and result["incomplete"] is True
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT old_digest FROM entity_events WHERE event_id = 'digest-only'"
        ).fetchone() == ("old-digest",)
    command.downgrade(config, "local_0036_model_capabilities")
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT revision, payload_json FROM entity_records WHERE entity_id = 'old'"
        ).fetchone() == (5, '{"value": 5}')


def test_history_is_project_type_and_identity_scoped_without_writes(
    store: EntityStore,
) -> None:
    owned = write(store, 1)
    other = store.write(
        project_id="project-b",
        entity_type="Record",
        payload={"private": True},
        status="open",
    )
    assert history(store, other["entity_id"]) is None
    assert (
        store.history(
            project_id="project-b", entity_type="Record", entity_id=owned["entity_id"]
        )
        is None
    )
    assert (
        store.history(
            project_id="project-a", entity_type="Other", entity_id=owned["entity_id"]
        )
        is None
    )
    assert history(store, "missing") is None
    with sqlite3.connect(store.database_path) as connection:
        before = connection.execute("SELECT COUNT(*) FROM entity_revisions").fetchone()
    assert "private" not in json.dumps(history(store, owned["entity_id"]))
    with sqlite3.connect(store.database_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM entity_revisions").fetchone()
            == before
        )


def test_snapshot_failure_rolls_back_record_event_and_snapshot(
    store: EntityStore, monkeypatch
) -> None:
    first = write(store, 1)

    def fail(*args, **kwargs):
        raise EntityStoreError("snapshot_failed", "synthetic snapshot failure")

    monkeypatch.setattr(store, "_snapshot", fail)
    with pytest.raises(EntityStoreError, match="synthetic"):
        write(store, 2, first["entity_id"])
    with pytest.raises(EntityStoreError, match="synthetic"):
        write(store, 3, "never-created")
    assert store.read("project-a", first["entity_id"])["revision"] == 1
    assert store.read("project-a", "never-created") is None
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM entity_events").fetchone() == (
            1,
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM entity_revisions"
        ).fetchone() == (1,)


def test_concurrent_writes_keep_distinct_committed_revision_snapshots(
    store: EntityStore,
) -> None:
    first = write(store, 0)
    barrier = Barrier(2)

    def update(value):
        barrier.wait(timeout=5)
        return write(store, value, first["entity_id"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(update, [1, 2]))
    assert sorted(row["revision"] for row in results) == [2, 3]
    result = history(store, first["entity_id"])
    assert sorted(row["data"]["value"] for row in result["revisions"]) == [0, 1, 2]
    assert result["incomplete"] is False


def test_history_limits_pages_and_explicitly_marks_truncation(
    store: EntityStore,
) -> None:
    first = write(store, 1)
    for value in range(2, 33):
        write(store, value, first["entity_id"])
    newest = history(store, first["entity_id"])
    assert len(newest["revisions"]) == ENTITY_HISTORY_MAX_RECORDS
    assert newest["truncated"] is True and newest["next_before_revision"] == 8
    older = history(store, first["entity_id"], before_revision=8)
    assert [row["revision"] for row in older["revisions"]] == list(range(7, 0, -1))
    assert older["truncated"] is False and older["next_before_revision"] is None


def test_history_bounds_multibyte_payload_and_serialized_metadata(
    store: EntityStore,
) -> None:
    record = store.write(
        project_id="project-a",
        entity_type="Record",
        payload={"text": "汉" * 200_000},
        status="open",
    )
    store.write(
        project_id="project-a",
        entity_type="Record",
        entity_id=record["entity_id"],
        payload={"text": "字" * 200_000},
        status="open",
    )
    result = history(store, record["entity_id"])
    assert len(result["revisions"]) == 1 and result["truncated"] is True
    assert (
        len(json.dumps(result, ensure_ascii=False).encode()) <= ENTITY_HISTORY_MAX_BYTES
    )
    store.write(
        project_id="project-a",
        entity_type="Record",
        entity_id=record["entity_id"],
        payload={"text": "汉" * ENTITY_HISTORY_MAX_BYTES},
        status="open",
    )
    oversized = history(store, record["entity_id"])
    assert oversized["revisions"] == [] and oversized["truncated"] is True
    assert oversized["next_before_revision"] == 3


@pytest.mark.parametrize(
    "options",
    [
        {"limit": 0},
        {"limit": 26},
        {"limit": True},
        {"limit": 1.5},
        {"before_revision": 0},
        {"before_revision": True},
        {"before_revision": 10**30},
        {"entity_type": ""},
        {"entity_id": None},
        {"project_id": ""},
    ],
)
def test_history_rejects_invalid_unbounded_input(
    store: EntityStore, options: dict
) -> None:
    with pytest.raises(EntityStoreError) as error:
        store.history(
            **{
                "project_id": "project-a",
                "entity_type": "Record",
                "entity_id": "a",
                **options,
            }
        )
    assert error.value.code == "entity_history_invalid"


def test_history_adapter_preserves_permissions_receipt_and_authoritative_scope(
    store: EntityStore, tmp_path: Path
) -> None:
    first = write(store, 1)
    catalog = ResourceCatalog()
    descriptor = catalog.detail("veyra.tool.entity.history", "1.0.0")
    assert descriptor["spec"]["input_constraints"]["limit"] == {
        "minimum": 1,
        "maximum": ENTITY_HISTORY_MAX_RECORDS,
    }
    assert (
        descriptor["spec"]["output_constraints"]["max_result_bytes"]
        == ENTITY_HISTORY_MAX_BYTES
    )
    assert (
        _tool_input_error(
            descriptor,
            {"entity_id": first["entity_id"], "entity_type": "Record", "limit": 25},
        )
        is None
    )
    assert "constraints" in _tool_input_error(
        descriptor,
        {"entity_id": first["entity_id"], "entity_type": "Record", "limit": 26},
    )
    source = _source(catalog, "veyra.tool.entity.history")
    node = next(
        item for item in source.nodes if item.component_type is ComponentType.TOOL
    )
    runtime = ToolRuntime(catalog, entity_store=store)
    values = {
        "entity_id": first["entity_id"],
        "entity_type": "Record",
        "project_id": "project-b",
    }
    authorization = runtime.authorize(source=source, node=node, values=values)
    execution = runtime.execute(
        project_root=tmp_path,
        source=source,
        node=node,
        values=values,
        authorization=authorization,
        approved=False,
        project_id="project-a",
    )
    assert execution.output["revisions"][0]["data"] == {"value": 1}
    assert execution.receipt["authorization"] == "allowed"
    assert execution.receipt["output_digest"] == sha256_digest(execution.output)
    assert execution.receipt["adapter"] == "veyra.runtime.entity.history"
    assert runtime._call_project_id.get() is None
    with pytest.raises(ToolRuntimeError, match="current Project"):
        runtime.execute(
            project_root=tmp_path,
            source=source,
            node=node,
            values=values,
            authorization=authorization,
            approved=False,
        )
    with pytest.raises(ToolRuntimeError, match="not found"):
        runtime.execute(
            project_root=tmp_path,
            source=source,
            node=node,
            values=values,
            authorization=authorization,
            approved=False,
            project_id="project-b",
        )
    denied = runtime.authorize(
        source=replace(source, permissions=replace(source.permissions, tools=())),
        node=node,
        values=values,
    )
    assert denied.decision == "denied" and denied.code == "tool_permission_denied"
    scoped = replace(
        source,
        state_contract=StateRequirement(
            entity="Other",
            identity="value",
            scope="project",
            fields={"value": "integer"},
            statuses=("open",),
        ),
    )
    with pytest.raises(ToolRuntimeError, match="state contract"):
        runtime.execute(
            project_root=tmp_path,
            source=scoped,
            node=node,
            values=values,
            authorization=authorization,
            approved=False,
            project_id="project-a",
        )


def test_history_adapter_keeps_concurrent_project_scope_isolated(
    store: EntityStore, tmp_path: Path
) -> None:
    records = {
        project: store.write(
            project_id=project,
            entity_type="Record",
            payload={"project": project},
            status="open",
        )
        for project in ("project-a", "project-b")
    }
    catalog = ResourceCatalog()
    source = _source(catalog, "veyra.tool.entity.history")
    node = next(
        item for item in source.nodes if item.component_type is ComponentType.TOOL
    )
    runtime = ToolRuntime(catalog, entity_store=store)
    original = runtime._adapters["veyra.runtime.entity.history"]
    barrier = Barrier(2)

    def adapter(**kwargs):
        barrier.wait(timeout=5)
        return original(**kwargs)

    runtime._adapters["veyra.runtime.entity.history"] = adapter

    def execute(project):
        values = {
            "entity_id": records[project]["entity_id"],
            "entity_type": "Record",
            "project_id": "forged",
        }
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
    assert [row["revisions"][0]["data"]["project"] for row in results] == [
        "project-a",
        "project-b",
    ]


def test_composed_persistent_agent_pins_history_and_exposes_constraints() -> None:
    from tests.integration.local.test_agent_state_apply import _product

    product = _product()
    assert "veyra.tool.entity.history" in product.source.permissions.tools
    descriptor = ResourceCatalog().detail("veyra.tool.entity.history", "1.0.0")
    assert product.source.lock[descriptor["reference"]] == descriptor["content_hash"]


def test_revision_requirement_binds_history_without_adding_a_model_capability() -> None:
    structure = plan_task_structure(
        "帮我管理客户线索，每个客户有状态，以后更新阶段和备注并保存修改记录。"
    ).structure
    assert structure is not None and structure.state is not None
    plan = compile_execution_plan(structure)
    requirements = derive_plan_capabilities(plan)
    request = next(item for item in requirements if item.capability == "entity_history")
    assert request.model_capability is None and request.side_effect == "read"
    assert all(
        "entity_history" not in item.required
        for item in derive_model_requirements(structure, plan)
    )
    no_revision = replace(plan, state=replace(plan.state, revision=False))
    assert "entity_history" not in {
        item.capability for item in derive_plan_capabilities(no_revision)
    }
