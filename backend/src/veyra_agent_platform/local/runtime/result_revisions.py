"""Explicit reuse of a previous result, never an implicit execution replay."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from typing import Any

from veyra_agent_platform.contracts.canonical import sha256_digest


class ResultRevisionError(ValueError):
    pass


def previous_result_base(
    connection: sqlite3.Connection,
    project_id: str,
    agent_id: str,
    version_id: str | None,
    messages: Sequence[sqlite3.Row],
) -> dict[str, Any] | None:
    previous = next(
        (row["run_id"] for row in reversed(messages) if row["role"] == "assistant"),
        None,
    )
    if not previous or not version_id:
        return None
    row = connection.execute(
        "SELECT r.run_id, r.result_json FROM runtime_runs r "
        "JOIN agent_versions v ON v.version_id=r.version_id "
        "WHERE r.run_id=? AND r.project_id=? AND r.agent_id=? AND r.version_id=? "
        "AND r.status IN ('verified', 'unverified') AND v.committed=1",
        (previous, project_id, agent_id, version_id),
    ).fetchone()
    if row is None or not row["result_json"]:
        return None
    result = json.loads(row["result_json"])
    if not isinstance(result, dict):
        return None
    return {
        "run_id": row["run_id"],
        "version_id": version_id,
        "result_hash": sha256_digest(result),
    }


def revision_base_outputs(
    repository: Any,
    project_id: str,
    agent_id: str,
    run_id: str,
    base_run_id: Any,
) -> dict[str, Any]:
    if not isinstance(base_run_id, str) or not base_run_id:
        raise ResultRevisionError("base_run_id must identify the available result base")
    current = repository.run(run_id)
    base = repository.run(base_run_id)
    if current is None or base is None or current["project_id"] != project_id:
        raise ResultRevisionError("Result revision base is unavailable")
    if (
        not current["version_id"]
        or not current["conversation_id"]
        or current["agent_id"] != agent_id
        or base["status"] not in {"verified", "unverified"}
        or not base["result_json"]
        or any(
            current[key] != base[key]
            for key in ("project_id", "agent_id", "version_id", "conversation_id")
        )
    ):
        raise ResultRevisionError(
            "Result revision requires the same committed version and conversation"
        )
    version = repository.version(current["version_id"])
    if version is None or not int(version["committed"] or 0):
        raise ResultRevisionError("Result revision requires a committed version")
    messages = repository.agent_conversation_messages(current["conversation_id"])
    boundary = _turn_boundary(repository, current, messages)
    previous = next(
        (
            row["run_id"]
            for row in reversed(messages)
            if boundary is not None
            and row["sequence"] < boundary
            and row["role"] == "assistant"
        ),
        None,
    )
    if previous != base_run_id:
        raise ResultRevisionError("Only the preceding result can be a revision base")
    result = json.loads(base["result_json"])
    if not isinstance(result, dict):
        raise ResultRevisionError("Result revision base has no structured outputs")
    return result


def _turn_boundary(repository: Any, current: Any, messages: Any) -> int | None:
    """Recovery keeps the originating user turn, not a later conversation turn."""
    origin = current
    seen = set()
    while origin["run_id"] not in seen:
        seen.add(origin["run_id"])
        created: dict[str, Any] = next(
            (
                event["payload"]
                for event in repository.run_events(origin["run_id"])
                if event["kind"] == "run.created"
            ),
            {},
        )
        parent_id = created.get("resume_of_run_id") or created.get("retry_of_run_id")
        if not isinstance(parent_id, str):
            boundary = next(
                (
                    row["sequence"]
                    for row in messages
                    if row["run_id"] == origin["run_id"] and row["role"] == "user"
                ),
                None,
            )
            return int(boundary) if boundary is not None else None
        parent = repository.run(parent_id)
        if parent is None or any(
            current[key] != parent[key]
            for key in ("project_id", "agent_id", "version_id", "conversation_id")
        ):
            return None
        origin = parent
    return None
