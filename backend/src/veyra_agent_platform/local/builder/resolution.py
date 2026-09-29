"""Read-only intent resolution before the existing Builder proposal adapters."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from veyra_agent_platform.local.builder.receipts import HarnessReceiptRecorder
from veyra_agent_platform.local.builder.target_kind import classify_builder_target
from veyra_agent_platform.local.factory.client import FactoryProviderError
from veyra_agent_platform.local.factory.edit_service import EditProposalService
from veyra_agent_platform.local.factory.service import FactoryError


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BuilderTarget(ClosedModel):
    kind: Literal["agent", "workflow"]
    target_id: str = Field(min_length=1, max_length=64)


class BuilderMessage(ClosedModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=10_000)


class ResolveRequest(ClosedModel):
    content: str = Field(min_length=1, max_length=10_000)
    history: list[BuilderMessage] = Field(default_factory=list, max_length=20)
    focus: BuilderTarget | None = None
    locale: Literal["zh", "en"] = "en"


class TargetEvidence(BuilderTarget):
    basis: Literal["mention", "context"]
    mention: str = Field(max_length=200)


class ComponentIntentField(ClosedModel):
    name: str = Field(min_length=1, max_length=80)
    type: Literal[
        "string",
        "number",
        "integer",
        "boolean",
        "object",
        "array",
        "table",
        "image",
        "pdf",
        "document",
        "file",
        "audio",
        "video",
    ]
    description: str = Field(default="", max_length=240)
    multiple: bool = False


class DirectComponentIntent(ClosedModel):
    capability_requirement: str = Field(min_length=1, max_length=240)
    purpose: str = Field(min_length=1, max_length=240)
    operation_kind: Literal["model", "transform", "capability"]
    dependency_requirement: str = Field(default="", max_length=240)
    inputs: list[ComponentIntentField] = Field(min_length=1, max_length=16)
    outputs: list[ComponentIntentField] = Field(min_length=1, max_length=8)


class Intent(ClosedModel):
    intent: Literal["create", "create_component", "edit", "discuss", "clarify"]
    create_kind: Literal["agent", "workflow", "resource", "custom_component"] | None
    targets: list[TargetEvidence] = Field(max_length=20)
    multi_object: bool
    instruction: str = Field(max_length=10_000)
    message: str = Field(min_length=1, max_length=4000)
    plan: list[str] = Field(max_length=12)
    component_plan: DirectComponentIntent | None = None


class BuilderResolutionService:
    def __init__(self, edits: EditProposalService) -> None:
        self.edits = edits

    def resolve(
        self,
        project_id: str,
        request: ResolveRequest,
        *,
        receipts: HarnessReceiptRecorder | None = None,
        on_visible: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        messages = self.edits.harness.messages(
            project_id,
            "resolve_intent",
            schema=Intent.model_json_schema(),
            conversation=request.model_dump(),
        )
        context = json.loads(messages[1]["content"])
        inventory = [
            {**item, "kind": kind, "target_id": item[f"{kind}_id"]}
            for kind in ("agent", "workflow")
            for item in context["inventory"][f"{kind}s"]
        ]
        indexed = {(item["kind"], item["target_id"]): item for item in inventory}
        if (
            request.focus
            and (request.focus.kind, request.focus.target_id) not in indexed
        ):
            raise FactoryError(
                "builder_target_invalid", "Context target is not in this Project"
            )
        self.edits.client.ensure_model()
        schema = Intent.model_json_schema()
        receipt_id = None
        if receipts is not None:
            receipt_id = receipts.begin(
                kind="resolve_intent",
                harness_mode="resolve_intent",
                structured_mode="json_object",
                output_contract="BuilderIntentV1",
                schema=schema,
                messages=messages,
                history_message_count=len(request.history),
            )
        try:
            completion = self.edits.client.complete(
                messages,
                response_format={"type": "json_object"},
                **({"on_visible": on_visible} if on_visible is not None else {}),
            )
        except Exception as exc:
            if (
                receipt_id is not None
                and receipts is not None
                and isinstance(exc, FactoryProviderError)
            ):
                receipts.fail(receipt_id, exc)
            raise
        if receipt_id is not None and receipts is not None:
            receipts.succeed(receipt_id, provider_request_id=completion.request_id)
        try:
            if len(completion.content.encode()) > 40_000:
                raise ValueError("Resolution exceeds the size limit")
            intent = Intent.model_validate_json(completion.content)
        except ValueError as exc:
            raise FactoryError(
                "builder_resolution_invalid",
                "Builder could not resolve the request; nothing changed. "
                "Try rephrasing.",
            ) from exc

        result: dict[str, Any] = {
            "schema_version": "1.0",
            "intent": intent.intent,
            "create_kind": intent.create_kind,
            "status": "resolved",
            "message": intent.message,
            "instruction": intent.instruction,
            "plan": intent.plan,
            "targets": [],
        }
        if intent.component_plan is not None:
            result["component_plan"] = intent.component_plan.model_dump()
        latest = request.content.casefold()
        mentioned = [
            item
            for item in inventory
            if any(
                _mentions(latest, str(item[key]))
                for key in ("name", "slug", "target_id")
            )
        ]
        user_text = latest
        if not mentioned:
            previous = next(
                (m.content for m in reversed(request.history) if m.role == "user"), ""
            )
            user_text = previous.casefold() + "\n" + latest
            mentioned = [
                item
                for item in inventory
                if any(
                    _mentions(user_text, str(item[key]))
                    for key in ("name", "slug", "target_id")
                )
            ]
        has_agent = bool(re.search(r"\bagent\b|智能体", latest))
        has_workflow = bool(re.search(r"\bworkflow\b|工作流", latest))
        if has_agent != has_workflow:
            mentioned = [
                item
                for item in mentioned
                if item["kind"] == ("agent" if has_agent else "workflow")
                or not any(
                    other["kind"] != item["kind"]
                    and any(
                        str(item[key]).casefold() == str(other[other_key]).casefold()
                        and _mentions(user_text, str(item[key]))
                        for key in ("name", "slug", "target_id")
                        for other_key in ("name", "slug", "target_id")
                    )
                    for other in mentioned
                )
            ]
        for target in intent.targets:
            item = indexed.get((target.kind, target.target_id))
            if item is None:
                return self._clarify(result, request, [])
            aliases = {
                str(item[key]).casefold() for key in ("name", "slug", "target_id")
            }
            mention = target.mention.strip().casefold()
            if target.basis == "context":
                if request.focus is None or (target.kind, target.target_id) != (
                    request.focus.kind,
                    request.focus.target_id,
                ):
                    return self._clarify(result, request, [])
                if mentioned and (
                    len(mentioned) != 1
                    or (mentioned[0]["kind"], mentioned[0]["target_id"])
                    != (target.kind, target.target_id)
                ):
                    return self._clarify(result, request, mentioned)
            elif (
                not mention
                or mention not in aliases
                or not _mentions(user_text, mention)
            ):
                return self._clarify(result, request, [])
            else:
                matches = [
                    other
                    for other in inventory
                    if mention
                    in {
                        str(other[key]).casefold()
                        for key in ("name", "slug", "target_id")
                    }
                ]
                # Only the latest clarification can narrow a same-name match.
                if has_agent != has_workflow:
                    matches = [
                        other
                        for other in matches
                        if other["kind"] == ("agent" if has_agent else "workflow")
                    ]
                if len(matches) != 1 or matches[0]["target_id"] != target.target_id:
                    return self._clarify(result, request, matches)
            result["targets"].append(
                {
                    "kind": target.kind,
                    "target_id": target.target_id,
                    "name": item["name"],
                }
            )
        if intent.intent == "clarify":
            result["status"] = "clarification"
        elif intent.intent == "edit":
            if not result["targets"] or not intent.instruction.strip():
                return self._clarify(result, request, [])
            if any(
                (item["kind"], item["target_id"])
                not in {
                    (target["kind"], target["target_id"])
                    for target in result["targets"]
                }
                for item in mentioned
            ):
                return self._clarify(result, request, mentioned)
            if intent.multi_object or len(result["targets"]) != 1:
                result["status"] = "unsupported"
                result["message"] = (
                    "这是跨对象 / Workflow 级修改；当前尚不支持多对象事务，"
                    "未生成或应用部分修改。"
                    if request.locale == "zh"
                    else "This is a cross-object / Workflow-level change. "
                    "Multi-object transactions are not supported yet; "
                    "no partial change was proposed or applied."
                )
            else:
                target = result["targets"][0]
                draft = indexed[(target["kind"], target["target_id"])]["draft"]
                target.update(revision=draft["revision"], etag=draft["etag"])
        elif intent.intent == "create_component" or (
            intent.intent == "create" and intent.create_kind == "custom_component"
        ):
            if intent.multi_object or intent.targets:
                result["status"] = "unsupported"
                result["message"] = (
                    "组件创建一次只处理一个独立能力；当前请求包含多个对象，请拆分后逐个确认。"
                    if request.locale == "zh"
                    else (
                        "Component creation is one independent capability at a time. "
                        "Split this multi-object request."
                    )
                )
            elif intent.component_plan is None:
                result.update(status="clarification", intent="clarify")
                result["message"] = (
                    "请说明这个可复用组件的输入、输出和要完成的具体能力。"
                    if request.locale == "zh"
                    else (
                        "Please specify the reusable component's inputs, outputs, "
                        "and specific capability."
                    )
                )
            else:
                result.update(status="resolved", create_kind="custom_component")
                result["intent"] = "create_component"
        elif (
            intent.intent == "create"
            and intent.create_kind
            in {
                "agent",
                "workflow",
            }
            and not intent.multi_object
            and not intent.targets
        ):
            classified = classify_builder_target(request.content)
            result["create_kind"] = classified.create_kind
            result["user_requested_surface"] = classified.user_requested_surface
            result["status"] = "resolved"
            result["instruction"] = request.content.strip()
            result["message"] = (
                classified.message_zh
                if request.locale == "zh"
                else classified.message_en
            )
            result["plan"] = [
                classified.reason,
                *list(intent.plan or []),
            ][:12]
        elif intent.intent == "create" and (
            intent.create_kind not in {"agent", "workflow"}
            or intent.multi_object
            or intent.targets
        ):
            result["status"] = "unsupported"
            result["message"] = (
                "已识别创建需求；当前创建适配器仅支持单个 Agent 或 Workflow，"
                "不会改为创建错误类型或部分对象。"
                if request.locale == "zh"
                else "Creation recognized. The current creation adapter supports "
                "one Agent or one Workflow; it will not substitute another type "
                "or create only part of the request."
            )
        return result

    @staticmethod
    def _clarify(
        result: dict[str, Any], request: ResolveRequest, matches: list[dict[str, Any]]
    ) -> dict[str, Any]:
        choices = " / ".join(
            dict.fromkeys(
                f"{item['kind']} · {item['name']} ({item['target_id']})"
                for item in matches
            )
        )
        result.update(status="clarification", intent="clarify", targets=[], plan=[])
        if request.locale == "zh":
            result["message"] = (
                f"你指的是哪一个对象：{choices}？"
                if choices
                else "请告诉我目标对象的名称和类型。"
            )
        else:
            result["message"] = (
                f"Which object do you mean: {choices}?"
                if choices
                else "Which object do you mean? Please give its name and type."
            )
        return result


def _mentions(text: str, alias: str) -> bool:
    alias = alias.casefold()
    return bool(
        re.search(r"(?<![a-z0-9_-])" + re.escape(alias) + r"(?![a-z0-9_-])", text)
    )
