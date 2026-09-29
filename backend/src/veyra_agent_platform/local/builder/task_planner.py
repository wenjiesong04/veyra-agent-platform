"""Structured task planner: language/structure clues, never occupation maps."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from veyra_agent_platform.contracts.common import (
    SCHEMA_VERSION,
    ContractValidationError,
)
from veyra_agent_platform.contracts.condition import parse_condition_expression
from veyra_agent_platform.contracts.task_structure import (
    ExecutionBoundary,
    InteractionModeHint,
    OrchestrationComplexity,
    StateRequirement,
    TaskActor,
    TaskIOField,
    TaskLifecycle,
    TaskStage,
    TaskStructure,
)

MAX_PLANNER_REPAIRS = 3

_MULTI_IMAGE = re.compile(
    r"(很多|多张|十几张|一次上传很多|一批|several|multiple|many)\s*"
    r"(张)?\s*(照片|图片|图像|photos?|images?)",
    re.IGNORECASE,
)
_SINGLE_IMAGE = re.compile(
    r"(一张|一个|单张|an? |one )\s*(照片|图片|图像|photo|image)",
    re.IGNORECASE,
)
_IMAGE = re.compile(r"照片|图片|图像|\bphotos?\b|\bimages?\b", re.IGNORECASE)
_DOCUMENT = re.compile(
    r"合同|\bpdf\b|文档|document|\bword\b",
    re.IGNORECASE,
)
_TABLE = re.compile(r"\bcsv\b|表格|spreadsheet|\bexcel\b", re.IGNORECASE)
_JSON = re.compile(r"\bjson\b", re.IGNORECASE)
_FOLDER = re.compile(r"文件夹|\bfolders?\b|多个文件|several files", re.IGNORECASE)
_WEB_SEARCH = re.compile(
    r"搜索网页|网页搜索|搜索公开(?:网页|资料|信息)|web search|search the web|"
    r"上网搜|查价格|搜价格|市场价格|公开资料|search the public|"
    r"调研|竞品",
    re.IGNORECASE,
)
_WORKSPACE_READ = re.compile(
    r"读取.{0,16}(项目|文件|代码)|查看.{0,12}(项目文件|文件|代码)|"
    r"阅读代码|阅读文件|阅读项目|"
    r"filesystem\.read|read (?:project |workspace )?files|read code",
    re.IGNORECASE,
)
_WORKSPACE_SEARCH = re.compile(
    r"搜索.{0,16}(项目文件|代码|工作区)|filesystem\.search|"
    r"search (?:project |workspace |the )?code",
    re.IGNORECASE,
)
_WORKSPACE_WRITE = re.compile(
    r"修改.{0,16}文件|写文件|写入文件|filesystem\.write|"
    r"edit (?:project |workspace )?files",
    re.IGNORECASE,
)
_SHELL = re.compile(
    r"运行测试|执行.{0,8}命令|危险命令|\bshell\b|run (?:the )?tests",
    re.IGNORECASE,
)
_IMAGE_GEN = re.compile(
    r"生成.{0,16}(效果图|图片|图像|设计图|最终设计)|"
    r"image generation|generate .{0,12}(image|visual)",
    re.IGNORECASE,
)
_TOOL_APPROVAL = re.compile(
    r"(写文件|修改|执行.{0,8}(危险)?命令).{0,16}(前|之前).{0,8}确认|"
    r"危险命令前|before (?:writing|modifying|running)",
    re.IGNORECASE,
)
_BUSINESS_APPROVAL = re.compile(
    r"(价格|售价).{0,12}(确认|批准)|让我确认|让我审批|选定.{0,12}以后|"
    r"确认后(再|才能|继续|存档)|经我批准|不要自动(执行|上架|发布)|"
    r"我确认以后才能|批准发布|是否采用|用户选定方案以后|"
    r"必须由.{0,12}确认|after (?:i |the user )?confirm",
    re.IGNORECASE,
)
_COMPARE_THEN = re.compile(r"(低于|高于|小于|大于).{0,12}?就", re.IGNORECASE)
_SOFT_IF = re.compile(r"如果你觉得|如果可以的话|要是方便", re.IGNORECASE)
_UNKNOWN_THEN_ASK = re.compile(
    r"(型号|信息|字段).{0,20}(不知道|看不出来|识别不了|无法确定|不确定)"
    r".{0,24}(问我|向我确认|让我补充|停下来)|"
    r"(不知道|看不出来|识别不了|无法确定|不确定).{0,16}"
    r"(型号|信息).{0,20}(问我|向我确认|让我补充|停下来)|"
    r"(看不出来|识别不了|无法确定).{0,8}就(问我|向我确认)",
    re.IGNORECASE,
)
_BLURRY_RETRY = re.compile(
    r"(太模糊|看不清).{0,12}(重新拍|再拍|重新上传)",
    re.IGNORECASE,
)
_AMOUNT_GATE = re.compile(
    r"(如果|若)?.{0,8}(金额|amount).{0,8}(超过|高于|>|大于)\s*"
    r"(\d+(?:\.\d+)?)\s*(万|w)?",
    re.IGNORECASE,
)
_PERSIST = re.compile(
    r"(保存|持久).{0,16}(状态|历史|对象)|价格历史|revision|"
    r"每个.{0,12}有状态|以后会不断|跨.{0,6}(次|run)|长期保存|"
    r"成交以后改成|不断更新|存档",
    re.IGNORECASE,
)
_VERIFY = re.compile(
    r"最后检查|确认有没有漏|验证是否|测试是否通过|"
    r"检查.{0,8}完整性|verify|validation",
    re.IGNORECASE,
)
_FORCE_AGENT = re.compile(
    r"不要\s*workflow|就做一个简单\s*agent|只要(一个)?\s*agent|"
    r"不要流程,?\s*就做",
    re.IGNORECASE,
)
_TRANSLATE_ONLY = re.compile(r"翻译|translate", re.IGNORECASE)
_ANALYSIS_REPORT = re.compile(r"分析报告|structured analysis", re.IGNORECASE)
_RESEARCH_REPORT = re.compile(r"研究报告|research report", re.IGNORECASE)
_STRUCTURED_OUTPUT = re.compile(
    r"结构化(?:研究)?报告|整理报告|structured (?:report|output)",
    re.IGNORECASE,
)
_SEARCH_FOR_TOOL = re.compile(r"搜索.{0,8}翻译", re.IGNORECASE)
_SURFACE_AGENT = re.compile(r"\bagent\b|助手|助理", re.IGNORECASE)
_SURFACE_WORKFLOW = re.compile(r"流程|workflow|自动化流水", re.IGNORECASE)
_RESEARCH_METHOD = re.compile(
    r"研究方法|整理证据|整理报告|研究报告|evidence synthesis|research brief",
    re.IGNORECASE,
)
_GITHUB_READ = re.compile(
    r"github(?:\s+issues)?(?:\s+read)?|读取.{0,12}github|"
    r"仓库读取|triage github|github issues",
    re.IGNORECASE,
)
_GITHUB_WRITE = re.compile(
    r"github write|写入.{0,12}github|repository write",
    re.IGNORECASE,
)
_KNOWLEDGE = re.compile(
    r"项目知识|项目资料|项目里的|项目中的|当前项目中|"
    r"project knowledge|brand guidelines",
    re.IGNORECASE,
)
_DOCUMENT_ANALYSIS = re.compile(
    r"分析文档|document analysis|document analyzer|"
    r"品牌规范|设计规范|brand guidelines",
    re.IGNORECASE,
)
_NAMED_CAPABILITY = re.compile(
    r"(?:capability|能力)\s*[:=]\s*`?([a-z][a-z0-9_]{2,62})`?",
    re.IGNORECASE,
)
_HTTP_REQUEST = re.compile(
    r"http\.request|调用 http|http request",
    re.IGNORECASE,
)
_MODEL_ONLY_CAPS = {
    "vision",
    "text_generation",
    "structured_output",
    "tool_calling",
    "human_approval",
}
_NEEDS_MODEL = re.compile(
    r"分析|识别|提取|翻译|研究|建议|整理|写介绍|文案|助手|agent|"
    r"summar|extract|analy|design|推理",
    re.IGNORECASE,
)


class PlannerProvider(Protocol):
    def complete_json(self, prompt: str, schema: Mapping[str, Any]) -> dict[str, Any]:
        """Return a JSON object. Tests inject fakes; production may use Factory."""


@dataclass(frozen=True)
class PlannerResult:
    status: str
    structure: TaskStructure | None
    diagnostics: tuple[str, ...] = ()
    repairs: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "structure": None if self.structure is None else self.structure.to_dict(),
            "diagnostics": list(self.diagnostics),
            "repairs": self.repairs,
        }


def plan_task_structure(
    requirement: str,
    *,
    provider: PlannerProvider | None = None,
    repair: Callable[[str, str], dict[str, Any]] | None = None,
) -> PlannerResult:
    """Understand the task. Never decide Agent vs Workflow here."""

    text = " ".join(requirement.split()).strip()
    if not text:
        return PlannerResult("planner_invalid", None, ("empty_requirement",))
    if provider is None:
        try:
            structure = _deterministic_plan(text)
            structure = normalize_task_structure(structure)
            validate_task_structure(structure)
        except (ContractValidationError, ValueError) as exc:
            return PlannerResult("planner_invalid", None, (str(exc),))
        return PlannerResult("ok", structure)
    last_error = "planner_invalid"
    payload: dict[str, Any] | None = None
    for attempt in range(MAX_PLANNER_REPAIRS + 1):
        try:
            if attempt == 0:
                payload = provider.complete_json(text, _PLANNER_SCHEMA)
            elif repair is not None and payload is not None:
                payload = repair(json.dumps(payload, ensure_ascii=False), last_error)
            else:
                break
            structure = TaskStructure.from_dict(payload)
            structure = normalize_task_structure(structure)
            validate_task_structure(structure)
            return PlannerResult("ok", structure, repairs=attempt)
        except (ContractValidationError, ValueError, TypeError, KeyError) as exc:
            last_error = str(exc)
    return PlannerResult("planner_invalid", None, (last_error,), MAX_PLANNER_REPAIRS)


def normalize_task_structure(structure: TaskStructure) -> TaskStructure:
    inputs = tuple(_normalize_io(item) for item in structure.inputs)
    if not inputs:
        inputs = (
            TaskIOField(
                name="request",
                type="string",
                description="User request",
            ),
        )
    outputs = tuple(_normalize_io(item) for item in structure.outputs)
    if not outputs:
        outputs = (
            TaskIOField(name="result", type="object", description="Task result"),
        )
    boundaries = tuple(
        _normalize_boundary(item) for item in structure.execution_boundaries
    )
    boundaries = _dedupe_boundaries(boundaries)
    lifecycle = structure.lifecycle
    persistent = lifecycle.persistent or any(
        item.kind == "state" for item in boundaries
    )
    interaction = lifecycle.interaction
    if persistent and interaction == "single_run":
        interaction = "persistent_task"
    elif (
        any(item.kind in {"human_input", "human_approval"} for item in boundaries)
        and interaction == "single_run"
    ):
        interaction = "multi_turn"
    complexity = _complexity(boundaries, structure.actors)
    return TaskStructure(
        schema_version=SCHEMA_VERSION,
        goal=structure.goal.strip() or structure.summary.strip(),
        summary=structure.summary.strip() or structure.goal.strip(),
        actors=structure.actors or _default_actors(boundaries),
        stages=structure.stages
        or tuple(
            TaskStage(id=item.stage, summary=item.reason) for item in boundaries[:12]
        ),
        entities=structure.entities,
        inputs=inputs,
        outputs=outputs,
        execution_boundaries=boundaries,
        lifecycle=TaskLifecycle(
            persistent=persistent,
            interaction=interaction,
            entity=lifecycle.entity
            or (structure.state.entity if structure.state else ""),
        ),
        orchestration_complexity=complexity,
        uncertainty=structure.uncertainty,
        state=structure.state,
        user_requested_surface=structure.user_requested_surface,
        user_shape_override=structure.user_shape_override,
    )


def validate_task_structure(structure: TaskStructure) -> None:
    if not structure.goal.strip():
        raise ContractValidationError("task structure needs a goal")
    if not structure.outputs:
        raise ContractValidationError("task structure needs outputs")
    for boundary in structure.execution_boundaries:
        if boundary.kind == "condition":
            if not boundary.expression or len(boundary.branches) < 2:
                raise ContractValidationError(
                    "condition boundaries need an expression and branches"
                )
            parse_condition_expression(boundary.expression)
        if boundary.kind == "human_input" and not boundary.question:
            raise ContractValidationError("human_input needs a question")
        if boundary.kind == "human_approval" and not boundary.reason:
            raise ContractValidationError("human_approval needs a reason")
        if boundary.kind == "state" and not boundary.entity:
            raise ContractValidationError("state boundary needs an entity")


def user_requested_surface(text: str) -> str:
    """Preference only. Never locks product shape."""

    if _FORCE_AGENT.search(text):
        return "agent"
    if _SURFACE_WORKFLOW.search(text):
        return "workflow"
    if _SURFACE_AGENT.search(text):
        return "agent"
    return ""


def _deterministic_plan(text: str) -> TaskStructure:
    inputs = _infer_inputs(text)
    outputs = _infer_outputs(text, inputs)
    boundaries = _infer_boundaries(text, inputs)
    state = _infer_state(text)
    entities = (state.entity,) if state is not None else ()
    actors = _infer_actors(text, boundaries)
    stages = _infer_stages(text, boundaries)
    surface = user_requested_surface(text)
    override = "PURE_AGENT" if _FORCE_AGENT.search(text) else ""
    persistent = state is not None
    interaction: InteractionModeHint = "persistent_task" if persistent else "single_run"
    if any(item.kind in {"human_input", "human_approval"} for item in boundaries):
        interaction = "persistent_task" if persistent else "multi_turn"
    return TaskStructure(
        schema_version=SCHEMA_VERSION,
        goal=_goal(text),
        summary=text[:240],
        actors=actors,
        stages=stages,
        entities=entities,
        inputs=inputs,
        outputs=outputs,
        execution_boundaries=boundaries,
        lifecycle=TaskLifecycle(
            persistent=persistent,
            interaction=interaction,
            entity=state.entity if state else "",
        ),
        orchestration_complexity=_complexity(boundaries, actors),
        uncertainty=(),
        state=state,
        user_requested_surface=surface,
        user_shape_override=override,
    )


def _infer_inputs(text: str) -> tuple[TaskIOField, ...]:
    fields: list[TaskIOField] = []
    if _FOLDER.search(text):
        fields.append(
            TaskIOField(
                name="files",
                type="collection",
                multiple=True,
                cardinality="collection",
                description="Uploaded file collection",
                source="folder/files language",
            )
        )
    elif _MULTI_IMAGE.search(text):
        fields.append(
            TaskIOField(
                name="product-images",
                type="image",
                multiple=True,
                cardinality="multiple",
                description="Multiple product images",
                source="multi-image language",
            )
        )
    elif _IMAGE.search(text) and not _SEARCH_FOR_TOOL.search(text):
        fields.append(
            TaskIOField(
                name="image",
                type="image",
                multiple=False,
                source="image language",
            )
        )
    if _DOCUMENT.search(text) and not any(item.type == "document" for item in fields):
        name = "contract" if "合同" in text else "document"
        kind = "pdf" if re.search(r"\bpdf\b", text, re.I) else "document"
        fields.append(
            TaskIOField(
                name=name,
                type=kind,
                description="Uploaded document",
                source="document language",
            )
        )
    if _TABLE.search(text):
        fields.append(
            TaskIOField(
                name="table",
                type="table",
                description="Tabular file",
                source="table language",
            )
        )
    if _JSON.search(text) and "json" not in {item.name for item in fields}:
        fields.append(
            TaskIOField(
                name="payload",
                type="object",
                description="JSON object",
                source="json language",
            )
        )
    if not fields:
        fields.append(
            TaskIOField(
                name="text"
                if _TRANSLATE_ONLY.search(text) and not _SEARCH_FOR_TOOL.search(text)
                else "request",
                type="string",
                description="User text",
            )
        )
    elif not any(item.type == "string" for item in fields):
        fields.append(
            TaskIOField(
                name="message",
                type="string",
                required=False,
                description="Optional user message",
            )
        )
    return tuple(fields)


def _infer_outputs(
    text: str, inputs: tuple[TaskIOField, ...]
) -> tuple[TaskIOField, ...]:
    del inputs
    fields: list[TaskIOField] = []
    if (
        _TRANSLATE_ONLY.search(text)
        and not _WEB_SEARCH.search(text)
        and not _SEARCH_FOR_TOOL.search(text)
    ):
        fields.append(TaskIOField(name="translation", type="string"))
        return tuple(fields)
    if _IMAGE_GEN.search(text):
        fields.append(
            TaskIOField(
                name="render",
                type="image",
                description="Generated visual",
                source="image generation language",
            )
        )
    if _ANALYSIS_REPORT.search(text):
        fields.append(
            TaskIOField(
                name="analysis",
                type="object",
                description="Structured analysis",
                source="analysis-report language",
            )
        )
        return tuple(fields)
    if _RESEARCH_REPORT.search(text):
        fields.append(
            TaskIOField(
                name="report",
                type="object",
                description="Structured research report",
                source="research-report language",
            )
        )
        return tuple(fields)
    structured = bool(
        _STRUCTURED_OUTPUT.search(text)
        or _JSON.search(text)
        or _PERSIST.search(text)
        or _IMAGE_GEN.search(text)
    )
    fields.append(
        TaskIOField(
            name="result",
            type="object" if structured else "string",
            description="Task result",
        )
    )
    return tuple(fields)


def _infer_boundaries(
    text: str,
    inputs: tuple[TaskIOField, ...],
) -> tuple[ExecutionBoundary, ...]:
    items: list[ExecutionBoundary] = []
    needs_model = bool(
        any(item.type == "image" for item in inputs)
        or _WEB_SEARCH.search(text)
        or _WORKSPACE_SEARCH.search(text)
        or _WORKSPACE_READ.search(text)
        or _WORKSPACE_WRITE.search(text)
        or _SHELL.search(text)
        or _IMAGE_GEN.search(text)
        or _TRANSLATE_ONLY.search(text)
        or _NEEDS_MODEL.search(text)
    )
    if any(item.type == "image" for item in inputs):
        items.append(
            ExecutionBoundary(
                kind="multimodal",
                stage="vision",
                reason="Image input requires vision",
                source="image input",
                capability="vision",
            )
        )
    if _WEB_SEARCH.search(text):
        items.append(
            ExecutionBoundary(
                kind="tool",
                stage="search",
                reason="External lookup requires a search tool",
                capability="web_search",
                source="search language",
            )
        )
    if _GITHUB_READ.search(text):
        items.append(
            ExecutionBoundary(
                kind="tool",
                stage="github-read",
                reason="GitHub access requires github_read",
                capability="github_read",
                source="github language",
            )
        )
    if _GITHUB_WRITE.search(text):
        items.append(
            ExecutionBoundary(
                kind="tool",
                stage="github-write",
                reason="GitHub writes require github_write",
                capability="github_write",
                source="github write language",
            )
        )
    if _WORKSPACE_SEARCH.search(text):
        items.append(
            ExecutionBoundary(
                kind="tool",
                stage="workspace-search",
                reason="Project search requires workspace_search",
                capability="workspace_search",
                source="workspace search language",
            )
        )
    if _WORKSPACE_READ.search(text):
        items.append(
            ExecutionBoundary(
                kind="tool",
                stage="workspace-read",
                reason="Reading project files requires workspace_read",
                capability="workspace_read",
                source="workspace read language",
            )
        )
    if _WORKSPACE_WRITE.search(text):
        items.append(
            ExecutionBoundary(
                kind="tool",
                stage="workspace-write",
                reason="Editing files requires workspace_write",
                capability="workspace_write",
                source="workspace write language",
            )
        )
    if _SHELL.search(text):
        items.append(
            ExecutionBoundary(
                kind="tool",
                stage="shell",
                reason="Running commands requires shell_exec",
                capability="shell_exec",
                source="shell language",
            )
        )
    if _IMAGE_GEN.search(text):
        items.append(
            ExecutionBoundary(
                kind="tool",
                stage="generate-image",
                reason="Producing images requires image_generation",
                capability="image_generation",
                source="image generation language",
            )
        )
    if _KNOWLEDGE.search(text):
        items.append(
            ExecutionBoundary(
                kind="tool",
                stage="knowledge",
                reason="Project knowledge is requested",
                capability="project_knowledge",
                source="knowledge language",
            )
        )
    if _DOCUMENT_ANALYSIS.search(text):
        items.append(
            ExecutionBoundary(
                kind="tool",
                stage="document-analysis",
                reason="Document or brand-guideline analysis is a skill capability",
                capability="document_analysis",
                source="document analysis language",
            )
        )
    if _HTTP_REQUEST.search(text):
        items.append(
            ExecutionBoundary(
                kind="tool",
                stage="http-request",
                reason="An HTTP lookup requires http_request",
                capability="http_request",
                source="http language",
            )
        )
    if _RESEARCH_METHOD.search(text):
        items.append(
            ExecutionBoundary(
                kind="tool",
                stage="research-method",
                reason="Structured research method is requested",
                capability="research_planning",
                source="research method language",
            )
        )
        items.append(
            ExecutionBoundary(
                kind="tool",
                stage="evidence",
                reason="Evidence synthesis is requested",
                capability="evidence_synthesis",
                source="evidence language",
            )
        )
    seen_caps = {item.capability for item in items if item.capability}
    for match in _NAMED_CAPABILITY.finditer(text):
        name = match.group(1).casefold()
        if name in seen_caps or name in _MODEL_ONLY_CAPS:
            continue
        seen_caps.add(name)
        items.append(
            ExecutionBoundary(
                kind="tool",
                stage=name.replace("_", "-")[:80],
                reason="The request named a capability requirement",
                capability=name,
                source=match.group(0),
            )
        )
    if _TOOL_APPROVAL.search(text):
        caps = []
        if _WORKSPACE_WRITE.search(text):
            caps.append("workspace_write")
        if _SHELL.search(text):
            caps.append("shell_exec")
        for capability in caps or ["workspace_write"]:
            items.append(
                ExecutionBoundary(
                    kind="tool",
                    stage="tool-approval",
                    reason="Write/exec tools require runtime permission approval",
                    capability=capability,
                    approval_class="tool",
                    source="tool approval language",
                )
            )
    if _UNKNOWN_THEN_ASK.search(text) and not _SOFT_IF.search(text):
        items.append(
            ExecutionBoundary(
                kind="condition",
                stage="information-check",
                reason="Unknown identity must branch before continuing",
                question="Is the identifying field already known?",
                expression="model_known == true",
                branches=("complete", "missing_information"),
                source="unknown-then-ask language",
            )
        )
        items.append(
            ExecutionBoundary(
                kind="human_input",
                stage="request-missing",
                reason="Ask the user when required identity is missing",
                question="请补充缺失的识别信息",
                expected_schema={"model": "string"},
                source="unknown-then-ask language",
            )
        )
    if _BLURRY_RETRY.search(text):
        items.append(
            ExecutionBoundary(
                kind="condition",
                stage="image-quality",
                reason="Unusable images must branch to a recapture request",
                expression="image_quality_acceptable == true",
                branches=("acceptable", "request_new_images"),
                source="image quality language",
            )
        )
        items.append(
            ExecutionBoundary(
                kind="human_input",
                stage="request-new-images",
                reason="Ask the user to recapture images",
                question="请重新拍摄更清晰的照片",
                expected_schema={"product-images": "image"},
                source="image quality language",
            )
        )
    amount = _AMOUNT_GATE.search(text)
    if amount and not _SOFT_IF.search(text):
        raw = amount.group(4)
        scale = 10000 if amount.group(5) else 1
        threshold = int(float(raw) * scale)
        items.append(
            ExecutionBoundary(
                kind="condition",
                stage="amount-gate",
                reason="A numeric threshold must branch the process",
                expression=f"amount > {threshold}",
                branches=("needs_approval", "skip_approval"),
                source=amount.group(0),
            )
        )
    elif (
        len(_COMPARE_THEN.findall(text)) >= 2
        and not _SOFT_IF.search(text)
        and not any(item.kind == "condition" for item in items)
    ):
        items.append(
            ExecutionBoundary(
                kind="condition",
                stage="threshold-gate",
                reason="A comparative threshold must branch the process",
                expression="above_target == true",
                branches=("above", "below"),
                source="comparative branch language",
            )
        )
    business_match = _BUSINESS_APPROVAL.search(text)
    business = bool(business_match) and not bool(_TOOL_APPROVAL.search(text))
    persist = bool(_PERSIST.search(text))
    verify = bool(_VERIFY.search(text))
    if business and business_match is not None:
        items.append(
            ExecutionBoundary(
                kind="human_approval",
                stage="business-approval",
                reason="The user must confirm before the process continues",
                approval_class="business",
                source=business_match.group(0),
            )
        )
    if persist:
        entity = _entity_name(text)
        items.append(
            ExecutionBoundary(
                kind="state",
                stage="persist",
                reason="The task keeps a durable object across runs",
                entity=entity,
                scope="project",
                source="persistence language",
            )
        )
    if verify or persist or business:
        checks = ["output.not_empty"]
        if persist:
            checks.append("artifact_exists:entity_id")
        elif verify:
            checks.extend(("required_fields:result", "schema_valid"))
        items.append(
            ExecutionBoundary(
                kind="verification",
                stage="verify",
                reason="The result must be checked before finishing",
                checks=tuple(checks),
                source="verification language",
            )
        )
    structural = {item.kind for item in items} & {
        "condition",
        "human_approval",
        "human_input",
        "state",
        "verification",
    }
    if needs_model or not structural:
        items.insert(
            0,
            ExecutionBoundary(
                kind="reasoning",
                stage="reason",
                reason="The task needs model reasoning",
                source=text[:120],
            ),
        )
    return tuple(items)


def _infer_state(text: str) -> StateRequirement | None:
    if not _PERSIST.search(text):
        return None
    entity = _entity_name(text)
    identity = "item_id" if entity.endswith("Item") else "record_id"
    fields = {
        "title": "string",
        "status": "string",
        "notes": "string",
    }
    if "价格" in text or "price" in text.lower():
        fields["current_price"] = "number"
        fields["price_history"] = "object"
    if _IMAGE.search(text):
        fields["images"] = "artifact"
    statuses = (
        "identifying",
        "needs_information",
        "active",
        "awaiting_approval",
        "completed",
    )
    return StateRequirement(
        entity=entity,
        identity=identity,
        scope="project",
        fields=fields,
        statuses=statuses,
        revision=True,
        source="persistence language",
    )


def _infer_actors(
    text: str,
    boundaries: tuple[ExecutionBoundary, ...],
) -> tuple[TaskActor, ...]:
    caps = {
        item.capability
        for item in boundaries
        if item.capability and item.kind in {"tool", "multimodal"}
    }
    actors: list[TaskActor] = []
    if "vision" in caps:
        actors.append(
            TaskActor(
                id="analyzer",
                role="analyzer",
                capabilities=("vision", "structured_output"),
                reason="Vision and structured extraction are one role",
            )
        )
    if "web_search" in caps:
        actors.append(
            TaskActor(
                id="researcher",
                role="researcher",
                capabilities=("web_search", "evidence_synthesis"),
                reason="External search is a distinct tool role",
            )
        )
    if "image_generation" in caps:
        actors.append(
            TaskActor(
                id="renderer",
                role="renderer",
                capabilities=("image_generation",),
                reason="Image generation is a distinct capability boundary",
            )
        )
    workspace = caps & {
        "workspace_read",
        "workspace_search",
        "workspace_write",
        "shell_exec",
        "github_read",
        "github_write",
    }
    if workspace and not actors:
        actors.append(
            TaskActor(
                id="editor",
                role="editor",
                capabilities=tuple(sorted(workspace)),
                reason="Workspace tools share one editor role",
            )
        )
    if not actors:
        extra = tuple(
            sorted(
                cap
                for cap in caps
                if cap
                not in {
                    "vision",
                    "web_search",
                    "image_generation",
                    "workspace_read",
                    "workspace_search",
                    "workspace_write",
                    "shell_exec",
                    "github_read",
                    "github_write",
                }
            )
        )
        actors.append(
            TaskActor(
                id="main",
                role="assistant",
                capabilities=("text_generation", *extra),
                reason="A single reasoning role can complete this task",
            )
        )
    elif _needs_writer(text, caps):
        actors.append(
            TaskActor(
                id="writer",
                role="writer",
                capabilities=("text_generation",),
                reason="Listing or copy generation is a separate writing role",
            )
        )
    return tuple(actors)


def _needs_writer(text: str, caps: set[str]) -> bool:
    if "image_generation" in caps:
        return False
    listing = re.search(r"写介绍|文案|listing|上架内容", text, re.I)
    return bool(listing and ("web_search" in caps or "vision" in caps))


def _infer_stages(
    text: str,
    boundaries: tuple[ExecutionBoundary, ...],
) -> tuple[TaskStage, ...]:
    del text
    stages: list[TaskStage] = []
    seen: set[str] = set()
    for item in boundaries:
        if item.stage in seen:
            continue
        seen.add(item.stage)
        stages.append(TaskStage(id=item.stage, summary=item.reason, source=item.source))
    return tuple(stages[:12])


def _entity_name(text: str) -> str:
    if re.search(r"客户|线索|lead|customer", text, re.I):
        return "CustomerLead"
    if re.search(r"合同", text):
        return "ContractRecord"
    if re.search(r"二手", text):
        return "SecondhandItem"
    if re.search(r"商品|item", text, re.I):
        return "CatalogItem"
    return "ProjectEntity"


def _goal(text: str) -> str:
    match = re.search(
        r"(?:帮我)?(?:做|创建)(?:一个)?([^。．.!！\n，,]{2,40})",
        text,
    )
    if match:
        name = match.group(1).strip(" ，,")
        if 1 < len(name) <= 40:
            return name
    return text[:120]


def _normalize_io(item: TaskIOField) -> TaskIOField:
    name = re.sub(r"[^a-z0-9-]", "", item.name.casefold().replace("_", "-"))
    name = re.sub(r"-{2,}", "-", name).strip("-")
    if not name or name[0].isdigit():
        name = "field"
    multiple = item.multiple or item.cardinality in {"multiple", "collection"}
    cardinality = item.cardinality
    if multiple and cardinality == "single":
        cardinality = "collection" if item.type == "collection" else "multiple"
    return TaskIOField(
        name=name[:63],
        type=item.type,
        multiple=multiple,
        required=item.required,
        cardinality=cardinality,
        description=item.description,
        source=item.source,
    )


def _normalize_boundary(item: ExecutionBoundary) -> ExecutionBoundary:
    stage = re.sub(r"[^a-z0-9-]", "", item.stage.casefold().replace("_", "-"))
    stage = re.sub(r"-{2,}", "-", stage).strip("-") or "stage"
    return ExecutionBoundary(
        kind=item.kind,
        stage=stage[:80],
        reason=item.reason,
        required=item.required,
        question=item.question,
        expression=item.expression,
        branches=item.branches,
        checks=item.checks,
        capability=item.capability,
        entity=item.entity,
        scope=item.scope,
        source=item.source,
        approval_class=item.approval_class,
        expected_schema=item.expected_schema,
    )


def _dedupe_boundaries(
    items: tuple[ExecutionBoundary, ...],
) -> tuple[ExecutionBoundary, ...]:
    seen: set[tuple[str, str, str]] = set()
    result: list[ExecutionBoundary] = []
    for item in items:
        key = (item.kind, item.stage, item.capability or item.expression)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return tuple(result)


def _default_actors(
    boundaries: tuple[ExecutionBoundary, ...],
) -> tuple[TaskActor, ...]:
    return _infer_actors("", boundaries)


def _complexity(
    boundaries: tuple[ExecutionBoundary, ...],
    actors: tuple[TaskActor, ...],
) -> OrchestrationComplexity:
    kinds = {item.kind for item in boundaries}
    structural = kinds & {
        "condition",
        "human_approval",
        "human_input",
        "state",
        "verification",
    }
    if len(actors) >= 3 and structural:
        return "multi_actor"
    if structural:
        return "branched"
    return "single"


_PLANNER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["schema_version", "goal", "summary", "lifecycle"],
}
