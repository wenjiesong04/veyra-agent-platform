from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from veyra_agent_platform.local.projects import ProjectService
from veyra_agent_platform.local.state.entity_store import EntityStore, EntityStoreError
from veyra_agent_platform.local.storage import LocalRepository
from veyra_agent_platform.local.storage.bootstrap import (
    HEAD_REVISION,
    migrate_local_database,
)


def test_entity_store_writes_revision_events(tmp_path: Path) -> None:
    database = tmp_path / "db.sqlite3"
    store = EntityStore(database)
    migrate_local_database(database)
    project_id = "project-1"
    store.define_type(project_id, "SecondhandItem", {"entity": "SecondhandItem"})
    created = store.write(
        project_id=project_id,
        entity_type="SecondhandItem",
        payload={"title": "lamp", "current_price": 20},
        status="pricing",
    )
    assert created["revision"] == 1
    updated = store.write(
        project_id=project_id,
        entity_type="SecondhandItem",
        payload={"title": "lamp", "current_price": 25},
        status="awaiting_approval",
        entity_id=created["entity_id"],
    )
    assert updated["revision"] == 2
    loaded = store.read(project_id, created["entity_id"])
    assert loaded is not None
    assert loaded["payload"]["current_price"] == 25
    assert loaded["status"] == "awaiting_approval"
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM project_entities WHERE entity_type = 'SecondhandItem'"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM entity_events WHERE entity_id = ?",
            (created["entity_id"],),
        ).fetchone() == (2,)


def test_entity_store_rejects_cross_project_or_type_overwrite(tmp_path: Path) -> None:
    database = tmp_path / "db.sqlite3"
    migrate_local_database(database)
    store = EntityStore(database)
    created = store.write(
        project_id="project-a",
        entity_type="Ticket",
        payload={"title": "a"},
        status="active",
    )
    for project_id, entity_type in (("project-b", "Ticket"), ("project-a", "Other")):
        with pytest.raises(EntityStoreError) as error:
            store.write(
                project_id=project_id,
                entity_type=entity_type,
                payload={"title": "hijack"},
                status="active",
                entity_id=created["entity_id"],
            )
        assert error.value.code == "entity_scope_conflict"
    assert store.read("project-b", created["entity_id"]) is None
    kept = store.read("project-a", created["entity_id"])
    assert kept is not None
    assert kept["payload"] == {"title": "a"}
    assert kept["revision"] == 1


def test_fresh_database_bootstraps_head_and_round_trips_project_entity(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fresh.sqlite3"
    migrate_local_database(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (HEAD_REVISION,)
    assert HEAD_REVISION == "local_0037_entity_revision_history"
    projects = ProjectService(LocalRepository(database), tmp_path / "objects")
    project = projects.create(root_path=tmp_path / "workspace", name="Fresh Entities")
    project_id = project["project_id"]
    agent = projects.create_agent(project_id=project_id, mode="blank")
    store = EntityStore(database)
    store.define_type(project_id, "Lead", {"fields": {"name": "string"}})
    created = store.write(
        project_id=project_id,
        entity_type="Lead",
        payload={"name": "Ada", "agent_id": agent["agent_id"]},
        status="new",
    )
    loaded = store.read(project_id, created["entity_id"])
    assert loaded is not None
    assert loaded["payload"]["name"] == "Ada"
    assert loaded["revision"] == 1
