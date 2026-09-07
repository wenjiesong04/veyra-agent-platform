"""Durable Workflow execution state; portable definitions remain unchanged."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.storage.repositories import LocalRepository


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class WorkflowRunStore:
    def __init__(self, repository: LocalRepository) -> None:
        self.repository = repository

    def row(self, run_id: str) -> Any:
        with self.repository._connect() as connection:
            return connection.execute(
                "SELECT * FROM workflow_runs WHERE run_id = ?", (run_id,)
            ).fetchone()

    def event(
        self,
        connection: Any,
        run_id: str,
        node_id: str | None,
        kind: str,
        payload: dict[str, Any],
    ) -> None:
        sequence = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM "
            "workflow_run_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO workflow_run_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                sequence,
                node_id,
                kind,
                json.dumps(payload),
                utc_now(),
                new_uuid7(),
            ),
        )

    def events(self, run_id: str, after: int = 0) -> list[dict[str, Any]]:
        with self.repository._connect() as connection:
            return [
                {
                    "schema_version": "1.0",
                    "event_id": row["event_id"],
                    "run_id": run_id,
                    "sequence": row["sequence"],
                    "node_id": row["node_id"],
                    "kind": row["kind"],
                    "payload": json.loads(row["payload_json"]),
                    "timestamp": row["created_at"],
                }
                for row in connection.execute(
                    "SELECT * FROM workflow_run_events WHERE run_id = ? AND "
                    "sequence > ? ORDER BY sequence",
                    (run_id, after),
                )
            ]

    def calls(self, run_id: str) -> list[dict[str, Any]]:
        with self.repository._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT c.*, r.status FROM workflow_run_calls c LEFT JOIN "
                    "runtime_runs r ON c.child_run_id = r.run_id WHERE c.run_id "
                    "= ? ORDER BY c.rowid",
                    (run_id,),
                )
            ]

    def detail(self, run_id: str) -> dict[str, Any]:
        row = self.row(run_id)
        return {
            "schema_version": "1.0",
            **{
                key: row[key]
                for key in (
                    "run_id",
                    "project_id",
                    "workflow_id",
                    "version_id",
                    "status",
                    "created_at",
                    "finished_at",
                )
            },
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": json.loads(row["error_json"]) if row["error_json"] else None,
            "waiting": json.loads(row["context_json"]).get("waiting"),
            "children": [
                {key: value for key, value in child.items() if key != "dispatch_key"}
                for child in self.calls(run_id)
            ],
            "events": self.events(run_id),
        }

    def interrupt_orphans(self) -> None:
        with self.repository.transaction() as connection:
            rows = connection.execute(
                "SELECT run_id FROM workflow_runs WHERE status = 'running'"
            ).fetchall()
            for row in rows:
                connection.execute(
                    "UPDATE workflow_runs SET status = 'interrupted', "
                    "finished_at = ?, error_json = ? WHERE run_id = ?",
                    (
                        utc_now(),
                        json.dumps(
                            {
                                "code": "runtime_interrupted",
                                "message": (
                                    "Workflow execution was interrupted; "
                                    "no effects were replayed."
                                ),
                            }
                        ),
                        row["run_id"],
                    ),
                )
                self.event(connection, row["run_id"], None, "run.interrupted", {})
