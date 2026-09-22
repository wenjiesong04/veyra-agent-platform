"""Project-scoped Builder conversation rows live in local SQLite, not Project files."""

from __future__ import annotations

import json
from typing import Any

from veyra_agent_platform.local.builder.operation_events import (
    EVENT_KINDS,
    TERMINAL_EVENT_KINDS,
)
from veyra_agent_platform.local.storage.repositories import LocalRepository

_EMPTY_OBJECT = "{}"


class BuilderConversationStore:
    def __init__(self, repository: LocalRepository) -> None:
        self.repository = repository

    def create_conversation(
        self,
        *,
        conversation_id: str,
        project_id: str,
        title: str,
        created_at: str,
    ) -> None:
        with self.repository.transaction() as connection:
            self._insert_conversation(
                connection,
                conversation_id=conversation_id,
                project_id=project_id,
                title=title,
                created_at=created_at,
            )

    def commit_user_turn(
        self,
        *,
        conversation_id: str,
        project_id: str,
        title: str,
        create_conversation: bool,
        operation_id: str,
        kind: str,
        retry_of: str | None,
        input_payload: dict[str, str],
        message_id: str | None,
        content: str | None,
        created_at: str,
    ) -> None:
        with self.repository.transaction() as connection:
            if create_conversation:
                self._insert_conversation(
                    connection,
                    conversation_id=conversation_id,
                    project_id=project_id,
                    title=title,
                    created_at=created_at,
                )
            connection.execute(
                """INSERT INTO builder_operations(
                    operation_id, conversation_id, kind, status, retry_of,
                    input_json, error_code, diagnostic_json, proposal_id,
                    run_id, factory_session_id, created_at, updated_at
                ) VALUES (
                    ?, ?, ?, 'in_progress', ?, ?, NULL, '{}',
                    NULL, NULL, NULL, ?, ?
                )""",
                (
                    operation_id,
                    conversation_id,
                    kind,
                    retry_of,
                    json.dumps(input_payload, ensure_ascii=False, sort_keys=True),
                    created_at,
                    created_at,
                ),
            )
            if message_id and content:
                sequence_row = connection.execute(
                    """SELECT COALESCE(MAX(sequence), -1) AS last
                       FROM builder_messages WHERE conversation_id = ?""",
                    (conversation_id,),
                ).fetchone()
                last = int(sequence_row["last"]) if sequence_row is not None else -1
                sequence = last + 1
                connection.execute(
                    """INSERT INTO builder_messages(
                        message_id, conversation_id, sequence, role, kind, content,
                        operation_id, payload_json, created_at
                    ) VALUES (?, ?, ?, 'user', 'user', ?, ?, '{}', ?)""",
                    (
                        message_id,
                        conversation_id,
                        sequence,
                        content,
                        operation_id,
                        created_at,
                    ),
                )
            connection.execute(
                """UPDATE builder_conversations
                   SET updated_at = ?, last_activity_at = ?
                   WHERE conversation_id = ?""",
                (created_at, created_at, conversation_id),
            )

    @staticmethod
    def _insert_conversation(
        connection: Any,
        *,
        conversation_id: str,
        project_id: str,
        title: str,
        created_at: str,
    ) -> None:
        connection.execute(
            """INSERT INTO builder_conversations(
                conversation_id, project_id, title, status,
                created_at, updated_at, last_activity_at
            ) VALUES (?, ?, ?, 'active', ?, ?, ?)""",
            (
                conversation_id,
                project_id,
                title,
                created_at,
                created_at,
                created_at,
            ),
        )

    def conversation(
        self, conversation_id: str, project_id: str | None = None
    ) -> dict[str, Any] | None:
        with self.repository.transaction() as connection:
            if project_id is None:
                row = connection.execute(
                    """SELECT * FROM builder_conversations
                       WHERE conversation_id = ? AND removed_at IS NULL""",
                    (conversation_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    """SELECT * FROM builder_conversations
                       WHERE conversation_id = ? AND project_id = ?
                         AND removed_at IS NULL""",
                    (conversation_id, project_id),
                ).fetchone()
            return dict(row) if row is not None else None

    def conversations(
        self, project_id: str | None = None, *, limit: int | None = None
    ) -> list[dict[str, Any]]:
        with self.repository.transaction() as connection:
            clauses = ["removed_at IS NULL"]
            params: list[Any] = []
            if project_id:
                clauses.append("project_id = ?")
                params.append(project_id)
            sql = f"""SELECT * FROM builder_conversations
                   WHERE {" AND ".join(clauses)}
                   ORDER BY last_activity_at DESC, conversation_id DESC"""
            if limit is not None:
                sql += " LIMIT ?"
                params.append(limit)
            rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def delete_conversation(
        self, conversation_id: str, project_id: str, *, removed_at: str
    ) -> bool:
        with self.repository.transaction() as connection:
            row = connection.execute(
                """SELECT conversation_id FROM builder_conversations
                   WHERE conversation_id = ? AND project_id = ?
                     AND removed_at IS NULL""",
                (conversation_id, project_id),
            ).fetchone()
            if row is None:
                return False
            connection.execute(
                """UPDATE builder_conversations
                   SET removed_at = ?, status = 'deleted', updated_at = ?
                   WHERE conversation_id = ? AND project_id = ?
                     AND removed_at IS NULL""",
                (removed_at, removed_at, conversation_id, project_id),
            )
            return True

    def trashed_conversations(self) -> list[dict[str, Any]]:
        with self.repository.transaction() as connection:
            rows = connection.execute(
                """SELECT conversations.conversation_id AS id,
                          conversations.title AS name,
                          conversations.project_id AS project_id,
                          conversations.removed_at AS removed_at,
                          projects.name AS project_name,
                          projects.removed_at AS project_removed_at
                   FROM builder_conversations AS conversations
                   LEFT JOIN projects
                     ON projects.project_id = conversations.project_id
                   WHERE conversations.removed_at IS NOT NULL
                   ORDER BY conversations.removed_at DESC,
                            conversations.conversation_id DESC"""
            ).fetchall()
            return [dict(row) for row in rows]

    def restore_trashed(self, conversation_id: str, *, restored_at: str) -> bool:
        with self.repository.transaction() as connection:
            row = connection.execute(
                """SELECT conversation_id FROM builder_conversations
                   WHERE conversation_id = ? AND removed_at IS NOT NULL""",
                (conversation_id,),
            ).fetchone()
            if row is None:
                return False
            cursor = connection.execute(
                """UPDATE builder_conversations
                   SET removed_at = NULL, status = 'active', updated_at = ?
                   WHERE conversation_id = ? AND removed_at IS NOT NULL""",
                (restored_at, conversation_id),
            )
            return cursor.rowcount == 1

    def purge_trashed(self, conversation_id: str) -> bool:
        with self.repository.transaction() as connection:
            row = connection.execute(
                """SELECT conversation_id FROM builder_conversations
                   WHERE conversation_id = ? AND removed_at IS NOT NULL""",
                (conversation_id,),
            ).fetchone()
            if row is None:
                return False
            connection.execute(
                """UPDATE builder_operations SET retry_of = NULL
                   WHERE conversation_id = ?""",
                (conversation_id,),
            )
            connection.execute(
                """DELETE FROM builder_harness_receipts
                   WHERE conversation_id = ?""",
                (conversation_id,),
            )
            connection.execute(
                """DELETE FROM builder_operation_events
                   WHERE operation_id IN (
                     SELECT operation_id FROM builder_operations
                     WHERE conversation_id = ?
                   )""",
                (conversation_id,),
            )
            connection.execute(
                """UPDATE builder_messages SET operation_id = NULL
                   WHERE conversation_id = ?""",
                (conversation_id,),
            )
            connection.execute(
                "DELETE FROM builder_operations WHERE conversation_id = ?",
                (conversation_id,),
            )
            connection.execute(
                "DELETE FROM builder_messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            connection.execute(
                "DELETE FROM builder_conversations WHERE conversation_id = ?",
                (conversation_id,),
            )
            return True

    def touch(
        self, conversation_id: str, *, title: str | None, updated_at: str
    ) -> None:
        with self.repository.transaction() as connection:
            if title is None:
                connection.execute(
                    """UPDATE builder_conversations
                       SET updated_at = ?, last_activity_at = ?
                       WHERE conversation_id = ?""",
                    (updated_at, updated_at, conversation_id),
                )
                return
            connection.execute(
                """UPDATE builder_conversations
                   SET title = ?, updated_at = ?, last_activity_at = ?
                   WHERE conversation_id = ?""",
                (title, updated_at, updated_at, conversation_id),
            )

    def create_operation(
        self,
        *,
        operation_id: str,
        conversation_id: str,
        kind: str,
        retry_of: str | None,
        input_payload: dict[str, str],
        created_at: str,
    ) -> None:
        with self.repository.transaction() as connection:
            connection.execute(
                """INSERT INTO builder_operations(
                    operation_id, conversation_id, kind, status, retry_of,
                    input_json, error_code, diagnostic_json, proposal_id,
                    run_id, factory_session_id, created_at, updated_at
                ) VALUES (
                    ?, ?, ?, 'in_progress', ?, ?, NULL, ?,
                    NULL, NULL, NULL, ?, ?
                )""",
                (
                    operation_id,
                    conversation_id,
                    kind,
                    retry_of,
                    json.dumps(input_payload, ensure_ascii=False, sort_keys=True),
                    _EMPTY_OBJECT,
                    created_at,
                    created_at,
                ),
            )

    def operation(
        self, operation_id: str, conversation_id: str | None = None
    ) -> dict[str, Any] | None:
        with self.repository.transaction() as connection:
            if conversation_id is None:
                row = connection.execute(
                    "SELECT * FROM builder_operations WHERE operation_id = ?",
                    (operation_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    """SELECT * FROM builder_operations
                       WHERE operation_id = ? AND conversation_id = ?""",
                    (operation_id, conversation_id),
                ).fetchone()
            return dict(row) if row is not None else None

    def operations(self, conversation_id: str) -> list[dict[str, Any]]:
        with self.repository.transaction() as connection:
            rows = connection.execute(
                """SELECT * FROM builder_operations
                   WHERE conversation_id = ?
                   ORDER BY created_at ASC, operation_id ASC""",
                (conversation_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def latest_operation(self, conversation_id: str) -> dict[str, Any] | None:
        with self.repository.transaction() as connection:
            row = connection.execute(
                """SELECT * FROM builder_operations
                   WHERE conversation_id = ?
                   ORDER BY created_at DESC, operation_id DESC
                   LIMIT 1""",
                (conversation_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def update_operation(
        self,
        operation_id: str,
        *,
        status: str,
        updated_at: str,
        error_code: str | None = None,
        diagnostic: dict[str, str] | None = None,
        proposal_id: str | None = None,
        run_id: str | None = None,
        factory_session_id: str | None = None,
        kind: str | None = None,
    ) -> None:
        assignments = ["status = ?", "updated_at = ?"]
        values: list[Any] = [status, updated_at]
        if error_code is not None:
            assignments.append("error_code = ?")
            values.append(error_code)
        if diagnostic is not None:
            assignments.append("diagnostic_json = ?")
            values.append(json.dumps(diagnostic, ensure_ascii=False, sort_keys=True))
        if proposal_id is not None:
            assignments.append("proposal_id = ?")
            values.append(proposal_id)
        if run_id is not None:
            assignments.append("run_id = ?")
            values.append(run_id)
        if factory_session_id is not None:
            assignments.append("factory_session_id = ?")
            values.append(factory_session_id)
        if kind is not None:
            assignments.append("kind = ?")
            values.append(kind)
        values.append(operation_id)
        with self.repository.transaction() as connection:
            connection.execute(
                f"UPDATE builder_operations SET {', '.join(assignments)} "
                "WHERE operation_id = ?",
                tuple(values),
            )

    def next_sequence(self, conversation_id: str) -> int:
        with self.repository.transaction() as connection:
            row = connection.execute(
                """SELECT COALESCE(MAX(sequence), -1) AS last
                   FROM builder_messages WHERE conversation_id = ?""",
                (conversation_id,),
            ).fetchone()
            last = int(row["last"]) if row is not None else -1
            return last + 1

    def append_message(
        self,
        *,
        message_id: str,
        conversation_id: str,
        sequence: int,
        role: str,
        kind: str,
        content: str,
        operation_id: str | None,
        payload: dict[str, str],
        created_at: str,
    ) -> None:
        with self.repository.transaction() as connection:
            connection.execute(
                """INSERT INTO builder_messages(
                    message_id, conversation_id, sequence, role, kind, content,
                    operation_id, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    message_id,
                    conversation_id,
                    sequence,
                    role,
                    kind,
                    content,
                    operation_id,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    created_at,
                ),
            )
            connection.execute(
                """UPDATE builder_conversations
                   SET updated_at = ?, last_activity_at = ?
                   WHERE conversation_id = ?""",
                (created_at, created_at, conversation_id),
            )

    def messages(self, conversation_id: str) -> list[dict[str, Any]]:
        with self.repository.transaction() as connection:
            rows = connection.execute(
                """SELECT * FROM builder_messages
                   WHERE conversation_id = ?
                   ORDER BY sequence ASC, message_id ASC""",
                (conversation_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def events(self, operation_id: str) -> list[dict[str, Any]]:
        with self.repository.transaction() as connection:
            rows = connection.execute(
                """SELECT * FROM builder_operation_events
                   WHERE operation_id = ?
                   ORDER BY sequence ASC, event_id ASC""",
                (operation_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def append_event(
        self,
        *,
        event_id: str,
        operation_id: str,
        kind: str,
        label: str,
        summary: str,
        facts: dict[str, str],
        created_at: str,
    ) -> dict[str, Any]:
        if kind not in EVENT_KINDS:
            raise ValueError("unknown Builder operation event")
        with self.repository.transaction() as connection:
            operation = connection.execute(
                "SELECT status FROM builder_operations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if operation is None:
                raise ValueError("unknown Builder operation")
            last = connection.execute(
                """SELECT kind FROM builder_operation_events
                   WHERE operation_id = ?
                   ORDER BY sequence DESC, event_id DESC
                   LIMIT 1""",
                (operation_id,),
            ).fetchone()
            if last is not None and last["kind"] in TERMINAL_EVENT_KINDS:
                raise ValueError("completed Builder operation is immutable")
            sequence_row = connection.execute(
                """SELECT COALESCE(MAX(sequence), -1) AS last
                   FROM builder_operation_events WHERE operation_id = ?""",
                (operation_id,),
            ).fetchone()
            last_sequence = (
                int(sequence_row["last"]) if sequence_row is not None else -1
            )
            sequence = last_sequence + 1
            payload = json.dumps(facts, ensure_ascii=False, sort_keys=True)
            connection.execute(
                """INSERT INTO builder_operation_events(
                    event_id, operation_id, sequence, kind, label, summary,
                    facts_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id,
                    operation_id,
                    sequence,
                    kind,
                    label,
                    summary,
                    payload,
                    created_at,
                ),
            )
            connection.execute(
                """UPDATE builder_operations SET updated_at = ?
                   WHERE operation_id = ?""",
                (created_at, operation_id),
            )
            return {
                "event_id": event_id,
                "operation_id": operation_id,
                "sequence": sequence,
                "kind": kind,
                "label": label,
                "summary": summary,
                "facts_json": payload,
                "created_at": created_at,
            }

    def next_receipt_sequence(self, operation_id: str) -> int:
        with self.repository.transaction() as connection:
            row = connection.execute(
                """SELECT COALESCE(MAX(sequence), -1) AS last
                   FROM builder_harness_receipts WHERE operation_id = ?""",
                (operation_id,),
            ).fetchone()
            last = int(row["last"]) if row is not None else -1
            return last + 1

    def insert_receipt(self, payload: dict[str, Any]) -> None:
        included = json.dumps(
            payload["included_categories"], ensure_ascii=False, sort_keys=True
        )
        excluded = json.dumps(
            payload["excluded_categories"], ensure_ascii=False, sort_keys=True
        )
        with self.repository.transaction() as connection:
            connection.execute(
                """INSERT INTO builder_harness_receipts(
                    receipt_id, operation_id, conversation_id, project_id,
                    invocation_kind, sequence, status, started_at, completed_at,
                    harness_mode, policy_version, policy_hash, output_contract,
                    schema_version, schema_hash, structured_mode,
                    project_snapshot_hash, catalog_snapshot_hash,
                    included_categories_json, excluded_categories_json,
                    history_message_count, context_size_bytes, request_size_bytes,
                    provider_id, model, endpoint_kind, provider_profile_status,
                    provider_profile_source, schema_profile, failure_stage,
                    error_code, safe_provider_error_type, safe_provider_error_param,
                    provider_request_id, fallback_from, fallback_to,
                    created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )""",
                (
                    payload["receipt_id"],
                    payload["operation_id"],
                    payload["conversation_id"],
                    payload["project_id"],
                    payload["invocation_kind"],
                    int(payload["sequence"]),
                    payload["status"],
                    payload["started_at"],
                    payload.get("completed_at"),
                    payload["harness_mode"],
                    payload["policy_version"],
                    payload["policy_hash"],
                    payload["output_contract"],
                    payload["schema_version"],
                    payload["schema_hash"],
                    payload["structured_mode"],
                    payload["project_snapshot_hash"],
                    payload["catalog_snapshot_hash"],
                    included,
                    excluded,
                    int(payload["history_message_count"]),
                    int(payload["context_size_bytes"]),
                    int(payload["request_size_bytes"]),
                    payload["provider_id"],
                    payload["model"],
                    payload["endpoint_kind"],
                    payload["provider_profile_status"],
                    payload["provider_profile_source"],
                    payload["schema_profile"],
                    payload.get("failure_stage"),
                    payload.get("error_code"),
                    payload.get("safe_provider_error_type"),
                    payload.get("safe_provider_error_param"),
                    payload.get("provider_request_id"),
                    payload.get("fallback_from"),
                    payload.get("fallback_to"),
                    payload["created_at"],
                    payload["updated_at"],
                ),
            )

    def receipts(
        self,
        *,
        project_id: str,
        conversation_id: str,
        operation_id: str,
    ) -> list[dict[str, Any]]:
        with self.repository.transaction() as connection:
            rows = connection.execute(
                """SELECT receipts.*
                   FROM builder_harness_receipts AS receipts
                   JOIN builder_conversations AS conversations
                     ON conversations.conversation_id = receipts.conversation_id
                   JOIN builder_operations AS operations
                     ON operations.operation_id = receipts.operation_id
                   WHERE receipts.project_id = ?
                     AND receipts.conversation_id = ?
                     AND receipts.operation_id = ?
                     AND conversations.project_id = ?
                     AND operations.conversation_id = ?
                   ORDER BY receipts.sequence ASC, receipts.receipt_id ASC""",
                (
                    project_id,
                    conversation_id,
                    operation_id,
                    project_id,
                    conversation_id,
                ),
            ).fetchall()
            return [dict(row) for row in rows]

    def receipt(self, receipt_id: str) -> dict[str, Any] | None:
        with self.repository.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM builder_harness_receipts WHERE receipt_id = ?",
                (receipt_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def finalize_receipt(
        self,
        receipt_id: str,
        *,
        status: str,
        completed_at: str,
        failure_stage: str | None = None,
        error_code: str | None = None,
        safe_provider_error_type: str | None = None,
        safe_provider_error_param: str | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        with self.repository.transaction() as connection:
            row = connection.execute(
                """SELECT status FROM builder_harness_receipts
                   WHERE receipt_id = ?""",
                (receipt_id,),
            ).fetchone()
            if row is None:
                raise ValueError("unknown harness receipt")
            if str(row["status"]) != "prepared":
                raise ValueError("completed harness receipt is immutable")
            connection.execute(
                """UPDATE builder_harness_receipts
                   SET status = ?, completed_at = ?, failure_stage = ?,
                       error_code = ?, safe_provider_error_type = ?,
                       safe_provider_error_param = ?, provider_request_id = ?,
                       updated_at = ?
                   WHERE receipt_id = ? AND status = 'prepared'""",
                (
                    status,
                    completed_at,
                    failure_stage,
                    error_code,
                    safe_provider_error_type,
                    safe_provider_error_param,
                    provider_request_id,
                    completed_at,
                    receipt_id,
                ),
            )
