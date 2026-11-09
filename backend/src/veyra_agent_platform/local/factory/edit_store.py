"""Proposal snapshots and durable Draft-write receipts share local SQLite."""

from __future__ import annotations

import json
from typing import Any

from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.local.storage.repositories import LocalRepository


class EditProposalStore:
    def __init__(self, repository: LocalRepository) -> None:
        self.repository = repository

    def create(self, proposal: dict[str, Any]) -> None:
        with self.repository.transaction() as connection:
            self.create_in_connection(connection, proposal)

    @staticmethod
    def create_in_connection(connection: Any, proposal: dict[str, Any]) -> None:
        connection.execute(
            """INSERT INTO edit_proposals(
               proposal_id, project_id, target_kind, target_id, payload_json,
               builder_creation_operation_id, factory_session_id
               ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                proposal["proposal_id"],
                proposal["project_id"],
                proposal["target_kind"],
                proposal["target_id"],
                json.dumps(proposal, ensure_ascii=False, sort_keys=True),
                proposal.get("builder_creation_operation_id"),
                proposal.get("factory_session_id"),
            ),
        )

    def builder_operation(
        self, project_id: str, operation_id: str
    ) -> dict[str, Any] | None:
        with self.repository.transaction() as connection:
            row = connection.execute(
                """SELECT * FROM edit_proposals
                   WHERE project_id = ? AND builder_creation_operation_id = ?""",
                (project_id, operation_id),
            ).fetchone()
            return self._payload(dict(row)) if row else None

    def list(
        self,
        project_id: str,
        target_kind: str,
        target_id: str,
        *,
        excluded_proposal_kinds: tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        with self.repository.transaction() as connection:
            rows = connection.execute(
                """SELECT * FROM edit_proposals WHERE project_id = ?
                   AND target_kind = ? AND target_id = ?
                   ORDER BY proposal_id DESC""",
                (project_id, target_kind, target_id),
            )
            proposals = []
            for row in rows:
                payload = self._payload(dict(row))
                if payload.get("proposal_kind") in excluded_proposal_kinds:
                    continue
                proposals.append(payload)
                if len(proposals) == 20:
                    break
            return proposals

    def get(self, project_id: str, proposal_id: str) -> dict[str, Any] | None:
        with self.repository.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM edit_proposals WHERE project_id = ? AND proposal_id = ?",
                (project_id, proposal_id),
            ).fetchone()
            return self._payload(dict(row)) if row else None

    @staticmethod
    def _payload(row: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = json.loads(row["payload_json"])
        applied_agent_id = row.get("applied_agent_id")
        if applied_agent_id:
            payload["state"] = "applied"
            payload["applied_agent_id"] = applied_agent_id
            if row.get("applied_json"):
                payload["applied_result"] = json.loads(row["applied_json"])
        else:
            payload["state"] = "rejected" if row["rejected"] else "review"
        return payload

    def reject(self, proposal_id: str) -> None:
        with self.repository.transaction() as connection:
            connection.execute(
                "UPDATE edit_proposals SET rejected = 1 WHERE proposal_id = ?",
                (proposal_id,),
            )

    def mark_applied(
        self, proposal_id: str, agent_id: str, result: dict[str, Any]
    ) -> None:
        with self.repository.transaction() as connection:
            connection.execute(
                """UPDATE edit_proposals
                   SET applied_agent_id = ?, applied_json = ?
                   WHERE proposal_id = ? AND rejected = 0""",
                (
                    agent_id,
                    json.dumps(result, ensure_ascii=False, sort_keys=True),
                    proposal_id,
                ),
            )

    def receipt(self, proposal: dict[str, Any], *, undo: bool = False) -> Any:
        if proposal.get("proposal_kind") == "create_custom_component":
            return None
        prefix = "workflow-draft" if proposal["target_kind"] == "workflow" else "draft"
        scope = f"{prefix}:{proposal['project_id']}:{proposal['target_id']}"
        key = (
            proposal["undo_key"]
            if undo
            else proposal.get("apply_key", proposal["proposal_id"])
        )
        with self.repository.transaction() as connection:
            row = connection.execute(
                "SELECT request_digest, response_json FROM idempotency_records "
                "WHERE scope = ? AND key = ?",
                (scope, key),
            ).fetchone()
        # The Draft writer commits the receipt atomically with the source revision.
        # Deriving state from it avoids a second, crash-sensitive 'applied' write.
        if row is None:
            return None
        base = (
            self.receipt(proposal)
            if undo
            else {"revision": proposal["base_revision"], "etag": proposal["base_etag"]}
        )
        if base is None or row["request_digest"] != sha256_digest(
            {
                "source": proposal["previous_source" if undo else "candidate_source"],
                "revision": base["revision"],
                "etag": base["etag"],
            }
        ):
            return None
        return json.loads(row["response_json"])
