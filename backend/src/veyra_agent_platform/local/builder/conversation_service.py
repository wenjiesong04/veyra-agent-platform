"""Persist Project Builder turns before model calls; failures stay in history."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from veyra_agent_platform.contracts.common import ContractValidationError, new_uuid7
from veyra_agent_platform.contracts.semantic_plan import OperationKind, SemanticField
from veyra_agent_platform.local.builder.component_planning import (
    capability_readiness,
    direct_component_draft_plan,
    matching_existing_component,
)
from veyra_agent_platform.local.builder.conversation_store import (
    BuilderConversationStore,
)
from veyra_agent_platform.local.builder.operation_events import (
    APPLY_COMPLETED,
    APPLY_STARTED,
    COMPONENT_CREATED,
    COMPONENT_DESIGN_COMPLETED,
    COMPONENT_DESIGN_STARTED,
    INTENT_RESOLVED,
    INTENT_STARTED,
    OPERATION_COMPLETED,
    OPERATION_FAILED,
    OPERATION_STARTED,
    PROPOSAL_CONFIRMED,
    PROPOSAL_READY,
    PROPOSAL_REJECTED,
    TEST_COMPLETED,
    TEST_FAILED,
    TEST_STARTED,
    TEST_STOPPED,
    TEST_WAITING_APPROVAL,
    event_label,
)
from veyra_agent_platform.local.builder.receipts import (
    HarnessReceiptRecorder,
    public_receipt,
)
from veyra_agent_platform.local.builder.resolution import (
    BuilderMessage,
    BuilderResolutionService,
    BuilderTarget,
    ResolveRequest,
)
from veyra_agent_platform.local.builder.test_run import (
    not_configured_observation,
    observe_run,
    public_observation,
)
from veyra_agent_platform.local.factory.client import FactoryProviderError
from veyra_agent_platform.local.factory.edit_service import EditProposalService
from veyra_agent_platform.local.factory.service import FactoryError, FactoryService
from veyra_agent_platform.local.library.service import DraftConflict
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService
from veyra_agent_platform.local.runtime.credentials import ProviderCredentialError
from veyra_agent_platform.local.runtime.service import (
    RuntimeError as RuntimeFailure,
)
from veyra_agent_platform.local.runtime.service import RuntimeService

HISTORY_LIMIT = 18
_TITLE_LIMIT = 32
_TITLE_PLACEHOLDER = "Chat"
_CLAUSE_SPLIT = re.compile(r"[。！？!?\n；;，,]")
_TITLE_PREFIXES = tuple(
    sorted(
        (
            "请帮我生成一个",
            "请帮我创建一个",
            "请帮我做一个",
            "请帮我做个",
            "请帮我生成",
            "请帮我创建",
            "请帮我做",
            "帮我生成一个",
            "帮我创建一个",
            "帮我做一个",
            "帮我做个",
            "帮我生成",
            "帮我创建",
            "帮我做",
            "麻烦生成一个",
            "麻烦创建一个",
            "请生成一个",
            "请创建一个",
            "请生成",
            "请创建",
            "生成一个",
            "创建一个",
            "新建一个",
            "做一个",
            "做个",
            "生成",
            "创建",
            "新建",
            "please create an",
            "please create a",
            "please generate an",
            "please generate a",
            "please build an",
            "please build a",
            "please make an",
            "please make a",
            "create an",
            "create a",
            "generate an",
            "generate a",
            "build an",
            "build a",
            "make an",
            "make a",
            "please create",
            "please generate",
            "please build",
            "please make",
            "create",
            "generate",
            "build",
            "make",
        ),
        key=len,
        reverse=True,
    )
)
_SECRET = re.compile(r"(?i)(bearer\s+\S+|sk-[A-Za-z0-9._-]+|moonshot-[A-Za-z0-9._-]+)")
_FORBIDDEN_PAYLOAD_KEYS = {
    "authorization",
    "api_key",
    "secret",
    "prompt",
    "system",
    "raw",
    "body",
    "reasoning",
}
_MESSAGE_KINDS = {
    "user",
    "assistant",
    "plan",
    "clarification",
    "failure",
    "proposal_reference",
    "reject",
    "confirm",
    "apply_summary",
    "validation_summary",
    "result",
}
BUILDER_ACTIVITY_MAX = 200

_RECORD_KINDS = {
    "proposal_reference",
    "reject",
    "confirm",
    "apply_summary",
    "validation_summary",
}
_HISTORY_KINDS = {"user", "assistant", "clarification", "failure", "result"}
_PROVIDER_STAGES = {
    "factory_request_invalid": "semantic_plan",
    "factory_unauthorized": "semantic_plan",
    "factory_rate_limited": "semantic_plan",
    "factory_provider_error": "semantic_plan",
    "factory_timeout": "semantic_plan",
    "factory_unavailable": "semantic_plan",
    "factory_provider_not_configured": "semantic_plan",
    "factory_generation_invalid": "semantic_generation",
    "factory_missing_capability": "semantic_compilation",
    "builder_resolution_invalid": "intent_resolution",
}


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TurnRequest(ClosedModel):
    conversation_id: str | None = Field(default=None, min_length=1, max_length=64)
    content: str | None = Field(default=None, max_length=10_000)
    focus: BuilderTarget | None = None
    locale: Literal["zh", "en"] = "en"
    retry_of: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def require_content_or_retry(self) -> TurnRequest:
        if self.retry_of:
            if not self.conversation_id:
                raise ValueError("retry_of requires conversation_id")
            return self
        if not (self.content or "").strip():
            raise ValueError("content is required")
        return self


class TestRunRequest(ClosedModel):
    agent_id: str | None = Field(default=None, min_length=1, max_length=64)
    workspace_id: str | None = Field(default=None, min_length=1, max_length=128)
    inputs: dict[str, Any] = Field(default_factory=dict)
    locale: Literal["zh", "en"] = "en"


class TestRunCommandRequest(ClosedModel):
    command: Literal["approve", "reject", "stop"]
    locale: Literal["zh", "en"] = "en"


class ComponentProposalCommandRequest(ClosedModel):
    command: Literal["apply", "reject"]
    confirm: StrictBool
    locale: Literal["zh", "en"] = "en"


class AgentCreationProposalCommandRequest(ClosedModel):
    command: Literal["apply", "reject"]
    confirm: StrictBool
    locale: Literal["zh", "en"] = "en"


class RuntimeBindingCommandRequest(ClosedModel):
    credential_id: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=128)
    confirm: StrictBool
    locale: Literal["zh", "en"] = "en"
    credential_scope: Literal["device", "cloud"] = "device"


class TestRepairRequest(ClosedModel):
    locale: Literal["zh", "en"] = "en"


class RecordRequest(ClosedModel):
    kind: Literal[
        "proposal_reference",
        "reject",
        "confirm",
        "apply_summary",
        "validation_summary",
    ]
    content: str = Field(min_length=1, max_length=4_000)
    operation_id: str | None = Field(default=None, min_length=1, max_length=64)
    proposal_id: str | None = Field(default=None, min_length=1, max_length=64)
    details: dict[str, str] = Field(default_factory=dict, max_length=20)


class RenameRequest(ClosedModel):
    title: str = Field(min_length=1, max_length=80)


class BuilderConversationError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class BuilderConversationService:
    def __init__(
        self,
        store: BuilderConversationStore,
        projects: ProjectService,
        resolution: BuilderResolutionService,
        factory: FactoryService,
        *,
        runtime: RuntimeService | None = None,
        edits: EditProposalService | None = None,
        runtime_preflight: bool = True,
    ) -> None:
        self.store = store
        self.projects = projects
        self.resolution = resolution
        self.factory = factory
        self.runtime = runtime
        self.edits = edits
        self.runtime_preflight = runtime_preflight

    def turn(
        self,
        project_id: str,
        request: TurnRequest,
        *,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        on_preview: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        self._require_project(project_id)
        conversation_id, operation_id, content, locale, focus = self._begin(
            project_id, request, on_event=on_event
        )
        resolution: dict[str, Any] | None = None
        factory_session: dict[str, Any] | None = None
        try:
            self._emit(
                operation_id,
                INTENT_STARTED,
                locale,
                on_event=on_event,
            )
            history = self._bounded_history(conversation_id, content)
            receipts = HarnessReceiptRecorder(
                self.store,
                self.factory.harness,
                project_id=project_id,
                conversation_id=conversation_id,
                operation_id=operation_id,
                profile=self.factory.resolved_capability_profile(),
            )
            resolution = self.resolution.resolve(
                project_id,
                ResolveRequest(
                    content=content,
                    history=history,
                    focus=focus,
                    locale=locale,
                ),
                receipts=receipts,
                on_visible=on_preview,
            )
            self._append_resolution(
                conversation_id, operation_id, resolution, locale, on_event=on_event
            )
            if (
                resolution.get("status") == "resolved"
                and resolution.get("intent") == "create"
                and resolution.get("create_kind") in {"agent", "workflow"}
            ):
                if self._requires_runtime_binding(project_id):
                    self._wait_for_runtime_binding(
                        project_id, conversation_id, operation_id, resolution, locale
                    )
                    return self.snapshot(
                        project_id, conversation_id, resolution=resolution
                    )
                factory_session = self._generate_product(
                    project_id,
                    conversation_id,
                    operation_id,
                    resolution,
                    content,
                    locale,
                    on_event=on_event,
                    receipts=receipts,
                )
            elif (
                resolution.get("status") == "resolved"
                and resolution.get("intent") == "create_component"
            ):
                self._create_component_proposal(
                    project_id,
                    conversation_id,
                    operation_id,
                    resolution,
                    locale,
                    on_event=on_event,
                )
            elif (
                resolution.get("status") == "resolved"
                and resolution.get("intent") == "edit"
            ):
                self._complete_operation(operation_id, "waiting")
            else:
                self._emit(operation_id, OPERATION_COMPLETED, locale, on_event=on_event)
                self._complete_operation(operation_id, "succeeded")
        except FactoryProviderError as exc:
            self._fail_operation(
                conversation_id,
                operation_id,
                locale,
                code=exc.code,
                message=str(exc),
                details=dict(exc.details or {}),
                on_event=on_event,
            )
        except FactoryError as exc:
            self._fail_operation(
                conversation_id,
                operation_id,
                locale,
                code=exc.code,
                message=str(exc),
                details={},
                on_event=on_event,
            )
        except (ProjectError, ContractValidationError) as exc:
            code = getattr(exc, "code", "builder_operation_failed")
            self._fail_operation(
                conversation_id,
                operation_id,
                locale,
                code=str(code),
                message=str(exc),
                details={},
                on_event=on_event,
            )
        except Exception:
            self._fail_operation(
                conversation_id,
                operation_id,
                locale,
                code="builder_operation_failed",
                message="Builder could not finish this operation.",
                details={},
                on_event=on_event,
            )
            raise
        return self.snapshot(
            project_id,
            conversation_id,
            resolution=resolution,
            factory_session=factory_session,
        )

    def get(self, project_id: str, conversation_id: str) -> dict[str, Any]:
        self._require_project(project_id)
        return self.snapshot(project_id, conversation_id)

    def rename(
        self, project_id: str, conversation_id: str, request: RenameRequest
    ) -> dict[str, Any]:
        self._require_project(project_id)
        conversation = self.store.conversation(conversation_id, project_id)
        if conversation is None:
            raise BuilderConversationError(
                "builder_conversation_not_found",
                "Builder conversation was not found",
                status_code=404,
            )
        title = _title(request.title)
        if title == _TITLE_PLACEHOLDER:
            raise BuilderConversationError(
                "builder_title_invalid", "Conversation title is required"
            )
        self.store.touch(conversation_id, title=title, updated_at=_now())
        return self.snapshot(project_id, conversation_id)

    def delete(self, project_id: str, conversation_id: str) -> dict[str, Any]:
        self._require_project(project_id)
        if not self.store.delete_conversation(
            conversation_id, project_id, removed_at=_now()
        ):
            raise BuilderConversationError(
                "builder_conversation_not_found",
                "Builder conversation was not found",
                status_code=404,
            )
        return {
            "schema_version": "1.0",
            "conversation_id": conversation_id,
            "deleted": True,
        }

    def list_trashed(self) -> list[dict[str, Any]]:
        return self.store.trashed_conversations()

    def restore_trashed(self, conversation_id: str) -> None:
        trashed = next(
            (
                row
                for row in self.store.trashed_conversations()
                if row["id"] == conversation_id
            ),
            None,
        )
        if trashed is None:
            raise BuilderConversationError(
                "trash_not_found",
                "Builder conversation was not found in Trash",
                status_code=404,
            )
        self._require_project(str(trashed["project_id"]))
        if not self.store.restore_trashed(conversation_id, restored_at=_now()):
            raise BuilderConversationError(
                "trash_not_found",
                "Builder conversation was not found in Trash",
                status_code=404,
            )

    def purge_trashed(self, conversation_id: str) -> None:
        if not self.store.purge_trashed(conversation_id):
            raise BuilderConversationError(
                "trash_not_found",
                "Builder conversation was not found in Trash",
                status_code=404,
            )

    def activity(
        self, project_id: str | None = None, *, limit: int | None = None
    ) -> dict[str, Any]:
        if project_id:
            self._require_project(project_id)
        bound = None if limit is None else max(1, min(limit, BUILDER_ACTIVITY_MAX))
        items: list[dict[str, Any]] = []
        for row in self.store.conversations(project_id, limit=bound):
            latest = self.store.latest_operation(row["conversation_id"])
            items.append(
                {
                    "kind": "conversation",
                    "id": row["conversation_id"],
                    "conversation_id": row["conversation_id"],
                    "project_id": row["project_id"],
                    "title": self._ensure_readable_title(
                        row["conversation_id"], row["title"]
                    ),
                    "status": latest["status"] if latest else "succeeded",
                    "operation_kind": latest["kind"] if latest else "resolve",
                    "occurred_at": row["last_activity_at"],
                }
            )
        return {
            "schema_version": "1.0",
            "project_id": project_id or "",
            "items": items,
        }

    def record(
        self, project_id: str, conversation_id: str, request: RecordRequest
    ) -> dict[str, Any]:
        self._require_project(project_id)
        conversation = self.store.conversation(conversation_id, project_id)
        if conversation is None:
            raise BuilderConversationError(
                "builder_conversation_not_found",
                "Builder conversation was not found",
                status_code=404,
            )
        if request.kind not in _RECORD_KINDS:
            raise BuilderConversationError(
                "builder_record_invalid", "Builder record kind is not supported"
            )
        operation_id = request.operation_id
        operation = None
        if operation_id:
            operation = self.store.operation(operation_id, conversation_id)
            if operation is None:
                raise BuilderConversationError(
                    "builder_operation_not_found",
                    "Builder operation was not found",
                    status_code=404,
                )
            if request.proposal_id:
                if self.edits is None:
                    raise BuilderConversationError(
                        "builder_proposal_unavailable",
                        "The canonical proposal service is unavailable.",
                    )
                try:
                    canonical = self.edits.get(project_id, request.proposal_id)
                except FactoryError as exc:
                    raise BuilderConversationError(
                        "builder_proposal_not_found",
                        "The Builder proposal was not found.",
                        status_code=404,
                    ) from exc
                input_payload = _load_object(operation.get("input_json"))
                canonical_operation = canonical.get("operation_id")
                canonical_matches_focus = canonical.get(
                    "target_kind"
                ) == input_payload.get("focus_kind") and canonical.get(
                    "target_id"
                ) == input_payload.get("focus_id")
                if (
                    (
                        operation.get("proposal_id")
                        and operation["proposal_id"] != request.proposal_id
                    )
                    or (
                        canonical_operation is not None
                        and canonical_operation != operation_id
                    )
                    or (canonical_operation is None and not canonical_matches_focus)
                ):
                    raise BuilderConversationError(
                        "builder_proposal_mismatch",
                        "The proposal does not belong to this Builder operation.",
                    )
            self._apply_record_status(operation, request.kind, request.proposal_id)
        locale: Literal["zh", "en"] = "zh" if _looks_zh(request.content) else "en"
        facts = _facts(
            {
                "kind": request.kind,
                **({"proposal_id": request.proposal_id} if request.proposal_id else {}),
                **request.details,
            }
        )
        if operation_id:
            existing = {item["kind"] for item in self.store.events(operation_id)}
            event_kind = _record_event_kind(request.kind)
            if event_kind and event_kind not in existing:
                self._emit(
                    operation_id,
                    event_kind,
                    locale,
                    summary=_clean(request.content)[:240],
                    facts=facts,
                )
            if request.kind == "confirm" and APPLY_STARTED not in existing:
                self._emit(operation_id, APPLY_STARTED, locale, facts=facts)
            if request.kind == "validation_summary":
                valid = str(request.details.get("valid") or "").casefold() == "true"
                name = (
                    request.details.get("agent_name")
                    or request.details.get("name")
                    or ""
                )
                already = any(
                    row["kind"] == "result" and row["operation_id"] == operation_id
                    for row in self.store.messages(conversation_id)
                )
                if not already:
                    self.store.append_message(
                        message_id=new_uuid7(),
                        conversation_id=conversation_id,
                        sequence=self.store.next_sequence(conversation_id),
                        role="assistant",
                        kind="result",
                        content=_result_text(locale, name, valid=valid),
                        operation_id=operation_id,
                        payload=facts,
                        created_at=_now(),
                    )
                if valid:
                    self._emit(operation_id, OPERATION_COMPLETED, locale, facts=facts)
                    self._complete_operation(
                        operation_id, "succeeded", proposal_id=request.proposal_id
                    )
        return self.snapshot(project_id, conversation_id)

    def snapshot(
        self,
        project_id: str,
        conversation_id: str,
        *,
        resolution: dict[str, Any] | None = None,
        factory_session: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        conversation = self.store.conversation(conversation_id, project_id)
        if conversation is None:
            raise BuilderConversationError(
                "builder_conversation_not_found",
                "Builder conversation was not found",
                status_code=404,
            )
        for row in self.store.operations(conversation_id):
            if row["kind"] == "test_agent" and row["run_id"]:
                self._sync_test_run(project_id, conversation_id, row)
        operations = [
            self._public_operation(row, project_id)
            for row in self.store.operations(conversation_id)
        ]
        latest = operations[-1] if operations else None
        session_id = next(
            (
                item["factory_session_id"]
                for item in reversed(operations)
                if item.get("factory_session_id")
            ),
            None,
        )
        session = factory_session
        if session is None and session_id:
            try:
                session = self.factory.get_session(project_id, session_id)
            except FactoryError:
                session = None
        return {
            "schema_version": "1.0",
            "conversation": {
                "conversation_id": conversation["conversation_id"],
                "project_id": conversation["project_id"],
                "title": self._ensure_readable_title(
                    conversation_id, conversation["title"]
                ),
                "status": conversation["status"],
                "created_at": conversation["created_at"],
                "updated_at": conversation["updated_at"],
                "last_activity_at": conversation["last_activity_at"],
                "last_operation_status": latest["status"] if latest else None,
            },
            "messages": [
                self._public_message(row)
                for row in self.store.messages(conversation_id)
            ],
            "operations": operations,
            "resolution": resolution,
            "factory_session": session,
        }

    def _begin(
        self,
        project_id: str,
        request: TurnRequest,
        *,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[str, str, str, Literal["zh", "en"], BuilderTarget | None]:
        locale: Literal["zh", "en"] = request.locale
        retry_of = request.retry_of
        focus = request.focus
        if retry_of:
            conversation_id = request.conversation_id
            if conversation_id is None:
                raise BuilderConversationError(
                    "builder_retry_invalid", "Retry requires a conversation"
                )
            conversation = self.store.conversation(conversation_id, project_id)
            if conversation is None:
                raise BuilderConversationError(
                    "builder_conversation_not_found",
                    "Builder conversation was not found",
                    status_code=404,
                )
            previous = self.store.operation(retry_of, conversation_id)
            if previous is None:
                raise BuilderConversationError(
                    "builder_operation_not_found",
                    "Builder operation was not found",
                    status_code=404,
                )
            if previous["status"] != "failed":
                raise BuilderConversationError(
                    "builder_retry_invalid",
                    "Only a failed Builder operation can be retried",
                )
            payload = _load_object(previous["input_json"])
            content = payload.get("content", "")
            if not content:
                raise BuilderConversationError(
                    "builder_retry_invalid",
                    "The operation has no request to retry",
                )
            focus = _focus_from_input(payload)
            locale = "zh" if payload.get("locale") == "zh" else "en"
            operation_id = new_uuid7()
            self.store.commit_user_turn(
                conversation_id=conversation_id,
                project_id=project_id,
                title=conversation["title"],
                create_conversation=False,
                operation_id=operation_id,
                kind=previous["kind"],
                retry_of=retry_of,
                input_payload=_input_payload(content, locale, focus),
                message_id=None,
                content=None,
                created_at=_now(),
            )
            self._emit(operation_id, OPERATION_STARTED, locale, on_event=on_event)
            return conversation_id, operation_id, content, locale, focus

        content = _clean(request.content or "")
        if not content:
            raise BuilderConversationError(
                "builder_message_empty", "Builder message must not be empty"
            )
        conversation_id = request.conversation_id
        created = conversation_id is None
        if conversation_id is None:
            conversation_id = new_uuid7()
            title = _provisional_title(content)
        else:
            conversation = self.store.conversation(conversation_id, project_id)
            if conversation is None:
                raise BuilderConversationError(
                    "builder_conversation_not_found",
                    "Builder conversation was not found",
                    status_code=404,
                )
            title = conversation["title"]
        operation_id = new_uuid7()
        self.store.commit_user_turn(
            conversation_id=conversation_id,
            project_id=project_id,
            title=title,
            create_conversation=created,
            operation_id=operation_id,
            kind="resolve",
            retry_of=None,
            input_payload=_input_payload(content, locale, focus),
            message_id=new_uuid7(),
            content=content,
            created_at=_now(),
        )
        if not created:
            self._ensure_readable_title(conversation_id, title)
        self._emit(operation_id, OPERATION_STARTED, locale, on_event=on_event)
        return conversation_id, operation_id, content, locale, focus

    def _bounded_history(
        self, conversation_id: str, current_content: str
    ) -> list[BuilderMessage]:
        selected: list[BuilderMessage] = []
        for row in self.store.messages(conversation_id):
            if row["kind"] not in _HISTORY_KINDS:
                continue
            role: Literal["user", "assistant"] = (
                "user" if row["role"] == "user" else "assistant"
            )
            content = str(row["content"] or "").strip()
            if not content:
                continue
            selected.append(BuilderMessage(role=role, content=content[:10_000]))
        if (
            selected
            and selected[-1].role == "user"
            and selected[-1].content == current_content
        ):
            selected = selected[:-1]
        return selected[-HISTORY_LIMIT:]

    def _append_resolution(
        self,
        conversation_id: str,
        operation_id: str,
        resolution: dict[str, Any],
        locale: Literal["zh", "en"],
        *,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        kind = (
            "clarification"
            if resolution.get("status") == "clarification"
            else "assistant"
        )
        payload = _facts(
            {
                "intent": str(resolution.get("intent") or ""),
                "status": str(resolution.get("status") or ""),
                "create_kind": str(resolution.get("create_kind") or ""),
                "instruction": str(resolution.get("instruction") or "")[:500],
            }
        )
        self.store.append_message(
            message_id=new_uuid7(),
            conversation_id=conversation_id,
            sequence=self.store.next_sequence(conversation_id),
            role="assistant",
            kind=kind,
            content=str(resolution.get("message") or _understood(locale))[:4_000],
            operation_id=operation_id,
            payload=payload,
            created_at=_now(),
        )
        create_kind = str(resolution.get("create_kind") or "")
        target_kind = (
            create_kind
            if create_kind in {"agent", "workflow"}
            else str(resolution.get("intent") or "")
        )
        self._emit(
            operation_id,
            INTENT_RESOLVED,
            locale,
            facts={
                **payload,
                "target_kind": (
                    target_kind if target_kind in {"agent", "workflow"} else ""
                ),
            },
            on_event=on_event,
        )
        self.store.update_operation(
            operation_id,
            status="in_progress",
            updated_at=_now(),
            diagnostic=_facts(
                {
                    "resolution_json": json.dumps(
                        resolution, ensure_ascii=False, sort_keys=True
                    )[:12_000],
                    "intent": str(resolution.get("intent") or ""),
                    "create_kind": str(resolution.get("create_kind") or ""),
                }
            ),
        )
        if (
            resolution.get("intent") == "create"
            and resolution.get("create_kind") == "agent"
        ):
            self.store.update_operation(
                operation_id,
                status="in_progress",
                updated_at=_now(),
                kind="create_agent",
            )
        elif (
            resolution.get("intent") == "create"
            and resolution.get("create_kind") == "workflow"
        ):
            self.store.update_operation(
                operation_id,
                status="in_progress",
                updated_at=_now(),
                kind="create_workflow",
            )
        elif resolution.get("intent") == "edit":
            self.store.update_operation(
                operation_id, status="in_progress", updated_at=_now(), kind="edit"
            )

    def _requires_runtime_binding(self, project_id: str) -> bool:
        return bool(
            self.runtime
            and self.runtime_preflight
            and self.runtime.builder_runtime_preflight(project_id)["status"] != "ready"
        )

    def _wait_for_runtime_binding(
        self,
        project_id: str,
        conversation_id: str,
        operation_id: str,
        resolution: dict[str, Any],
        locale: Literal["zh", "en"],
    ) -> None:
        assert self.runtime is not None
        preflight = self.runtime.builder_runtime_preflight(project_id)
        waiting_for = str(preflight["status"])
        kind = (
            "create_workflow"
            if resolution.get("create_kind") == "workflow"
            else "create_agent"
        )
        self.store.update_operation(
            operation_id,
            status="waiting",
            updated_at=_now(),
            kind=kind,
            diagnostic=_facts(
                {
                    "waiting_for": waiting_for,
                    "binding_slot": str(
                        preflight.get("binding_slot") or "primary_model"
                    ),
                    "runtime_credentials_json": json.dumps(
                        preflight.get("credentials") or [],
                        ensure_ascii=False,
                        sort_keys=True,
                    )[:20_000],
                    "resolution_json": json.dumps(
                        resolution, ensure_ascii=False, sort_keys=True
                    )[:12_000],
                }
            ),
        )
        self.store.append_message(
            message_id=new_uuid7(),
            conversation_id=conversation_id,
            sequence=self.store.next_sequence(conversation_id),
            role="assistant",
            kind="clarification",
            content=(
                "还没有可用的 Runtime 模型 API，请先添加并选择一个 Provider。"
                if waiting_for == "waiting_for_runtime_credential" and locale == "zh"
                else (
                    "Choose the Runtime Provider and model for this Agent before "
                    "continuing."
                )
                if waiting_for == "waiting_for_runtime_binding"
                else "还没有可用的 Runtime 模型 API。"
            ),
            operation_id=operation_id,
            payload=_facts(
                {
                    "waiting_for": waiting_for,
                    "binding_slot": str(
                        preflight.get("binding_slot") or "primary_model"
                    ),
                    "credential_count": str(len(preflight.get("credentials") or [])),
                }
            ),
            created_at=_now(),
        )

    def command_runtime_binding(
        self,
        project_id: str,
        conversation_id: str,
        operation_id: str,
        request: RuntimeBindingCommandRequest,
    ) -> dict[str, Any]:
        if not request.confirm:
            raise BuilderConversationError(
                "runtime_binding_confirmation_required",
                "Explicit confirmation is required before continuing Builder "
                "generation.",
            )
        if request.credential_scope == "device" and (
            self.runtime is None or self.runtime.credentials is None
        ):
            raise BuilderConversationError(
                "runtime_binding_unavailable",
                "Runtime credential binding is unavailable.",
            )
        if self.store.conversation(conversation_id, project_id) is None:
            raise BuilderConversationError(
                "builder_conversation_not_found",
                "Builder conversation was not found",
                status_code=404,
            )
        operation = self.store.operation(operation_id, conversation_id)
        if operation is None:
            raise BuilderConversationError(
                "builder_operation_not_found",
                "Builder operation was not found",
                status_code=404,
            )
        if operation.get("status") != "waiting":
            raise BuilderConversationError(
                "runtime_binding_not_waiting",
                "This Builder operation is not waiting for Runtime binding.",
            )
        diagnostic = _load_object(operation.get("diagnostic_json"))
        if diagnostic.get("waiting_for") not in {
            "waiting_for_runtime_binding",
            "waiting_for_runtime_credential",
        }:
            raise BuilderConversationError(
                "runtime_binding_not_waiting",
                "This Builder operation is not waiting for Runtime binding.",
            )
        binding_slot = "primary_model"
        if request.credential_scope == "device":
            try:
                assert self.runtime is not None and self.runtime.credentials is not None
                binding = self.runtime.credentials.set_binding(
                    project_id,
                    None,
                    request.credential_id,
                    request.model_id,
                )
                binding_slot = binding.slot
            except ProviderCredentialError as exc:
                raise BuilderConversationError(exc.code, str(exc)) from exc
        resolution = _load_object(diagnostic.get("resolution_json"))
        input_payload = _load_object(operation.get("input_json"))
        locale: Literal["zh", "en"] = request.locale
        self.store.append_message(
            message_id=new_uuid7(),
            conversation_id=conversation_id,
            sequence=self.store.next_sequence(conversation_id),
            role="assistant",
            kind="confirm",
            content=(
                "已选择 Runtime Provider，继续生成 Agent Proposal。"
                if locale == "zh"
                else "Runtime Provider selected. Continuing Agent Proposal generation."
            ),
            operation_id=operation_id,
            payload=_facts(
                {
                    "credential_id": request.credential_id,
                    "model_id": request.model_id,
                    "binding_slot": binding_slot,
                    "credential_scope": request.credential_scope,
                }
            ),
            created_at=_now(),
        )
        self.store.update_operation(
            operation_id,
            status="in_progress",
            updated_at=_now(),
            diagnostic=_facts(
                {
                    "runtime_binding_status": "confirmed",
                    "credential_id": request.credential_id,
                    "model_id": request.model_id,
                    "credential_scope": request.credential_scope,
                    "resolution_json": json.dumps(
                        resolution, ensure_ascii=False, sort_keys=True
                    )[:12_000],
                }
            ),
        )
        content = str(input_payload.get("content") or "")
        receipts = HarnessReceiptRecorder(
            self.store,
            self.factory.harness,
            project_id=project_id,
            conversation_id=conversation_id,
            operation_id=operation_id,
            profile=self.factory.resolved_capability_profile(),
        )
        generate = self._generate_product
        try:
            generate(
                project_id,
                conversation_id,
                operation_id,
                resolution,
                content,
                locale,
                receipts=receipts,
            )
        except FactoryProviderError as exc:
            self._fail_operation(
                conversation_id,
                operation_id,
                locale,
                code=exc.code,
                message=str(exc),
                details=dict(exc.details or {}),
            )
        except (FactoryError, ProjectError, ContractValidationError) as exc:
            self._fail_operation(
                conversation_id,
                operation_id,
                locale,
                code=str(getattr(exc, "code", "builder_operation_failed")),
                message=str(exc),
                details={},
            )
        return self.snapshot(project_id, conversation_id, resolution=resolution)

    def _generate_product(
        self,
        project_id: str,
        conversation_id: str,
        operation_id: str,
        resolution: dict[str, Any],
        content: str,
        locale: Literal["zh", "en"],
        *,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        receipts: HarnessReceiptRecorder | None = None,
    ) -> dict[str, Any]:
        goal = content.strip() or str(resolution.get("instruction") or "")
        session = self.factory.create_session(project_id, goal, receipts=receipts)
        session_id = str(session["session_id"])
        self.store.update_operation(
            operation_id,
            status="in_progress",
            updated_at=_now(),
            factory_session_id=session_id,
            kind="create_agent",
        )

        def on_stage(kind: str, facts: dict[str, str]) -> None:
            self._emit(operation_id, kind, locale, facts=facts, on_event=on_event)
            name = facts.get("suggested_name")
            if name:
                self._maybe_upgrade_title(conversation_id, name)
                self.store.update_operation(
                    operation_id,
                    status="in_progress",
                    updated_at=_now(),
                    diagnostic=_facts({"candidate_name": name[:80], **facts}),
                )

        generated = self.factory.generate(
            project_id, session_id, on_stage=on_stage, receipts=receipts
        )
        state = str(generated.get("state") or "")
        candidate = generated.get("candidate") if isinstance(generated, dict) else None
        name = ""
        if isinstance(candidate, dict):
            name = str(candidate.get("name") or "")
        if state == "missing_capability":
            missing = generated.get("missing_capabilities") or []
            component_plan = next(
                (
                    item.get("component_plan")
                    for item in missing
                    if isinstance(item, dict)
                    and isinstance(item.get("component_plan"), dict)
                ),
                None,
            )
            if component_plan is not None and self.edits is not None:
                self._emit(
                    operation_id,
                    COMPONENT_DESIGN_STARTED,
                    locale,
                    facts=_facts({"factory_session_id": session_id}),
                    on_event=on_event,
                )
                proposal = self.edits.create_component_proposal(
                    project_id,
                    component_plan,
                    conversation_id=conversation_id,
                    operation_id=operation_id,
                    factory_session_id=session_id,
                    continuation="agent",
                )
                self._emit(
                    operation_id,
                    COMPONENT_DESIGN_COMPLETED,
                    locale,
                    facts=_facts(
                        {
                            "component_name": str(
                                component_plan.get("display_name") or ""
                            )[:200],
                            "implementation_kind": str(
                                (component_plan.get("implementation") or {}).get("kind")
                                or ""
                            ),
                            "readiness": str(
                                component_plan.get("readiness_expectation") or ""
                            ),
                        }
                    ),
                    on_event=on_event,
                )
                self._emit(
                    operation_id,
                    PROPOSAL_READY,
                    locale,
                    facts=_facts(
                        {
                            "proposal_id": str(proposal["proposal_id"]),
                            "proposal_kind": "create_custom_component",
                            "component_proposal_id": str(proposal["proposal_id"]),
                            "factory_session_id": session_id,
                            "state": "review",
                        }
                    ),
                    on_event=on_event,
                )
                self._complete_operation(
                    operation_id,
                    "waiting",
                    factory_session_id=session_id,
                    proposal_id=str(proposal["proposal_id"]),
                )
                return generated
            references = ", ".join(
                str(item.get("reference") or "")
                for item in missing
                if isinstance(item, dict)
            )
            self._fail_operation(
                conversation_id,
                operation_id,
                locale,
                code="factory_missing_capability",
                message=references
                or "Requested capability is not bound to this Project",
                details={"stage": "semantic_compilation"},
                on_event=on_event,
            )
            return generated
        if state != "review":
            question = str(generated.get("next_prompt") or "")
            self.store.append_message(
                message_id=new_uuid7(),
                conversation_id=conversation_id,
                sequence=self.store.next_sequence(conversation_id),
                role="assistant",
                kind="clarification",
                content=question[:4_000] or _understood(locale),
                operation_id=operation_id,
                payload=_facts({"factory_session_id": session_id, "state": state}),
                created_at=_now(),
            )
            self._emit(operation_id, OPERATION_COMPLETED, locale, on_event=on_event)
            self._complete_operation(
                operation_id, "succeeded", factory_session_id=session_id
            )
            return generated
        if str(generated.get("target_kind") or "") == "workflow":
            return self._materialize_workflow_proposal(
                project_id,
                conversation_id,
                operation_id,
                session_id,
                generated,
                name,
                locale,
                on_event=on_event,
            )
        if self.edits is None:
            raise FactoryError(
                "agent_creation_proposal_unavailable",
                "The canonical Agent creation proposal service is unavailable.",
            )
        candidate = self.factory.compile_review_source(project_id, session_id)
        proposal = self.edits.create_agent_proposal(
            project_id,
            candidate=candidate,
            conversation_id=conversation_id,
            operation_id=operation_id,
            factory_session_id=session_id,
            persist=False,
        )
        materialized = self.store.materialize_builder_proposal(
            proposal_store=self.edits.store,
            proposal=proposal,
            locale=locale,
            summary="",
            facts=_facts(
                {
                    "factory_session_id": session_id,
                    "agent_name": name[:200],
                }
            ),
            created_at=_now(),
        )
        event = materialized.get("event")
        if event is not None and on_event is not None:
            on_event(self._public_event(event))
        return generated

    def _materialize_workflow_proposal(
        self,
        project_id: str,
        conversation_id: str,
        operation_id: str,
        session_id: str,
        generated: dict[str, Any],
        name: str,
        locale: Literal["zh", "en"],
        *,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if self.edits is None:
            raise FactoryError(
                "workflow_creation_proposal_unavailable",
                "The canonical Workflow creation proposal service is unavailable.",
            )
        self.store.update_operation(
            operation_id,
            status="in_progress",
            updated_at=_now(),
            factory_session_id=session_id,
            kind="create_workflow",
        )
        review = self.factory.compile_review_source(project_id, session_id)
        proposal = self.edits.create_workflow_proposal(
            project_id,
            candidate=review,
            conversation_id=conversation_id,
            operation_id=operation_id,
            factory_session_id=session_id,
            persist=False,
        )
        materialized = self.store.materialize_builder_proposal(
            proposal_store=self.edits.store,
            proposal=proposal,
            locale=locale,
            summary="",
            facts=_facts(
                {
                    "factory_session_id": session_id,
                    "workflow_name": name[:200],
                    "target_kind": "workflow",
                    "product_shape": str(generated.get("product_shape") or ""),
                }
            ),
            created_at=_now(),
        )
        event = materialized.get("event")
        if event is not None and on_event is not None:
            on_event(self._public_event(event))
        return generated

    def _generate_workflow(
        self,
        project_id: str,
        conversation_id: str,
        operation_id: str,
        resolution: dict[str, Any],
        content: str,
        locale: Literal["zh", "en"],
        *,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        receipts: HarnessReceiptRecorder | None = None,
    ) -> dict[str, Any]:
        return self._generate_product(
            project_id,
            conversation_id,
            operation_id,
            resolution,
            content,
            locale,
            on_event=on_event,
            receipts=receipts,
        )

    def _create_component_proposal(
        self,
        project_id: str,
        conversation_id: str,
        operation_id: str,
        resolution: dict[str, Any],
        locale: Literal["zh", "en"],
        *,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        if self.edits is None:
            self._fail_operation(
                conversation_id,
                operation_id,
                locale,
                code="component_proposal_unavailable",
                message="Custom Component proposals are not configured.",
                details={"stage": "component_design"},
                on_event=on_event,
            )
            return
        raw = resolution.get("component_plan")
        if not isinstance(raw, dict):
            self._fail_operation(
                conversation_id,
                operation_id,
                locale,
                code="component_plan_missing",
                message=(
                    "The component request needs typed inputs, outputs, and a "
                    "capability description."
                ),
                details={"stage": "component_design"},
                on_event=on_event,
            )
            return
        requirement = str(raw.get("capability_requirement") or "")
        project_resources = self.edits.project_resources.list(project_id)["resources"]
        matching = matching_existing_component(project_resources, requirement)
        if len(matching) > 1:
            names = ", ".join(str(item.get("name") or "Component") for item in matching)
            message = (
                f"当前 Project 有多个匹配 Component：{names}。请指定要使用的一个。"
                if locale == "zh"
                else f"Several Project Components match: {names}. Please identify one."
            )
            self._append_component_message(
                conversation_id, operation_id, "clarification", message
            )
            self._emit(operation_id, OPERATION_COMPLETED, locale, on_event=on_event)
            self._complete_operation(operation_id, "succeeded", kind="create_component")
            return
        if matching:
            resource = matching[0]
            readiness = capability_readiness(resource)
            if readiness == "ready":
                message = (
                    f"Project 已有可复用 Component：{resource['name']}。"
                    "未创建重复组件。"
                    if locale == "zh"
                    else (
                        "A reusable Component already exists: "
                        f"{resource['name']}. No duplicate was created."
                    )
                )
                self._append_component_message(
                    conversation_id,
                    operation_id,
                    "result",
                    message,
                    payload={
                        "component_reference": str(resource.get("reference") or "")
                    },
                )
                self._emit(
                    operation_id,
                    OPERATION_COMPLETED,
                    locale,
                    facts=_facts(
                        {"component_reference": str(resource.get("reference") or "")}
                    ),
                    on_event=on_event,
                )
                self._complete_operation(
                    operation_id, "succeeded", kind="create_component"
                )
                return
            message = (
                f"已有匹配 Component {resource.get('name')}，但状态为 "
                f"{readiness}。请先完成配置；不会创建重复组件。"
                if locale == "zh"
                else (
                    f"The matching Component {resource.get('name')} is "
                    f"{readiness}. Configure it first; no duplicate was created."
                )
            )
            self._fail_operation(
                conversation_id,
                operation_id,
                locale,
                code="component_requires_configuration",
                message=message,
                details={"stage": "capability_resolution", "readiness": readiness},
                on_event=on_event,
            )
            return

        self._emit(
            operation_id,
            COMPONENT_DESIGN_STARTED,
            locale,
            on_event=on_event,
        )
        try:
            inputs = [
                SemanticField(
                    name=item["name"],
                    type=item["type"],
                    description=item.get("description", ""),
                    multiple=item.get("multiple", False),
                )
                for item in raw["inputs"]
            ]
            outputs = [
                SemanticField(
                    name=item["name"],
                    type=item["type"],
                    description=item.get("description", ""),
                    multiple=item.get("multiple", False),
                )
                for item in raw["outputs"]
            ]
            plan, reason = direct_component_draft_plan(
                capability_requirement=requirement,
                purpose=str(raw.get("purpose") or ""),
                operation_kind=cast(OperationKind, raw.get("operation_kind")),
                inputs=inputs,
                outputs=outputs,
                dependency_requirement=str(raw.get("dependency_requirement") or ""),
                project_resources=project_resources,
            )
        except (KeyError, TypeError, ValueError, ContractValidationError) as exc:
            plan, reason = None, str(exc)
        if plan is None:
            self._fail_operation(
                conversation_id,
                operation_id,
                locale,
                code="component_capability_unavailable",
                message=reason
                or "The current platform cannot safely implement this component.",
                details={"stage": "component_design"},
                on_event=on_event,
            )
            return
        proposal = self.edits.create_component_proposal(
            project_id,
            plan,
            conversation_id=conversation_id,
            operation_id=operation_id,
            factory_session_id=None,
            continuation="direct_component",
        )
        self._emit(
            operation_id,
            COMPONENT_DESIGN_COMPLETED,
            locale,
            facts=_facts(
                {
                    "component_name": str(plan["display_name"])[:200],
                    "implementation_kind": str(plan["implementation"]["kind"]),
                    "readiness": str(
                        proposal["component_plan"]["readiness_expectation"]
                    ),
                }
            ),
            on_event=on_event,
        )
        self._emit(
            operation_id,
            PROPOSAL_READY,
            locale,
            facts=_facts(
                {
                    "proposal_id": str(proposal["proposal_id"]),
                    "proposal_kind": "create_custom_component",
                    "component_proposal_id": str(proposal["proposal_id"]),
                    "state": "review",
                }
            ),
            on_event=on_event,
        )
        self._complete_operation(
            operation_id,
            "waiting",
            proposal_id=str(proposal["proposal_id"]),
            kind="create_component",
        )

    def command_component_proposal(
        self,
        project_id: str,
        conversation_id: str,
        operation_id: str,
        proposal_id: str,
        command: Literal["apply", "reject"],
        *,
        confirm: bool,
        locale: Literal["zh", "en"],
    ) -> dict[str, Any]:
        if not confirm:
            raise BuilderConversationError(
                "component_confirmation_required",
                "Explicit confirmation is required before applying a "
                "Component proposal.",
            )
        operation = self.store.operation(operation_id, conversation_id)
        if operation is None or operation.get("proposal_id") != proposal_id:
            raise BuilderConversationError(
                "component_proposal_operation_mismatch",
                "The Component proposal does not belong to the active "
                "Builder operation.",
            )
        if self.edits is None:
            raise BuilderConversationError(
                "component_proposal_unavailable",
                "Custom Component proposals are unavailable.",
            )
        proposal = self.edits.get_proposal(project_id, proposal_id)
        if (
            proposal.get("proposal_kind") != "create_custom_component"
            or proposal.get("conversation_id") != conversation_id
            or proposal.get("operation_id") != operation_id
        ):
            raise BuilderConversationError(
                "component_proposal_operation_mismatch",
                "The Component proposal does not match this Builder operation.",
            )

        session_id = str(proposal.get("factory_session_id") or "")
        session = (
            self.factory.get_session(project_id, session_id) if session_id else None
        )
        if (
            command == "apply"
            and proposal["state"] == "applied"
            and session
            and session["state"] == "review"
        ):
            return self.snapshot(project_id, conversation_id, factory_session=session)

        self._emit(
            operation_id,
            PROPOSAL_CONFIRMED if command == "apply" else PROPOSAL_REJECTED,
            locale,
            facts=_facts(
                {
                    "proposal_id": proposal_id,
                    "proposal_kind": "create_custom_component",
                    "command": command,
                }
            ),
        )
        if command == "reject":
            rejected = self.edits.command(
                project_id, proposal_id, "reject", confirm=True
            )
            message = (
                "已拒绝 Component 提案；没有创建 Component，也不会静默降级创建 Agent。"
                if locale == "zh"
                else (
                    "Component proposal rejected; no Component or fallback "
                    "Agent was created."
                )
            )
            self._append_component_message(
                conversation_id,
                operation_id,
                "result",
                message,
                payload={"proposal_id": proposal_id, "state": rejected["state"]},
            )
            self._complete_operation(operation_id, "rejected", proposal_id=proposal_id)
            return self.snapshot(project_id, conversation_id, factory_session=session)

        self._emit(
            operation_id,
            APPLY_STARTED,
            locale,
            facts=_facts(
                {"proposal_id": proposal_id, "proposal_kind": "create_custom_component"}
            ),
        )
        try:
            applied = self.edits.command(project_id, proposal_id, "apply", confirm=True)
        except (FactoryError, DraftConflict, ProjectError) as exc:
            code = getattr(exc, "code", "component_apply_failed")
            self._fail_operation(
                conversation_id,
                operation_id,
                locale,
                code=str(code),
                message=str(exc),
                details={"stage": "component_validation"},
            )
            return self.snapshot(project_id, conversation_id, factory_session=session)
        component = applied.get("created_component")
        if not isinstance(component, dict):
            raise BuilderConversationError(
                "component_apply_incomplete",
                "The Component proposal did not return a published Component.",
            )
        self._emit(
            operation_id,
            COMPONENT_CREATED,
            locale,
            facts=_facts(
                {
                    "component_id": str(component["component_id"]),
                    "component_name": str(component["display_name"]),
                    "component_reference": str(component["reference"]),
                    "readiness": str(component["readiness"]),
                }
            ),
        )
        message = (
            f"Custom Component 已发布：{component['display_name']} "
            f"v{component['version']}（{component['readiness']}）。"
            if locale == "zh"
            else (
                f"Custom Component published: {component['display_name']} "
                f"v{component['version']} ({component['readiness']})."
            )
        )
        self._append_component_message(
            conversation_id,
            operation_id,
            "result",
            message,
            payload={
                "component_id": str(component["component_id"]),
                "component_reference": str(component["reference"]),
                "readiness": str(component["readiness"]),
            },
        )
        self._emit(
            operation_id,
            APPLY_COMPLETED,
            locale,
            facts=_facts({"component_reference": str(component["reference"])}),
        )
        if proposal.get("continuation") == "direct_component":
            self._emit(
                operation_id,
                OPERATION_COMPLETED,
                locale,
                facts=_facts({"component_reference": str(component["reference"])}),
            )
            self._complete_operation(operation_id, "succeeded", proposal_id=proposal_id)
            return self.snapshot(project_id, conversation_id)

        if not session_id:
            self._fail_operation(
                conversation_id,
                operation_id,
                locale,
                code="factory_continuation_unavailable",
                message=(
                    "Component was published, but no Agent continuation "
                    "session is available."
                ),
                details={"stage": "semantic_compilation"},
            )
            return self.snapshot(project_id, conversation_id)

        def on_stage(kind: str, facts: dict[str, str]) -> None:
            self._emit(operation_id, kind, locale, facts=_facts(facts))

        try:
            resumed = self.factory.resume_after_component(
                project_id, session_id, on_stage=on_stage
            )
        except (FactoryError, DraftConflict, ProjectError) as exc:
            code = getattr(exc, "code", "factory_continuation_failed")
            self._fail_operation(
                conversation_id,
                operation_id,
                locale,
                code=str(code),
                message=str(exc),
                details={"stage": "semantic_compilation"},
            )
            return self.snapshot(project_id, conversation_id)
        if resumed["state"] == "review":
            self._emit(
                operation_id,
                PROPOSAL_READY,
                locale,
                facts=_facts(
                    {
                        "proposal_kind": "agent_blueprint",
                        "factory_session_id": session_id,
                        "agent_name": str(
                            (resumed.get("candidate") or {}).get("name") or ""
                        ),
                    }
                ),
            )
            self._complete_operation(
                operation_id, "waiting", factory_session_id=session_id
            )
            return self.snapshot(project_id, conversation_id, factory_session=resumed)

        next_plan = next(
            (
                item.get("component_plan")
                for item in resumed.get("missing_capabilities") or []
                if isinstance(item, dict)
                and isinstance(item.get("component_plan"), dict)
            ),
            None,
        )
        if resumed["state"] == "missing_capability" and next_plan is not None:
            try:
                next_proposal = self.edits.create_component_proposal(
                    project_id,
                    next_plan,
                    conversation_id=conversation_id,
                    operation_id=operation_id,
                    factory_session_id=session_id,
                    continuation="agent",
                )
            except FactoryError as exc:
                self._fail_operation(
                    conversation_id,
                    operation_id,
                    locale,
                    code=exc.code,
                    message=str(exc),
                    details={"stage": "component_design"},
                )
                return self.snapshot(project_id, conversation_id)
            self._emit(
                operation_id,
                COMPONENT_DESIGN_COMPLETED,
                locale,
                facts=_facts(
                    {
                        "component_name": str(next_plan.get("display_name") or ""),
                        "implementation_kind": str(
                            (next_plan.get("implementation") or {}).get("kind") or ""
                        ),
                        "readiness": str(next_plan.get("readiness_expectation") or ""),
                    }
                ),
            )
            self._emit(
                operation_id,
                PROPOSAL_READY,
                locale,
                facts=_facts(
                    {
                        "proposal_id": str(next_proposal["proposal_id"]),
                        "proposal_kind": "create_custom_component",
                        "component_proposal_id": str(next_proposal["proposal_id"]),
                        "factory_session_id": session_id,
                    }
                ),
            )
            self._complete_operation(
                operation_id,
                "waiting",
                factory_session_id=session_id,
                proposal_id=str(next_proposal["proposal_id"]),
            )
            return self.snapshot(project_id, conversation_id, factory_session=resumed)

        if resumed["state"] == "ready":
            prompt = str(resumed.get("next_prompt") or "")
            self._append_component_message(
                conversation_id, operation_id, "clarification", prompt
            )
            self._emit(operation_id, OPERATION_COMPLETED, locale)
            self._complete_operation(
                operation_id, "succeeded", factory_session_id=session_id
            )
            return self.snapshot(project_id, conversation_id, factory_session=resumed)

        missing = resumed.get("missing_capabilities") or []
        missing_names = ", ".join(
            str(item.get("reference") or item.get("kind") or "capability")
            for item in missing
            if isinstance(item, dict)
        )
        self._fail_operation(
            conversation_id,
            operation_id,
            locale,
            code="factory_missing_capability",
            message=missing_names
            or (
                "The Agent still has a capability blocker; the Component "
                "was published but no Agent was created."
            ),
            details={"stage": "semantic_compilation"},
        )
        return self.snapshot(project_id, conversation_id, factory_session=resumed)

    def _append_component_message(
        self,
        conversation_id: str,
        operation_id: str,
        kind: str,
        content: str,
        *,
        payload: dict[str, str] | None = None,
    ) -> None:
        if not content:
            return
        self.store.append_message(
            message_id=new_uuid7(),
            conversation_id=conversation_id,
            sequence=self.store.next_sequence(conversation_id),
            role="assistant",
            kind=kind,
            content=content[:4_000],
            operation_id=operation_id,
            payload=_facts(payload or {}),
            created_at=_now(),
        )

    def _fail_operation(
        self,
        conversation_id: str,
        operation_id: str,
        locale: Literal["zh", "en"],
        *,
        code: str,
        message: str,
        details: dict[str, str],
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        diagnostic = _facts(
            {
                "error_code": code,
                "stage": _PROVIDER_STAGES.get(code, "builder"),
                "http_status": details.get("http_status", ""),
                "provider_error_type": details.get("provider_error_type", ""),
                "provider_error_code": details.get("provider_error_code", ""),
                "rejected_field": details.get("rejected_field", ""),
                "provider": "Kimi K3",
            }
        )
        self.store.update_operation(
            operation_id,
            status="failed",
            updated_at=_now(),
            error_code=code,
            diagnostic=diagnostic,
        )
        self._emit(
            operation_id,
            OPERATION_FAILED,
            locale,
            summary=_failure_text(locale, code, message, diagnostic)[:240],
            facts=diagnostic,
            on_event=on_event,
        )
        self.store.append_message(
            message_id=new_uuid7(),
            conversation_id=conversation_id,
            sequence=self.store.next_sequence(conversation_id),
            role="assistant",
            kind="failure",
            content=_failure_text(locale, code, message, diagnostic),
            operation_id=operation_id,
            payload=diagnostic,
            created_at=_now(),
        )

    def _complete_operation(
        self,
        operation_id: str,
        status: str,
        *,
        factory_session_id: str | None = None,
        proposal_id: str | None = None,
        kind: str | None = None,
    ) -> None:
        self.store.update_operation(
            operation_id,
            status=status,
            updated_at=_now(),
            factory_session_id=factory_session_id,
            proposal_id=proposal_id,
            kind=kind,
        )

    def _apply_record_status(
        self, operation: dict[str, Any], kind: str, proposal_id: str | None
    ) -> None:
        current = str(operation["status"])
        if current == "failed":
            return
        desired = None
        if kind == "reject" and current in {"waiting", "in_progress"}:
            desired = "rejected"
        elif kind == "confirm" and current in {"waiting", "in_progress"}:
            desired = "waiting"
        elif kind == "apply_summary" and current in {"waiting", "in_progress"}:
            desired = "in_progress"
        if desired is None:
            return
        self.store.update_operation(
            operation["operation_id"],
            status=desired,
            updated_at=_now(),
            proposal_id=proposal_id,
        )

    def _require_project(self, project_id: str) -> None:
        if self.projects.repository.project(project_id) is None:
            raise BuilderConversationError(
                "builder_project_not_found",
                "Builder project was not found",
                status_code=404,
            )

    def _first_user_content(self, conversation_id: str) -> str:
        for row in self.store.messages(conversation_id):
            if row["kind"] == "user" and str(row["content"] or "").strip():
                return str(row["content"])
        return ""

    def _ensure_readable_title(self, conversation_id: str, title: str) -> str:
        compact = _clean(title)
        if (
            compact
            and compact != _TITLE_PLACEHOLDER
            and not _looks_like_identity(compact)
        ):
            return title
        repaired = _provisional_title(self._first_user_content(conversation_id))
        if repaired != title:
            self.store.touch(conversation_id, title=repaired, updated_at=_now())
        return repaired

    def _maybe_upgrade_title(self, conversation_id: str, suggested_name: str) -> None:
        conversation = self.store.conversation(conversation_id)
        if conversation is None:
            return
        current = str(conversation["title"] or "")
        first = self._first_user_content(conversation_id)
        if not _title_is_provisional(current, first):
            return
        upgraded = _title(suggested_name)
        if not upgraded or upgraded in {_TITLE_PLACEHOLDER, current}:
            return
        self.store.touch(conversation_id, title=upgraded, updated_at=_now())

    def receipts(
        self, project_id: str, conversation_id: str, operation_id: str
    ) -> dict[str, Any]:
        self._require_project(project_id)
        conversation = self.store.conversation(conversation_id, project_id)
        if conversation is None:
            raise BuilderConversationError(
                "builder_conversation_not_found",
                "Builder conversation was not found",
                status_code=404,
            )
        operation = self.store.operation(operation_id, conversation_id)
        if operation is None:
            raise BuilderConversationError(
                "builder_operation_not_found",
                "Builder operation was not found",
                status_code=404,
            )
        return {
            "schema_version": "1.0",
            "project_id": project_id,
            "conversation_id": conversation_id,
            "operation_id": operation_id,
            "receipts": [
                public_receipt(item)
                for item in self.store.receipts(
                    project_id=project_id,
                    conversation_id=conversation_id,
                    operation_id=operation_id,
                )
            ],
        }

    def command_agent_creation_proposal(
        self,
        project_id: str,
        conversation_id: str,
        operation_id: str,
        proposal_id: str,
        command: Literal["apply", "reject"],
        *,
        confirm: bool,
        locale: Literal["zh", "en"],
    ) -> dict[str, Any]:
        if not confirm:
            raise BuilderConversationError(
                "agent_creation_confirmation_required",
                "Explicit confirmation is required before applying an Agent Proposal.",
            )
        operation = self.store.operation(operation_id, conversation_id)
        if operation is None:
            raise BuilderConversationError(
                "builder_operation_not_found",
                "Builder operation was not found",
                status_code=404,
            )
        if operation.get("proposal_id") != proposal_id:
            raise BuilderConversationError(
                "agent_proposal_operation_mismatch",
                "The Agent Proposal does not belong to this Builder operation.",
            )
        if self.edits is None:
            raise BuilderConversationError(
                "agent_creation_proposal_unavailable",
                "The canonical Agent creation proposal service is unavailable.",
            )
        proposal = self.edits.get(project_id, proposal_id)
        proposal_kind = str(proposal.get("proposal_kind") or "")
        if (
            proposal_kind not in {"create_agent", "create_workflow"}
            or proposal.get("conversation_id") != conversation_id
            or proposal.get("operation_id") != operation_id
        ):
            raise BuilderConversationError(
                "agent_proposal_operation_mismatch",
                "The Agent Proposal does not match this Builder operation.",
            )
        if (
            command == "apply"
            and proposal.get("state") == "applied"
            and operation.get("status") == "succeeded"
        ) or (
            command == "reject"
            and proposal.get("state") == "rejected"
            and operation.get("status") == "rejected"
        ):
            return self.snapshot(project_id, conversation_id)
        if command == "apply" and proposal.get("state") == "rejected":
            raise BuilderConversationError(
                "agent_proposal_closed",
                "A rejected Agent Proposal cannot be applied.",
                status_code=409,
            )
        if command == "reject" and proposal.get("state") == "applied":
            raise BuilderConversationError(
                "agent_proposal_closed",
                "An applied Agent Proposal cannot be rejected.",
                status_code=409,
            )
        if command == "reject":
            rejected = self.edits.command(
                project_id, proposal_id, "reject", confirm=True
            )
            self._emit(
                operation_id,
                PROPOSAL_REJECTED,
                locale,
                facts=_facts(
                    {"proposal_id": proposal_id, "proposal_kind": proposal_kind}
                ),
            )
            self._complete_operation(operation_id, "rejected", proposal_id=proposal_id)
            if proposal_kind == "create_workflow":
                rejected_copy = (
                    "已拒绝 Workflow 提案。"
                    if locale == "zh"
                    else "Workflow Proposal rejected."
                )
            else:
                rejected_copy = (
                    "已拒绝 Agent 提案。"
                    if locale == "zh"
                    else "Agent Proposal rejected."
                )
            self.store.append_message(
                message_id=new_uuid7(),
                conversation_id=conversation_id,
                sequence=self.store.next_sequence(conversation_id),
                role="assistant",
                kind="result",
                content=rejected_copy,
                operation_id=operation_id,
                payload=_facts(
                    {"proposal_id": proposal_id, "state": rejected["state"]}
                ),
                created_at=_now(),
            )
            return self.snapshot(project_id, conversation_id)

        self._emit(
            operation_id,
            PROPOSAL_CONFIRMED,
            locale,
            facts=_facts({"proposal_id": proposal_id, "proposal_kind": proposal_kind}),
        )
        self._emit(
            operation_id,
            APPLY_STARTED,
            locale,
            facts=_facts({"proposal_id": proposal_id, "proposal_kind": proposal_kind}),
        )
        try:
            applied = self.edits.command(project_id, proposal_id, "apply", confirm=True)
        except (FactoryError, DraftConflict, ProjectError) as exc:
            code = getattr(exc, "code", "agent_creation_apply_failed")
            self._fail_operation(
                conversation_id,
                operation_id,
                locale,
                code=str(code),
                message=str(exc),
                details={"stage": "agent_creation_apply"},
            )
            return self.snapshot(project_id, conversation_id)
        if proposal_kind == "create_workflow":
            workflow = applied.get("applied_workflow")
            if not isinstance(workflow, dict):
                self._fail_operation(
                    conversation_id,
                    operation_id,
                    locale,
                    code="workflow_creation_apply_incomplete",
                    message=(
                        "The canonical Workflow Proposal did not return "
                        "an installed Workflow."
                    ),
                    details={"stage": "workflow_creation_apply"},
                )
                return self.snapshot(project_id, conversation_id)
            session_id = str(proposal.get("factory_session_id") or "")
            session = None
            if session_id:
                session = self.factory.mark_workflow_applied(
                    project_id, session_id, str(workflow["workflow_id"])
                )
            self._emit(
                operation_id,
                APPLY_COMPLETED,
                locale,
                facts=_facts(
                    {
                        "proposal_id": proposal_id,
                        "proposal_kind": "create_workflow",
                        "workflow_id": str(workflow["workflow_id"]),
                        "workflow_name": str(workflow.get("name") or ""),
                    }
                ),
            )
            self._emit(
                operation_id,
                OPERATION_COMPLETED,
                locale,
                facts=_facts({"proposal_id": proposal_id}),
            )
            self._complete_operation(operation_id, "succeeded", proposal_id=proposal_id)
            self.store.append_message(
                message_id=new_uuid7(),
                conversation_id=conversation_id,
                sequence=self.store.next_sequence(conversation_id),
                role="assistant",
                kind="result",
                content=(
                    "Workflow Draft 已创建。"
                    if locale == "zh"
                    else "Workflow Draft created from the confirmed Proposal."
                ),
                operation_id=operation_id,
                payload=_facts(
                    {
                        "proposal_id": proposal_id,
                        "workflow_id": str(workflow["workflow_id"]),
                    }
                ),
                created_at=_now(),
            )
            return self.snapshot(project_id, conversation_id, factory_session=session)
        agent = applied.get("applied_agent")
        if not isinstance(agent, dict):
            self._fail_operation(
                conversation_id,
                operation_id,
                locale,
                code="agent_creation_apply_incomplete",
                message=(
                    "The canonical Agent Proposal did not return an installed Agent."
                ),
                details={"stage": "agent_creation_apply"},
            )
            return self.snapshot(project_id, conversation_id)
        session_id = str(proposal.get("factory_session_id") or "")
        session = None
        if session_id:
            session = self.factory.mark_agent_applied(
                project_id, session_id, str(agent["agent_id"])
            )
        self._emit(
            operation_id,
            APPLY_COMPLETED,
            locale,
            facts=_facts(
                {
                    "proposal_id": proposal_id,
                    "proposal_kind": "create_agent",
                    "agent_id": str(agent["agent_id"]),
                    "agent_name": str(agent.get("name") or ""),
                }
            ),
        )
        self._emit(
            operation_id,
            OPERATION_COMPLETED,
            locale,
            facts=_facts({"proposal_id": proposal_id}),
        )
        self._complete_operation(operation_id, "succeeded", proposal_id=proposal_id)
        self.store.append_message(
            message_id=new_uuid7(),
            conversation_id=conversation_id,
            sequence=self.store.next_sequence(conversation_id),
            role="assistant",
            kind="result",
            content=(
                "Agent Draft 已创建。"
                if locale == "zh"
                else "Agent Draft created from the confirmed Proposal."
            ),
            operation_id=operation_id,
            payload=_facts(
                {"proposal_id": proposal_id, "agent_id": str(agent["agent_id"])}
            ),
            created_at=_now(),
        )
        return self.snapshot(project_id, conversation_id, factory_session=session)

    def start_test_run(
        self, project_id: str, conversation_id: str, request: TestRunRequest
    ) -> dict[str, Any]:
        self._require_project(project_id)
        conversation = self.store.conversation(conversation_id, project_id)
        if conversation is None:
            created_at = _now()
            self.store.create_conversation(
                conversation_id=conversation_id,
                project_id=project_id,
                title="测试 Agent" if request.locale == "zh" else "Test Agent",
                created_at=created_at,
            )
            conversation = self.store.conversation(conversation_id, project_id)
        if conversation is None:
            raise BuilderConversationError(
                "builder_conversation_not_found",
                "Builder conversation was not found",
                status_code=404,
            )
        if self.runtime is None:
            raise BuilderConversationError(
                "runtime_unavailable", "Local Runtime is not connected"
            )
        locale = request.locale
        agent_id = request.agent_id or self._conversation_agent_id(conversation_id)
        if not agent_id:
            raise BuilderConversationError(
                "builder_test_agent_missing",
                "Confirm and create an Agent before starting a test run",
            )
        try:
            self.runtime.library._agent_in_project(project_id, agent_id)
        except ProjectError as exc:
            raise BuilderConversationError(
                exc.code or "unknown_agent", str(exc), status_code=404
            ) from exc
        created_at = _now()
        operation_id = new_uuid7()
        self.store.create_operation(
            conversation_id=conversation_id,
            operation_id=operation_id,
            kind="test_agent",
            retry_of=None,
            input_payload={
                "agent_id": agent_id,
                "locale": locale,
                **(
                    {"workspace_id": request.workspace_id}
                    if request.workspace_id
                    else {}
                ),
                "inputs": json.dumps(
                    request.inputs, ensure_ascii=False, sort_keys=True
                ),
            },
            created_at=created_at,
        )
        self._emit(
            operation_id, OPERATION_STARTED, locale, facts={"agent_id": agent_id}
        )
        readiness = self.runtime.readiness(project_id, agent_id)
        raw_model = readiness.get("model")
        model = raw_model if isinstance(raw_model, dict) else {}
        if bool(model.get("required")) and not bool(model.get("configured")):
            observation = not_configured_observation(
                agent_id=agent_id,
                locale=locale,
                runtime_model_id=str(model.get("model_id") or ""),
                runtime_model_source=str(readiness.get("profile_source") or "host"),
            )
            self._emit(
                operation_id,
                TEST_STARTED,
                locale,
                facts={
                    "agent_id": agent_id,
                    "runtime_model_id": observation["runtime_model_id"],
                },
            )
            self._fail_test_operation(
                conversation_id,
                operation_id,
                locale,
                code="runtime_not_configured",
                message=str(observation["explanation"]),
                observation=observation,
            )
            return self.snapshot(project_id, conversation_id)
        self._emit(
            operation_id,
            TEST_STARTED,
            locale,
            facts={
                "agent_id": agent_id,
                "runtime_model_id": str(model.get("model_id") or ""),
            },
        )
        try:
            started = self.runtime.run(
                project_id,
                agent_id,
                request.inputs,
                new_uuid7(),
                conversation_id=None,
                append_user=True,
            )
        except (ProjectError, RuntimeFailure) as exc:
            self._fail_test_operation(
                conversation_id,
                operation_id,
                locale,
                code=exc.code,
                message=str(exc),
                observation={
                    "classification": "user_action"
                    if exc.code in {"inputs_invalid", "source_changed"}
                    else "environment",
                    "runtime_model_id": str(model.get("model_id") or ""),
                },
            )
            return self.snapshot(project_id, conversation_id)
        self.store.update_operation(
            operation_id,
            status="in_progress",
            updated_at=_now(),
            run_id=started["run_id"],
            diagnostic={
                "agent_id": agent_id,
                "version_id": str(started.get("version_id") or ""),
                "runtime_model_id": str(model.get("model_id") or ""),
            },
        )
        row = self.store.operation(operation_id, conversation_id)
        if row is not None:
            self._sync_test_run(project_id, conversation_id, row)
        return self.snapshot(project_id, conversation_id)

    def command_test_run(
        self,
        project_id: str,
        conversation_id: str,
        operation_id: str,
        request: TestRunCommandRequest,
    ) -> dict[str, Any]:
        self._require_project(project_id)
        operation = self._require_test_operation(
            project_id, conversation_id, operation_id
        )
        if self.runtime is None or not operation.get("run_id"):
            raise BuilderConversationError(
                "builder_test_run_missing", "No Runtime run is attached to this test"
            )
        payload = _load_object(operation.get("input_json"))
        agent_id = payload.get("agent_id") or self._conversation_agent_id(
            conversation_id
        )
        if not agent_id:
            raise BuilderConversationError(
                "builder_test_agent_missing", "The test operation is missing its Agent"
            )
        try:
            self.runtime.command(
                project_id,
                agent_id,
                str(operation["run_id"]),
                request.command,
                new_uuid7(),
            )
        except (ProjectError, RuntimeFailure) as exc:
            raise BuilderConversationError(exc.code, str(exc)) from exc
        row = self.store.operation(operation_id, conversation_id)
        if row is not None:
            self._sync_test_run(project_id, conversation_id, row)
        return self.snapshot(project_id, conversation_id)

    def propose_test_repair(
        self,
        project_id: str,
        conversation_id: str,
        operation_id: str,
        request: TestRepairRequest,
    ) -> dict[str, Any]:
        self._require_project(project_id)
        operation = self._require_test_operation(
            project_id, conversation_id, operation_id
        )
        if self.edits is None or self.runtime is None:
            raise BuilderConversationError(
                "builder_test_repair_unavailable",
                "Repair proposals are unavailable",
            )
        payload = _load_object(operation.get("input_json"))
        agent_id = payload.get("agent_id") or ""
        observation = self._observation_for(project_id, operation, request.locale)
        if observation is None or observation.get("classification") != "repairable":
            raise BuilderConversationError(
                "builder_test_not_repairable",
                "This Runtime failure cannot be repaired as an EditProposal",
            )
        reference = str(observation.get("repair_reference") or "")
        code = str(observation.get("repair_code") or "")
        if not reference or not code:
            raise BuilderConversationError(
                "builder_test_not_repairable",
                "This Runtime failure cannot be repaired as an EditProposal",
            )
        draft = self.edits.draft(project_id, "agent", agent_id)
        proposal = self.edits.create_validation_repair(
            project_id,
            agent_id,
            reference,
            code,
            int(draft["revision"]),
            str(draft["etag"]),
        )
        self.store.update_operation(
            operation_id,
            status=str(operation["status"]),
            updated_at=_now(),
            proposal_id=str(proposal["proposal_id"]),
        )
        return self.snapshot(project_id, conversation_id)

    def _require_test_operation(
        self, project_id: str, conversation_id: str, operation_id: str
    ) -> dict[str, Any]:
        conversation = self.store.conversation(conversation_id, project_id)
        if conversation is None:
            raise BuilderConversationError(
                "builder_conversation_not_found",
                "Builder conversation was not found",
                status_code=404,
            )
        operation = self.store.operation(operation_id, conversation_id)
        if operation is None or operation["kind"] != "test_agent":
            raise BuilderConversationError(
                "builder_operation_not_found",
                "Builder test operation was not found",
                status_code=404,
            )
        return operation

    def _conversation_agent_id(self, conversation_id: str) -> str | None:
        for row in reversed(self.store.operations(conversation_id)):
            payload = _load_object(row.get("input_json"))
            if payload.get("agent_id"):
                return payload["agent_id"]
            for event in reversed(self.store.events(row["operation_id"])):
                facts = _facts(_load_object(event.get("facts_json")))
                if facts.get("agent_id"):
                    return facts["agent_id"]
        return None

    def _sync_test_run(
        self, project_id: str, conversation_id: str, row: Mapping[str, Any]
    ) -> None:
        if self.runtime is None or not row.get("run_id"):
            return
        payload = _load_object(row.get("input_json"))
        locale: Literal["zh", "en"] = "zh" if payload.get("locale") == "zh" else "en"
        agent_id = payload.get("agent_id") or ""
        try:
            observation = observe_run(
                self.runtime,
                project_id,
                agent_id,
                str(row["run_id"]),
                locale=locale,
                repair_proposal_id=row.get("proposal_id"),
            )
        except ProjectError:
            return
        status = str(observation.get("status") or "")
        existing = {
            item["kind"] for item in self.store.events(str(row["operation_id"]))
        }
        if status == "waiting" and TEST_WAITING_APPROVAL not in existing:
            self._emit(
                str(row["operation_id"]),
                TEST_WAITING_APPROVAL,
                locale,
                facts={"run_id": str(row["run_id"])},
            )
            self.store.update_operation(
                str(row["operation_id"]), status="waiting", updated_at=_now()
            )
            return
        if status in {"verified", "unverified"} and OPERATION_COMPLETED not in existing:
            self._emit(
                str(row["operation_id"]),
                TEST_COMPLETED,
                locale,
                facts={
                    "run_id": str(row["run_id"]),
                    "version_id": str(observation.get("version_id") or ""),
                },
            )
            self._emit(str(row["operation_id"]), OPERATION_COMPLETED, locale)
            self._complete_operation(str(row["operation_id"]), "succeeded")
            return
        if (
            status in {"cancelled", "interrupted"}
            and OPERATION_COMPLETED not in existing
        ):
            self._emit(
                str(row["operation_id"]),
                TEST_STOPPED,
                locale,
                facts={"run_id": str(row["run_id"])},
            )
            self._emit(str(row["operation_id"]), OPERATION_COMPLETED, locale)
            self._complete_operation(str(row["operation_id"]), "succeeded")
            return
        if status == "failed" and OPERATION_FAILED not in existing:
            self._fail_test_operation(
                conversation_id,
                str(row["operation_id"]),
                locale,
                code=str(observation.get("failure_code") or "runtime_provider_error"),
                message=str(observation.get("explanation") or ""),
                observation=observation,
                run_id=str(row["run_id"]),
            )

    def _fail_test_operation(
        self,
        _conversation_id: str,
        operation_id: str,
        locale: Literal["zh", "en"],
        *,
        code: str,
        message: str,
        observation: Mapping[str, Any],
        run_id: str | None = None,
    ) -> None:
        existing = {item["kind"] for item in self.store.events(operation_id)}
        if TEST_FAILED not in existing:
            self._emit(
                operation_id,
                TEST_FAILED,
                locale,
                summary=message[:240],
                facts={
                    "error_code": code,
                    "classification": str(observation.get("classification") or ""),
                },
            )
        if OPERATION_FAILED not in existing:
            self._emit(operation_id, OPERATION_FAILED, locale, summary=message[:240])
        self.store.update_operation(
            operation_id,
            status="failed",
            updated_at=_now(),
            error_code=code,
            diagnostic={
                "error_code": code,
                "classification": str(observation.get("classification") or ""),
                "runtime_model_id": str(observation.get("runtime_model_id") or ""),
            },
            run_id=run_id,
        )
        # Keep Runtime test explanations on the operation observation.
        # Do not copy them into Chat messages.

    def _observation_for(
        self,
        project_id: str,
        row: Mapping[str, Any],
        locale: Literal["zh", "en"],
    ) -> dict[str, Any] | None:
        payload = _load_object(row.get("input_json"))
        agent_id = payload.get("agent_id") or ""
        if row.get("run_id") and self.runtime is not None and agent_id:
            try:
                return observe_run(
                    self.runtime,
                    project_id,
                    agent_id,
                    str(row["run_id"]),
                    locale=locale,
                    repair_proposal_id=row.get("proposal_id"),
                )
            except ProjectError:
                return None
        if row.get("error_code") == "runtime_not_configured":
            return not_configured_observation(
                agent_id=agent_id,
                locale=locale,
                runtime_model_id="",
                runtime_model_source="host",
            )
        return None

    def _public_operation(self, row: dict[str, Any], project_id: str) -> dict[str, Any]:
        diagnostic = _load_object(row.get("diagnostic_json"))
        payload = _load_object(row.get("input_json"))
        events = [
            self._public_event(item) for item in self.store.events(row["operation_id"])
        ]
        kind = str(row["kind"] or "")
        target_kind = "agent" if kind in {"create_agent", "test_agent"} else None
        if kind == "create_workflow":
            target_kind = "workflow"
        if kind == "edit":
            focus_kind = payload.get("focus_kind")
            if focus_kind in {"agent", "workflow"}:
                target_kind = focus_kind
        locale: Literal["zh", "en"] = "zh" if payload.get("locale") == "zh" else "en"
        observation = (
            self._observation_for(project_id, row, locale)
            if kind == "test_agent"
            else None
        )
        return {
            "operation_id": row["operation_id"],
            "conversation_id": row["conversation_id"],
            "kind": row["kind"],
            "target_kind": target_kind,
            "status": row["status"],
            "retry_of": row["retry_of"],
            "error_code": row["error_code"],
            "proposal_id": row["proposal_id"],
            "run_id": row["run_id"],
            "factory_session_id": row["factory_session_id"],
            **(
                {"workspace_id": payload["workspace_id"]}
                if isinstance(payload.get("workspace_id"), str)
                else {}
            ),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "diagnostic": _facts(diagnostic),
            "has_request": bool(payload.get("content")),
            "events": events,
            "receipts": [
                public_receipt(item)
                for item in self.store.receipts(
                    project_id=project_id,
                    conversation_id=str(row["conversation_id"]),
                    operation_id=str(row["operation_id"]),
                )
            ],
            "run_observation": public_observation(observation),
        }

    def _public_event(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "event_id": row["event_id"],
            "operation_id": row["operation_id"],
            "sequence": int(row["sequence"]),
            "kind": row["kind"],
            "label": row["label"],
            "summary": row["summary"],
            "facts": _facts(_load_object(row.get("facts_json"))),
            "created_at": row["created_at"],
        }

    def _emit(
        self,
        operation_id: str,
        kind: str,
        locale: Literal["zh", "en"],
        *,
        summary: str = "",
        facts: dict[str, str] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any] | None:
        try:
            row = self.store.append_event(
                event_id=new_uuid7(),
                operation_id=operation_id,
                kind=kind,
                label=event_label(kind, locale=locale),
                summary=_clean(summary)[:240],
                facts=_facts(facts or {}),
                created_at=_now(),
            )
        except ValueError as exc:
            if "immutable" in str(exc):
                return None
            raise BuilderConversationError(
                "builder_operation_event_invalid", str(exc)
            ) from exc
        public = self._public_event(row)
        if on_event is not None:
            on_event(public)
        return public

    def _public_message(self, row: dict[str, Any]) -> dict[str, Any]:
        kind = row["kind"] if row["kind"] in _MESSAGE_KINDS else "assistant"
        return {
            "message_id": row["message_id"],
            "conversation_id": row["conversation_id"],
            "sequence": int(row["sequence"]),
            "role": row["role"],
            "kind": kind,
            "content": row["content"],
            "operation_id": row["operation_id"],
            "payload": _facts(_load_object(row.get("payload_json"))),
            "created_at": row["created_at"],
        }


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _clean(value: str) -> str:
    return " ".join(value.split()).strip()


def _looks_like_identity(value: str) -> bool:
    compact = value.strip()
    if len(compact) != 36 or compact.count("-") != 4:
        return False
    hexpart = compact.replace("-", "")
    return len(hexpart) == 32 and all(
        char in "0123456789abcdefABCDEF" for char in hexpart
    )


def _title(content: str) -> str:
    compact = _clean(content)
    if not compact or _looks_like_identity(compact):
        return _TITLE_PLACEHOLDER
    if len(compact) <= _TITLE_LIMIT:
        return compact
    return compact[: _TITLE_LIMIT - 1] + "…"


def _provisional_title(content: str) -> str:
    compact = _clean(content)
    if not compact or _looks_like_identity(compact):
        return "新对话"
    clause = _CLAUSE_SPLIT.split(compact, maxsplit=1)[0].strip() or compact
    extracted = clause
    lowered = clause.casefold()
    for prefix in _TITLE_PREFIXES:
        if lowered.startswith(prefix.casefold()):
            extracted = clause[len(prefix) :].strip(" \t-—:：")
            break
    extracted = extracted.strip(" \t-—:：") or clause or compact
    titled = _title(extracted)
    if titled == _TITLE_PLACEHOLDER:
        return _title(compact)
    return titled


def _title_is_provisional(current: str, first_user: str) -> bool:
    compact = _clean(current)
    if not compact or compact == _TITLE_PLACEHOLDER or _looks_like_identity(compact):
        return True
    if not first_user:
        return False
    return compact in {_provisional_title(first_user), _title(first_user)}


def _looks_zh(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _record_event_kind(kind: str) -> str | None:
    mapping = {
        "proposal_reference": PROPOSAL_READY,
        "confirm": PROPOSAL_CONFIRMED,
        "reject": PROPOSAL_REJECTED,
        "apply_summary": APPLY_COMPLETED,
    }
    return mapping.get(kind)


def _result_text(locale: Literal["zh", "en"], name: str, *, valid: bool) -> str:
    label = name.strip() or ("Agent" if locale == "en" else "Agent")
    if locale == "zh":
        if valid:
            return f"{label}已经创建并通过结构验证。"
        return f"{label}已创建，但结构验证未通过。"
    if valid:
        return f"{label} was created and passed structural validation."
    return f"{label} was created, but structural validation failed."


def _input_payload(
    content: str, locale: Literal["zh", "en"], focus: BuilderTarget | None
) -> dict[str, str]:
    payload = {"content": content, "locale": locale}
    if focus is not None:
        payload["focus_kind"] = focus.kind
        payload["focus_id"] = focus.target_id
    return payload


def _focus_from_input(payload: dict[str, str]) -> BuilderTarget | None:
    kind = payload.get("focus_kind")
    target_id = payload.get("focus_id")
    if kind == "agent" and target_id:
        return BuilderTarget(kind="agent", target_id=target_id)
    if kind == "workflow" and target_id:
        return BuilderTarget(kind="workflow", target_id=target_id)
    return None


def _load_object(raw: Any) -> dict[str, str]:
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in parsed.items()
        if isinstance(key, str) and value is not None
    }


def _facts(values: dict[str, str]) -> dict[str, str]:
    facts: dict[str, str] = {}
    for key, value in values.items():
        lowered = key.casefold()
        if lowered in _FORBIDDEN_PAYLOAD_KEYS or not value:
            continue
        cleaned = _SECRET.sub("<redacted>", " ".join(str(value).split()))
        if not cleaned:
            continue
        facts[key[:80]] = cleaned[:200]
        if len(facts) >= 20:
            break
    return facts


def _understood(locale: Literal["zh", "en"]) -> str:
    return "我理解了这个请求。" if locale == "zh" else "I understood the request."


def _failure_text(
    locale: Literal["zh", "en"],
    code: str,
    message: str,
    diagnostic: dict[str, str],
) -> str:
    stage = diagnostic.get("stage") or "builder"
    provider = diagnostic.get("provider") or "Kimi K3"
    http_status = diagnostic.get("http_status") or ""
    error_type = diagnostic.get("provider_error_type") or ""
    safe_message = _SECRET.sub("<redacted>", " ".join(message.split()))[:240]
    generated = "factory" in code or stage == "blueprint_generation"
    if locale == "zh":
        heading = "Agent 结构生成失败" if generated else "Builder 未能完成这次操作"
        lines = [
            heading,
            f"Stage: {stage}",
            f"Provider: {provider}",
            f"Error: {safe_message}",
        ]
        if http_status:
            lines.append(f"HTTP: {http_status}")
        if error_type:
            lines.append(f"Type: {error_type}")
        return "\n".join(lines)
    lines = [
        "Agent structure generation failed"
        if "factory" in code or stage == "blueprint_generation"
        else "Builder could not finish this operation",
        f"Stage: {stage}",
        f"Provider: {provider}",
        f"Error: {safe_message}",
    ]
    if http_status:
        lines.append(f"HTTP: {http_status}")
    if error_type:
        lines.append(f"Type: {error_type}")
    return "\n".join(lines)
