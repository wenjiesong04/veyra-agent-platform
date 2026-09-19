"""Persist Project Builder turns before model calls; failures stay in history."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from veyra_agent_platform.contracts.common import ContractValidationError, new_uuid7
from veyra_agent_platform.local.builder.conversation_store import (
    BuilderConversationStore,
)
from veyra_agent_platform.local.builder.operation_events import (
    APPLY_COMPLETED,
    APPLY_STARTED,
    INTENT_RESOLVED,
    INTENT_STARTED,
    OPERATION_COMPLETED,
    OPERATION_FAILED,
    OPERATION_STARTED,
    PROPOSAL_CONFIRMED,
    PROPOSAL_READY,
    PROPOSAL_REJECTED,
    event_label,
)
from veyra_agent_platform.local.builder.resolution import (
    BuilderMessage,
    BuilderResolutionService,
    BuilderTarget,
    ResolveRequest,
)
from veyra_agent_platform.local.factory.client import FactoryProviderError
from veyra_agent_platform.local.factory.service import FactoryError, FactoryService
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService

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
    ) -> None:
        self.store = store
        self.projects = projects
        self.resolution = resolution
        self.factory = factory

    def turn(
        self,
        project_id: str,
        request: TurnRequest,
        *,
        on_event: Callable[[dict[str, Any]], None] | None = None,
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
            resolution = self.resolution.resolve(
                project_id,
                ResolveRequest(
                    content=content,
                    history=history,
                    focus=focus,
                    locale=locale,
                ),
            )
            self._append_resolution(
                conversation_id, operation_id, resolution, locale, on_event=on_event
            )
            if (
                resolution.get("status") == "resolved"
                and resolution.get("intent") == "create"
                and resolution.get("create_kind") == "agent"
            ):
                factory_session = self._generate_agent(
                    project_id,
                    conversation_id,
                    operation_id,
                    resolution,
                    content,
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

    def activity(self, project_id: str, *, limit: int = 5) -> dict[str, Any]:
        self._require_project(project_id)
        bound = max(1, min(limit, 5))
        items: list[dict[str, Any]] = []
        for row in self.store.conversations(project_id, limit=bound):
            latest = self.store.latest_operation(row["conversation_id"])
            items.append(
                {
                    "kind": "conversation",
                    "id": row["conversation_id"],
                    "conversation_id": row["conversation_id"],
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
            "project_id": project_id,
            "items": items[:bound],
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
        operations = [
            self._public_operation(row)
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
        elif resolution.get("intent") == "edit":
            self.store.update_operation(
                operation_id, status="in_progress", updated_at=_now(), kind="edit"
            )

    def _generate_agent(
        self,
        project_id: str,
        conversation_id: str,
        operation_id: str,
        resolution: dict[str, Any],
        content: str,
        locale: Literal["zh", "en"],
        *,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        goal = str(resolution.get("instruction") or content)
        session = self.factory.create_session(project_id, goal)
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

        generated = self.factory.generate(project_id, session_id, on_stage=on_stage)
        state = str(generated.get("state") or "")
        candidate = generated.get("candidate") if isinstance(generated, dict) else None
        name = ""
        if isinstance(candidate, dict):
            name = str(candidate.get("name") or "")
        if state == "missing_capability":
            missing = generated.get("missing_capabilities") or []
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
        self._emit(
            operation_id,
            PROPOSAL_READY,
            locale,
            facts=_facts(
                {
                    "factory_session_id": session_id,
                    "agent_name": name[:200],
                    "state": state,
                }
            ),
            on_event=on_event,
        )
        self._complete_operation(operation_id, "waiting", factory_session_id=session_id)
        return generated

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
    ) -> None:
        self.store.update_operation(
            operation_id,
            status=status,
            updated_at=_now(),
            factory_session_id=factory_session_id,
            proposal_id=proposal_id,
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
        if compact and compact != _TITLE_PLACEHOLDER:
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

    def _public_operation(self, row: dict[str, Any]) -> dict[str, Any]:
        diagnostic = _load_object(row.get("diagnostic_json"))
        payload = _load_object(row.get("input_json"))
        events = [
            self._public_event(item) for item in self.store.events(row["operation_id"])
        ]
        kind = str(row["kind"] or "")
        target_kind = "agent" if kind == "create_agent" else None
        if kind == "create_workflow":
            target_kind = "workflow"
        if kind == "edit":
            focus_kind = payload.get("focus_kind")
            if focus_kind in {"agent", "workflow"}:
                target_kind = focus_kind
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
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "diagnostic": _facts(diagnostic),
            "has_request": bool(payload.get("content")),
            "events": events,
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


def _title(content: str) -> str:
    compact = _clean(content)
    if not compact:
        return _TITLE_PLACEHOLDER
    if len(compact) <= _TITLE_LIMIT:
        return compact
    return compact[: _TITLE_LIMIT - 1] + "…"


def _provisional_title(content: str) -> str:
    compact = _clean(content)
    if not compact:
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
    if not compact or compact == _TITLE_PLACEHOLDER:
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
