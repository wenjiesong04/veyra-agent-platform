"""Explicit human budget continuation on a waiting Run; never approves Tools."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.common import new_uuid7

from .execution_budget import ModelTurnBudget

if TYPE_CHECKING:
    from .service import RuntimeService


def extend_runtime_budget(
    host: RuntimeService,
    row: Any,
    *,
    additional_turns: int | None,
    expected_request_id: str | None,
    scope: str,
    idempotency_key: str,
    digest: str,
    on_resolved: Callable[[Any], None] | None = None,
) -> dict[str, Any]:
    from .service import RuntimeError, _now

    command_id, now = new_uuid7(), _now()
    with host.repository.transaction() as connection:
        replay = host.repository.idempotent_response(
            connection, scope, idempotency_key, digest
        )
        if replay is not None:
            return replay
        current = connection.execute(
            "SELECT * FROM runtime_runs WHERE run_id = ?", (row["run_id"],)
        ).fetchone()
        if current["status"] != "waiting":
            raise RuntimeError(
                "command_not_applicable", "This Run is not waiting for budget"
            )
        pending = host.repository.pending_approval(connection, row["run_id"])
        checkpoint = host.repository.latest_checkpoint(connection, row["run_id"])
        if (
            pending is None
            or checkpoint is None
            or expected_request_id != pending["approval_id"]
        ):
            raise RuntimeError(
                "command_request_changed",
                "The budget request changed; review the current request",
            )
        version = connection.execute(
            "SELECT * FROM agent_versions WHERE version_id = ?", (row["version_id"],)
        ).fetchone()
        if version is None:
            raise RuntimeError("version_missing", "Agent version is unavailable")
        source = AgentSource.from_dict(json.loads(version["source_json"]))
        if source.source_hash != version["source_hash"] or not source.is_loop:
            raise RuntimeError(
                "agent_version_invalid", "Pinned loop version integrity check failed"
            )
        values = json.loads(checkpoint["values_json"])
        state = values.get("$agent_loop")
        if not isinstance(state, dict) or not isinstance(
            state.get("pending_budget"), dict
        ):
            raise RuntimeError("command_not_applicable", "This is not a budget request")
        try:
            budget = ModelTurnBudget.restore(
                source.max_turns, state, host.model.settings
            )
            required = state["pending_budget"]["required_remaining"]
            if type(required) is not int or required < 1:
                raise ValueError("The saved delivery reserve is invalid")
            if (
                type(additional_turns) is not int
                or budget.remaining + additional_turns < required
            ):
                raise ValueError("Additional turns must cover the pending stage")
            budget.extend(additional_turns)
        except ValueError as exc:
            raise RuntimeError("execution_budget_invalid", str(exc)) from exc
        state["budget"] = budget.state()
        state.pop("pending_budget", None)
        state["messages"].append(
            {
                "role": "user",
                "content": (
                    "[Runtime model-turn allowance] The user granted "
                    f"{additional_turns} "
                    f"additional model turns; {budget.remaining} remain. "
                    "This is not money, image-request allowance, or Tool permission. "
                    "Preserve completed effects and all task constraints."
                ),
            }
        )
        identity = host._recovery_identity(row["project_id"], source)
        if state.get("recovery_identity") != identity:
            raise RuntimeError(
                "resume_identity_changed", "Budget checkpoint dependencies changed"
            )
        conversation_id = row["conversation_id"]
        conversation_context = (
            host.conversations.prompt_context(conversation_id)
            if host.conversations and conversation_id
            else ""
        )
        host.repository.remember_response(
            connection, scope, idempotency_key, digest, host._row_payload(current)
        )
        if on_resolved is not None:
            on_resolved(connection)
        host.repository.insert_run_command(
            connection,
            command_id=command_id,
            run_id=row["run_id"],
            command_type="extend_budget",
            status="applied",
            created_at=now,
            applied_at=now,
            payload={
                "request_id": pending["approval_id"],
                "additional_turns": additional_turns,
            },
        )
        host.repository.resolve_approval(
            connection,
            pending["approval_id"],
            status="approved",
            command_id=command_id,
            resolved_at=now,
        )
        # Save the new allowance before scheduling so restart/duplicate commands
        # cannot lose or grant it twice. No Tool approval is inherited.
        host.repository.set_run_status(connection, row["run_id"], status="running")
        checkpoint_id = new_uuid7()
        host.repository.add_run_events(
            connection,
            row["run_id"],
            [
                (
                    "model",
                    "approval.resolved",
                    {
                        "kind": "budget",
                        "decision": "extended",
                        "request_id": pending["approval_id"],
                        "additional_turns": additional_turns,
                    },
                ),
                (
                    "model",
                    "agent.budget_updated",
                    {
                        "budget": budget.snapshot(),
                        "command_id": command_id,
                        "additional_turns": additional_turns,
                    },
                ),
                (
                    "model",
                    "checkpoint.created",
                    {
                        "checkpoint_id": checkpoint_id,
                        "waiting_kind": "execution",
                        "next_node_id": "model",
                    },
                ),
            ],
        )
        host.repository.insert_checkpoint(
            connection,
            checkpoint_id=checkpoint_id,
            run_id=row["run_id"],
            node_id="model",
            waiting_kind="execution",
            created_at=now,
            values={
                "values": values,
                "approved": False,
                "verified": False,
                "conversation_context": conversation_context,
                "identity": identity,
                "sequence": connection.execute(
                    "SELECT MAX(sequence) FROM runtime_run_events WHERE run_id = ?",
                    (row["run_id"],),
                ).fetchone()[0],
            },
        )
        response = host._stored_run_response(
            connection,
            row["run_id"],
            scope=scope,
            idempotency_key=idempotency_key,
            digest=digest,
        )
    host._schedule_execution(
        row["run_id"],
        lambda: host._complete_execution(
            row["project_id"],
            row["run_id"],
            source,
            values,
            start_node=None,
            approved=False,
            scope=scope,
            idempotency_key=idempotency_key,
            digest=digest,
            conversation_id=conversation_id,
            conversation_context=conversation_context,
        ),
    )
    return response
