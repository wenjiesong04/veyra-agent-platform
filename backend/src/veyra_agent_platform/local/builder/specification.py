"""Server-owned AgentSpecification inference and completeness checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from veyra_agent_platform.contracts.agent_spec import (
    PLATFORM_CAPABILITIES,
    SPECIFICATION_GAP_KEYS,
    AgentSpecification,
)
from veyra_agent_platform.contracts.semantic_plan import SemanticField
from veyra_agent_platform.contracts.typed_io import COMPACT_TYPES

CompletenessStatus = Literal["complete", "needs_clarification"]
EXPRESSIBLE_CAPABILITIES = frozenset(PLATFORM_CAPABILITIES)
UNSUPPORTED_CAPABILITY_NEEDLES = (
    "audio",
    "video",
    "browser automation",
    "浏览器自动化",
    "语音",
    "视频",
)
_APPROVAL = re.compile(
    r"确认|批准|审批|同意后再|让我确认|人工确认|用户确认|approve|confirm",
    re.IGNORECASE,
)
_REJECT = re.compile(r"拒绝|不满意|修改一次|revision|reject", re.IGNORECASE)
_AUTO = re.compile(r"不要问我|无需确认|自动生成|不要人工", re.IGNORECASE)
_MULTI_CONCEPT = re.compile(r"多个|几套|几种|多套|directions|options", re.IGNORECASE)
_IMAGE_IN = re.compile(
    r"照片|图片|图像|上传.{0,8}图|item image|product photo|upload.{0,12}image",
    re.IGNORECASE,
)
_IMAGE_OUT = re.compile(
    r"效果图|视觉图|生成.{0,12}图|预览图|image generation|advertisement visual",
    re.IGNORECASE,
)
_PDF = re.compile(r"\bpdf\b|上传.{0,8}pdf", re.IGNORECASE)
_SHEET = re.compile(r"excel|xlsx|spreadsheet|表格|销售数据", re.IGNORECASE)
_DOC = re.compile(r"文档|document|word", re.IGNORECASE)
_SUMMARY = re.compile(r"摘要|总结|summar", re.IGNORECASE)
_KEY_POINTS = re.compile(r"关键点|key points?", re.IGNORECASE)
_COPY = re.compile(r"文案|稿|copy", re.IGNORECASE)
_ANALYSIS = re.compile(r"分析|类型、颜色|材质|视觉风格", re.IGNORECASE)
_PACKAGING = re.compile(r"包装|gift wrap|packaging", re.IGNORECASE)
_TRANSLATE = re.compile(r"翻译|translate|中文翻译成|翻译成", re.IGNORECASE)
_MEETING = re.compile(r"会议纪要|会议记录|meeting notes", re.IGNORECASE)
_RESEARCH = re.compile(
    r"研究助手|研究分析助手|研究报告|搜索网页|网页搜索|web search|整理成报告",
    re.IGNORECASE,
)
_OCCASION = re.compile(r"场合|occasion", re.IGNORECASE)
_RECIPIENT = re.compile(r"收礼|接收者|recipient", re.IGNORECASE)
_BUDGET = re.compile(r"预算|budget", re.IGNORECASE)
_STYLE = re.compile(r"风格|style", re.IGNORECASE)
_WRITE_FILE = re.compile(
    r"写入文件|写入之前|写文件|保存到磁盘|filesystem write|"
    r"修改(?:项目|Project|工作区|指定).{0,8}文件|"
    r"修改.{0,16}(?:项目|Project|工作区).{0,8}文件",
    re.IGNORECASE,
)
_READ_FILE = re.compile(
    r"读取相关文件|读取项目文件|读取工作区|阅读代码|阅读文件|"
    r"读取.{0,16}(?:项目|Project|工作区).{0,8}文件|filesystem read|read code",
    re.IGNORECASE,
)
_WEB_SEARCH = re.compile(
    r"搜索公开(?:网页|资料|信息)|搜索网页|网页搜索|公开资料|"
    r"web search|search the (?:public )?web",
    re.IGNORECASE,
)
_WORKSPACE_SEARCH = re.compile(
    r"搜索项目文件|搜索当前项目文件|搜索工作区|"
    r"搜索.{0,24}(?:项目|Project|工作区).{0,8}文件|filesystem search|"
    r"search (?:project |workspace )?files",
    re.IGNORECASE,
)
_GITHUB_READ = re.compile(
    r"github(?:\s+repository)?(?:\s+read)?|仓库读取|repository read",
    re.IGNORECASE,
)
_SHELL_EXEC = re.compile(
    r"shell\.exec|运行(?:测试)?命令|执行(?:测试)?命令|"
    r"运行测试|执行测试|run (?:the )?tests",
    re.IGNORECASE,
)
_RESEARCH_PLAN = re.compile(
    r"研究报告|研究方法|research brief|研究规划|structured research report",
    re.IGNORECASE,
)
_EVIDENCE = re.compile(r"整理证据|evidence synthesis|证据台账", re.IGNORECASE)
_DOCUMENT_ANALYSIS = re.compile(
    r"分析文档|document analysis|document analyzer|"
    r"品牌规范|设计规范|brand guidelines",
    re.IGNORECASE,
)
_PROJECT_KNOWLEDGE = re.compile(
    r"project knowledge|项目知识|项目资料|项目里的|项目中的|"
    r"当前项目中|当前 project knowledge|knowledge_access",
    re.IGNORECASE,
)
_DENY_WRITE = re.compile(
    r"不能修改|不得修改|不要修改|不可修改|read-?only|只读", re.IGNORECASE
)
_FORBIDDEN_TOKENS = ("node id", "edge id", "api_key", "authorization", "secret")


@dataclass(frozen=True)
class SpecificationCompleteness:
    status: CompletenessStatus
    missing: tuple[str, ...]
    specification: AgentSpecification | None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "missing": list(self.missing),
            "specification": (
                self.specification.to_dict() if self.specification is not None else None
            ),
        }


def platform_capability_manifest() -> tuple[str, ...]:
    return PLATFORM_CAPABILITIES


def compact_field_types() -> tuple[str, ...]:
    return tuple(sorted(COMPACT_TYPES - {"audio", "video"}))


def infer_agent_specification(requirement: str) -> AgentSpecification:
    text = " ".join(requirement.split()).strip()
    folded = text.casefold()
    inputs = _infer_inputs(text, folded)
    outputs = _infer_outputs(text, folded)
    capabilities = _infer_capabilities(text, folded, inputs, outputs)
    interactions = _infer_interactions(text, capabilities)
    name = _suggested_name(text, folded)
    goal = _goal(text, folded)
    description = goal
    responsibilities = _responsibilities(text, folded, capabilities)
    success = _success_criteria(text, folded, inputs, outputs, capabilities)
    return AgentSpecification(
        schema_version="1.0",
        goal=goal,
        suggested_name=name,
        description=description,
        inputs=tuple(inputs),
        outputs=tuple(outputs),
        responsibilities=tuple(responsibilities),
        human_interactions=tuple(interactions),
        required_capabilities=tuple(capabilities),
        success_criteria=tuple(success),
    )


def check_specification_completeness(
    spec: AgentSpecification,
    *,
    requirement: str = "",
) -> SpecificationCompleteness:
    missing: list[str] = []
    if not spec.goal.strip():
        missing.append("goal")
    if not spec.outputs:
        missing.append("output")
    allowed = set(compact_field_types())
    if any(item.type not in allowed for item in spec.inputs):
        missing.append("input_type")
    if any(item.type not in allowed for item in spec.outputs):
        missing.append("output_type")
    unknown = [
        name
        for name in spec.required_capabilities
        if name not in EXPRESSIBLE_CAPABILITIES
    ]
    if unknown:
        missing.append("required_capability")
    if not spec.success_criteria:
        missing.append("success_criteria")
    haystack = f"{requirement}\n{spec.goal}\n{spec.description}".casefold()
    if any(token in haystack for token in UNSUPPORTED_CAPABILITY_NEEDLES):
        missing.append("unsupported_capability")
    if _AUTO.search(haystack) and _APPROVAL.search(haystack):
        missing.append("contradictory_requirements")
    if _needs_approval_question(requirement, spec):
        missing.append("approval_requirement")
    unique = tuple(item for item in missing if item in SPECIFICATION_GAP_KEYS)
    status: CompletenessStatus = "complete" if not unique else "needs_clarification"
    return SpecificationCompleteness(
        status=status,
        missing=unique,
        specification=spec if status == "complete" else spec,
    )


def resolve_agent_specification(requirement: str) -> SpecificationCompleteness:
    spec = infer_agent_specification(requirement)
    return check_specification_completeness(spec, requirement=requirement)


def _field(
    name: str,
    type_name: str,
    *,
    required: bool = True,
    description: str = "",
) -> SemanticField:
    return SemanticField(
        name=name,
        type=type_name,  # type: ignore[arg-type]
        description=description,
        required=required,
    )


def _infer_inputs(text: str, folded: str) -> list[SemanticField]:
    fields: list[SemanticField] = []

    def add(field: SemanticField) -> None:
        if all(item.name != field.name for item in fields):
            fields.append(field)

    if _IMAGE_IN.search(text):
        name = "item_image" if _PACKAGING.search(text) else "product_image"
        if "商品" in text or "产品" in text:
            name = "product_image"
        add(
            _field(
                name,
                "image",
                description="User-uploaded photograph of the subject",
            )
        )
        if "品牌" in text:
            add(_field("brand_name", "string", description="Brand or product name"))
        if _ANALYSIS.search(text) and not _IMAGE_OUT.search(text):
            add(
                _field("message", "string", description="Analysis request or follow-up")
            )
    if _PDF.search(text) and not _SHEET.search(text):
        add(_field("source_pdf", "pdf", description="Uploaded PDF document"))
    if _SHEET.search(text):
        add(
            _field(
                "spreadsheet",
                "document",
                description="Uploaded spreadsheet or table file",
            )
        )
    elif _DOC.search(text) and not _PDF.search(text) and not _IMAGE_IN.search(text):
        add(_field("document", "document", description="Uploaded document"))
    if _OCCASION.search(text):
        add(_field("occasion", "string", description="Occasion or event"))
    if _RECIPIENT.search(text):
        add(_field("recipient", "string", description="Intended recipient"))
    if _BUDGET.search(text):
        add(
            _field(
                "budget",
                "string",
                required=False,
                description="Optional budget guidance",
            )
        )
    if _STYLE.search(text):
        add(
            _field(
                "style_preferences",
                "string",
                required=False,
                description="Optional style preferences",
            )
        )
    if _PACKAGING.search(text) and "描述" in text:
        add(
            _field(
                "item_description",
                "string",
                required=False,
                description="Optional text description of the item",
            )
        )
    if _REJECT.search(text) and _APPROVAL.search(text):
        add(
            _field(
                "revision_feedback",
                "string",
                required=False,
                description="Optional revision notes after rejection",
            )
        )
    if _SUMMARY.search(text) and not fields:
        add(_field("article", "string", description="Source article or text"))
    if _COPY.search(text) and not fields:
        add(_field("briefing", "string", description="Campaign or copy briefing"))
    if _TRANSLATE.search(text) and not fields:
        add(_field("text", "string", description="Source text to translate"))
    if _RESEARCH.search(text) and not fields:
        add(_field("query", "string", description="Research question or topic"))
    if not fields:
        add(_field("request", "string", description="Primary user request"))
    return fields


def _infer_outputs(text: str, folded: str) -> list[SemanticField]:
    fields: list[SemanticField] = []

    def add(field: SemanticField) -> None:
        if all(item.name != field.name for item in fields):
            fields.append(field)

    if _PACKAGING.search(text):
        if _IMAGE_OUT.search(text):
            add(
                _field(
                    "packaging_design",
                    "object",
                    description="Complete packaging design proposal",
                )
            )
            add(
                _field(
                    "packaging_preview",
                    "image",
                    description="Final packaging visual",
                )
            )
            return fields
        if _ANALYSIS.search(text) or _IMAGE_IN.search(text):
            add(
                _field(
                    "analysis",
                    "object",
                    description="Structured visual, material, and brand analysis",
                )
            )
            return fields
        add(
            _field(
                "packaging_design",
                "object",
                description="Complete packaging design proposal",
            )
        )
        return fields
    if _MEETING.search(text):
        add(_field("summary", "string", description="会议摘要"))
        add(_field("decisions", "string", description="会议决定"))
        add(_field("todos", "string", description="待办事项"))
        return fields
    if _SUMMARY.search(text):
        add(_field("summary", "string", description="Short summary of the source"))
        if _KEY_POINTS.search(text):
            add(_field("key_points", "array", description="Three key points"))
        return fields
    if _SHEET.search(text):
        add(_field("summary", "object", description="Sales or table summary"))
        add(_field("anomalies", "array", description="Detected anomalies"))
        return fields
    if _PDF.search(text) or (_DOC.search(text) and _SUMMARY.search(text)):
        add(_field("summary", "string", description="Extracted highlights and summary"))
        return fields
    if _IMAGE_OUT.search(text) and not _PACKAGING.search(text):
        if _ANALYSIS.search(text) or _IMAGE_IN.search(text):
            add(
                _field(
                    "analysis",
                    "object",
                    description="Structured visual analysis of the product",
                )
            )
        add(
            _field(
                "advertisement", "image", description="Generated advertisement visual"
            )
        )
        return fields
    if _IMAGE_IN.search(text) and _ANALYSIS.search(text):
        add(
            _field(
                "analysis",
                "object",
                description="Product type, color, material, and visual style",
            )
        )
        return fields
    if _COPY.search(text):
        add(_field("final_copy", "string", description="Final approved copy"))
        return fields
    if _TRANSLATE.search(text):
        add(_field("translation", "string", description="Natural translation"))
        return fields
    if _RESEARCH.search(text):
        if "结构化" in text:
            add(_field("report", "object", description="Structured research report"))
        else:
            add(_field("report", "string", description="Researched report"))
        return fields
    add(_field("result", "string", description="Primary Agent result"))
    return fields


def _infer_capabilities(
    text: str,
    folded: str,
    inputs: list[SemanticField],
    outputs: list[SemanticField],
) -> list[str]:
    found = ["text_generation"]
    if any(item.type == "image" for item in inputs):
        found.append("vision")
        found.append("image_understanding")
    if any(
        item.type in {"pdf", "document", "file", "collection", "table"}
        for item in inputs
    ):
        found.append("document_understanding")
    if any(item.type == "image" for item in outputs):
        found.append("image_generation")
    if any(item.type in {"object", "array", "table"} for item in outputs):
        found.append("structured_output")
    if _APPROVAL.search(text):
        found.append("human_approval")
    if _WRITE_FILE.search(text) and not _DENY_WRITE.search(text):
        found.append("filesystem_write")
        found.append("workspace_write")
        found.append("human_approval")
    if _READ_FILE.search(text):
        found.append("filesystem_read")
        found.append("workspace_read")
    if _WORKSPACE_SEARCH.search(text):
        found.append("workspace_search")
        found.append("filesystem_read")
    if _WEB_SEARCH.search(text):
        found.append("web_search")
        found.append("tool_calling")
    if _GITHUB_READ.search(text):
        found.append("github_read")
    if _SHELL_EXEC.search(text):
        found.append("shell_exec")
        found.append("human_approval")
    if _RESEARCH_PLAN.search(text):
        found.append("research_planning")
    if _EVIDENCE.search(text):
        found.append("evidence_synthesis")
    if _DOCUMENT_ANALYSIS.search(text):
        found.append("document_analysis")
    if _PROJECT_KNOWLEDGE.search(text):
        found.append("project_knowledge")
        found.append("knowledge_access")
    if _DENY_WRITE.search(text):
        found = [
            item
            for item in found
            if item not in {"filesystem_write", "workspace_write"}
        ]
    return list(dict.fromkeys(found))


def _infer_interactions(text: str, capabilities: list[str]) -> list[str]:
    if "human_approval" not in capabilities:
        return []
    if _REJECT.search(text):
        return ["Approve a proposed direction before the final result"]
    return ["Confirm the draft before producing the final result"]


def _needs_approval_question(requirement: str, spec: AgentSpecification) -> bool:
    if "human_approval" in spec.required_capabilities:
        return False
    if not any(item.type == "image" for item in spec.outputs):
        return False
    if not _MULTI_CONCEPT.search(requirement):
        return False
    return not _APPROVAL.search(requirement) and not _AUTO.search(requirement)


def _suggested_name(text: str, folded: str) -> str:
    if _TRANSLATE.search(text):
        return "Translation Agent"
    if _MEETING.search(text):
        return "会议纪要整理 Agent"
    if _RESEARCH.search(text):
        return "Research Agent"
    if _PACKAGING.search(text):
        return "Packaging Designer Agent"
    if _SUMMARY.search(text) and _KEY_POINTS.search(text):
        return "文章摘要 Agent"
    if _IMAGE_IN.search(text) and _IMAGE_OUT.search(text):
        return "广告视觉生成 Agent"
    if _IMAGE_IN.search(text) and _ANALYSIS.search(text):
        return "商品视觉分析 Agent"
    if _PDF.search(text):
        return "PDF 摘要 Agent"
    if _SHEET.search(text):
        return "销售数据分析 Agent"
    if _COPY.search(text):
        return "宣传文案 Agent"
    clipped = text[:24].strip() or "Agent"
    return f"{clipped} Agent"


def _goal(text: str, folded: str) -> str:
    del folded
    if not text:
        return ""
    return text[:400]


def _responsibilities(text: str, folded: str, capabilities: list[str]) -> list[str]:
    items: list[str] = []
    if "vision" in capabilities:
        items.append("Understand uploaded images")
    if "document_understanding" in capabilities:
        items.append("Read uploaded documents")
    if "structured_output" in capabilities:
        items.append("Return structured results")
    if "human_approval" in capabilities:
        items.append("Wait for an explicit human approval")
    if "image_generation" in capabilities:
        items.append("Generate a final image")
    if not items:
        items.append("Produce the requested result")
    return items[:12]


def _success_criteria(
    text: str,
    folded: str,
    inputs: list[SemanticField],
    outputs: list[SemanticField],
    capabilities: list[str],
) -> list[str]:
    items: list[str] = []
    if any(item.type == "image" for item in inputs):
        items.append("The Agent can identify the uploaded image")
    if _PACKAGING.search(text):
        items.extend(
            [
                "Packaging advice relates to the item's features",
                "Multiple design directions are provided",
            ]
        )
    if "human_approval" in capabilities:
        items.append("A final design is produced only after user confirmation")
    if any(item.type == "image" for item in outputs):
        items.append("The run produces a real image output")
    if _REJECT.search(text):
        items.append("A rejected or revision path can complete one revision")
    if _SUMMARY.search(text):
        items.append("The summary covers the source text")
    if _KEY_POINTS.search(text):
        items.append("Three key points are returned")
    if _TRANSLATE.search(text):
        items.append("The translation is natural English")
    if _RESEARCH.search(text):
        items.append("The report is based on permitted web search")
    if not items:
        items.append("The declared outputs are produced")
    return items[:8]


def assert_no_implementation_leak(spec: AgentSpecification) -> None:
    blob = str(spec.to_dict()).casefold()
    for token in _FORBIDDEN_TOKENS:
        if token in blob:
            raise ValueError(f"specification leaked {token}")
