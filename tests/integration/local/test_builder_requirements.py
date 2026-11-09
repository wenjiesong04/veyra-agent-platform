from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.integration.local.test_builder_conversations import _turn
from tests.integration.local.test_builder_resolution import intent
from tests.integration.local.test_edit_proposal_routes import _target
from tests.integration.local.test_factory_routes import _client, _completion
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.factory.client import KimiCompletion
from veyra_agent_platform.local.factory.service import FactoryError


class IntentCapture:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def models(self) -> tuple[str, ...]:
        return ("kimi-k3",)

    def complete(
        self, messages: object, *, response_format: object = None
    ) -> KimiCompletion:
        del response_format
        assert isinstance(messages, list)
        context = json.loads(messages[1]["content"])
        self.requests.append(context["conversation"])
        return _completion(
            json.dumps(intent(intent="create", create_kind="agent", instruction=""))
        )


def _fail_after_goal(client: Any) -> list[str]:
    goals: list[str] = []

    def generate(project_id: str, session_id: str, **_: Any) -> dict[str, Any]:
        session = client.app.state.factory.get_session(project_id, session_id)
        goals.append(session["messages"][0]["content"])
        raise FactoryError("factory_generation_blocked", "Offline test failure")

    client.app.state.factory.generate = generate
    return goals


def test_full_user_goal_survives_bounded_history_and_repeated_retry(
    tmp_path: Path,
) -> None:
    transport = IntentCapture()
    original = (
        "Build a reconciliation assistant: recognize normal split payments, "
        "report physical source rows, never change the source files, "
        "and ask for business confirmation before saving under reports/."
    )
    amendment = "Keep all the requirements above and include orphan payments."
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        goals = _fail_after_goal(client)
        first = _turn(client, project, content=original).json()
        conversation = first["conversation"]["conversation_id"]
        store = client.app.state.builder_conversations.store
        for index in range(22):
            store.append_message(
                message_id=new_uuid7(),
                conversation_id=conversation,
                sequence=store.next_sequence(conversation),
                role="assistant",
                kind="failure",
                content=f"Previous attempt {index} did not produce a proposal.",
                operation_id=None,
                payload={},
                created_at="2026-01-01T00:00:00Z",
            )
        updated = _turn(
            client, project, conversation_id=conversation, content=amendment
        ).json()
        context = transport.requests[-1]["requirement_context"]
        assert original in context and amendment in context
        assert context.index(original) < context.index(amendment)
        assert original not in [
            row["content"] for row in transport.requests[-1]["history"]
        ]
        assert "Previous attempt" not in context
        assert " ".join(context.split()) == goals[-1]
        operation = updated["operations"][-1]["operation_id"]
        for _ in range(3):
            retried = _turn(
                client, project, conversation_id=conversation, retry_of=operation
            ).json()
            operation = retried["operations"][-1]["operation_id"]
            assert transport.requests[-1]["requirement_context"] == context
            assert goals[-1] == " ".join(context.split())
            stored = store.operation(operation, conversation)
            assert json.loads(stored["input_json"])["requirement_context"] == context
        assert [row["kind"] for row in retried["messages"]].count("user") == 2


def test_retry_older_request_excludes_later_user_changes(tmp_path: Path) -> None:
    transport = IntentCapture()
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        goals = _fail_after_goal(client)
        first = _turn(
            client, project, content="Create a read-only report assistant."
        ).json()
        conversation = first["conversation"]["conversation_id"]
        source = first["operations"][0]["operation_id"]
        _turn(
            client,
            project,
            conversation_id=conversation,
            content="Now add file saving.",
        )
        _turn(client, project, conversation_id=conversation, retry_of=source)
        assert goals[-1] == "Create a read-only report assistant."
        assert transport.requests[-1]["requirement_context"] == goals[-1]
        assert not any(
            "Now add file saving" in row["content"]
            for row in transport.requests[-1]["history"]
        )


def test_legacy_retry_recovers_original_user_turns_not_model_summaries(
    tmp_path: Path,
) -> None:
    transport = IntentCapture()
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        goals = _fail_after_goal(client)
        first = _turn(
            client, project, content="Preserve source data and ask before writing."
        ).json()
        conversation = first["conversation"]["conversation_id"]
        updated = _turn(
            client,
            project,
            conversation_id=conversation,
            content="Regenerate using the complete requirements above.",
        ).json()
        source = updated["operations"][-1]["operation_id"]
        with client.app.state.repository.transaction() as connection:
            for operation in updated["operations"]:
                row = connection.execute(
                    "SELECT input_json FROM builder_operations WHERE operation_id=?",
                    (operation["operation_id"],),
                ).fetchone()
                payload = json.loads(row["input_json"])
                payload.pop("requirement_context")
                connection.execute(
                    "UPDATE builder_operations SET input_json=? WHERE operation_id=?",
                    (json.dumps(payload), operation["operation_id"]),
                )
        _turn(
            client,
            project,
            conversation_id=conversation,
            content="A later unrelated task.",
        )
        retried = _turn(
            client, project, conversation_id=conversation, retry_of=source
        ).json()
        assert retried["operations"][-1]["status"] == "failed"
        assert "Preserve source data and ask before writing." in goals[-1]
        assert "Regenerate using the complete requirements above." in goals[-1]
        assert "A later unrelated task." not in goals[-1]
