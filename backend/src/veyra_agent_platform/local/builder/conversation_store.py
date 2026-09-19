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
                    "SELECT * FROM builder_conversations WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    """SELECT * FROM builder_conversations
                       WHERE conversation_id = ? AND project_id = ?""",
                    (conversation_id, project_id),
                ).fetchone()
            return dict(row) if row is not None else None

    def conversations(self, project_id: str, *, limit: int) -> list[dict[str, Any]]:
        with self.repository.transaction() as connection:
            rows = connection.execute(
                """SELECT * FROM builder_conversations
                   WHERE project_id = ?
                   ORDER BY last_activity_at DESC, conversation_id DESC
                   LIMIT ?""",
                (project_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]

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
