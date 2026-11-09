"""Derive Capability Requirements from AgentSpecification plus requirement text.

This layer names capabilities, never catalog resource IDs. Domain occupations
such as gift, research assistant, packaging, or translation are not resource maps.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from veyra_agent_platform.contracts.agent_spec import AgentSpecification
from veyra_agent_platform.contracts.capability import CapabilityRequirement

_CLAIMED_RESOURCE = re.compile(
    r"veyra\.(?:tool|skill|policy|mcp)[a-z0-9_.-]*(?:@[0-9]+\.[0-9]+\.[0-9]+)?"
)

_SPEC_ALIASES = {
    "filesystem_read": "workspace_read",
    "filesystem_write": "workspace_write",
    "knowledge_access": "project_knowledge",
    "image_understanding": "vision",
}

_PROFILES: dict[str, dict[str, object]] = {
    "arithmetic": {
        "input_types": ("string",),
        "output_types": ("number",),
        "side_effect": "none",
    },
    "web_search": {
        "input_types": ("string",),
        "output_types": ("object",),
        "network": "required",
        "side_effect": "read",
    },
    "http_request": {
        "input_types": ("string",),
        "output_types": ("object",),
        "network": "required",
        "side_effect": "read",
        "approval": "required",
    },
    "browser_navigate": {
        "input_types": ("string",),
        "output_types": ("object",),
        "network": "required",
        "side_effect": "read",
    },
    "workspace_read": {
        "input_types": ("string",),
        "output_types": ("string",),
        "filesystem": "read",
        "side_effect": "read",
    },
    "workspace_search": {
        "input_types": ("string",),
        "output_types": ("array",),
        "filesystem": "read",
        "side_effect": "read",
    },
    "workspace_list": {
        "input_types": ("string",),
        "output_types": ("array",),
        "filesystem": "read",
        "side_effect": "read",
    },
    "workspace_write": {
        "input_types": ("string",),
        "output_types": ("object",),
        "filesystem": "write",
        "side_effect": "write",
        "approval": "required",
    },
    "shell_exec": {
        "input_types": ("string",),
        "output_types": ("object",),
        "filesystem": "write",
        "side_effect": "write",
        "approval": "required",
    },
    "github_read": {
        "input_types": ("string",),
        "output_types": ("object",),
        "network": "required",
        "side_effect": "read",
    },
    "github_write": {
        "input_types": ("string",),
        "output_types": ("object",),
        "network": "required",
        "side_effect": "write",
        "approval": "required",
    },
    "mcp_call": {
        "network": "required",
        "side_effect": "read",
    },
    "research_planning": {"side_effect": "none"},
    "evidence_synthesis": {"side_effect": "none"},
    "document_analysis": {"side_effect": "read"},
    "content_planning": {"side_effect": "none"},
    "need_extraction": {"side_effect": "none"},
    "file_taxonomy": {"side_effect": "none"},
    "project_knowledge": {"side_effect": "read"},
    "image_generation": {
        "output_types": ("image",),
        "model_capability": "image_generation",
    },
    "local_only": {"network": "none"},
    "verification_required": {"side_effect": "none"},
    "external_write_approval": {"approval": "required", "side_effect": "write"},
    "entity_read": {
        "input_types": ("string",),
        "output_types": ("object",),
        "side_effect": "read",
    },
    "entity_query": {
        "input_types": ("string",),
        "output_types": ("array",),
        "side_effect": "read",
    },
    "entity_history": {
        "input_types": ("string",),
        "output_types": ("array",),
        "side_effect": "read",
    },
    "entity_write": {
        "input_types": ("object",),
        "output_types": ("object",),
        "side_effect": "write",
    },
}

_SIGNALS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "web_search",
        re.compile(
            r"搜索公开(?:网页|资料|信息)|搜索网页|网页搜索|公开资料|"
            r"web search|search the (?:public )?web",
            re.IGNORECASE,
        ),
    ),
    (
        "workspace_search",
        re.compile(
            r"搜索项目文件|搜索当前项目文件|搜索工作区|"
            r"搜索.{0,24}(?:项目|Project|工作区).{0,8}文件|"
            r"filesystem search|search (?:project |workspace )?files",
            re.IGNORECASE,
        ),
    ),
    (
        "workspace_read",
        re.compile(
            r"读取相关文件|读取项目文件|读取工作区|阅读代码|阅读文件|"
            r"读取.{0,16}(?:项目|Project|工作区).{0,8}文件|"
            r"filesystem read|read (?:project |workspace )?files|read code",
            re.IGNORECASE,
        ),
    ),
    (
        "workspace_write",
        re.compile(
            r"修改(?:项目|Project|工作区|指定).{0,8}文件|"
            r"修改.{0,16}(?:项目|Project|工作区).{0,8}文件|"
            r"写入(?:之前|文件)|写文件|filesystem write|"
            r"save (?:changes )?to (?:project )?files",
            re.IGNORECASE,
        ),
    ),
    (
        "workspace_list",
        re.compile(r"列出文件|list (?:project )?files", re.IGNORECASE),
    ),
    (
        "github_read",
        re.compile(
            r"github(?:\s+repository)?(?:\s+read)?|读取.{0,12}github|"
            r"仓库读取|repository read",
            re.IGNORECASE,
        ),
    ),
    (
        "github_write",
        re.compile(r"github write|写入.{0,12}github|repository write", re.IGNORECASE),
    ),
    (
        "shell_exec",
        re.compile(
            r"shell\.exec|运行(?:测试)?命令|执行(?:测试)?命令|"
            r"运行测试|执行测试|run (?:the )?tests|workspace shell",
            re.IGNORECASE,
        ),
    ),
    (
        "http_request",
        re.compile(r"http\.request|调用 http|http request", re.IGNORECASE),
    ),
    (
        "browser_navigate",
        re.compile(r"browser\.navigate|打开网页|navigate (?:to )?url", re.IGNORECASE),
    ),
    (
        "research_planning",
        re.compile(
            r"研究报告|研究方法|research brief|研究规划|structured research report",
            re.IGNORECASE,
        ),
    ),
    (
        "evidence_synthesis",
        re.compile(r"整理证据|evidence synthesis|证据台账", re.IGNORECASE),
    ),
    (
        "document_analysis",
        re.compile(
            r"分析文档|document analysis|document analyzer|"
            r"品牌规范|设计规范|brand guidelines",
            re.IGNORECASE,
        ),
    ),
    (
        "project_knowledge",
        re.compile(
            r"project knowledge|项目知识|项目资料|项目里的|项目中的|"
            r"当前项目中|当前 project knowledge|knowledge_access",
            re.IGNORECASE,
        ),
    ),
    (
        "image_generation",
        re.compile(
            r"生成最终.{0,16}(?:图片|图像)|image generation|生成包装设计图片",
            re.IGNORECASE,
        ),
    ),
)

_NAMED_CAPABILITY = re.compile(
    r"(?:capability|能力)\s*[:=]\s*`?([a-z][a-z0-9_]{2,62})`?",
    re.IGNORECASE,
)
_DENY_WRITE = re.compile(
    r"不能修改|不得修改|不要修改|不可修改|read-?only|只读",
    re.IGNORECASE,
)
_SKIP_FROM_SPEC = frozenset(
    {
        "text_generation",
        "vision",
        "image_understanding",
        "document_understanding",
        "structured_output",
        "human_approval",
        "tool_calling",
        "filesystem_read",
        "filesystem_write",
    }
)


def derive_capability_requirements(
    specification: AgentSpecification,
    requirement: str = "",
) -> tuple[CapabilityRequirement, ...]:
    """Build capability needs from the specification and capability-oriented text."""

    haystack = " ".join(
        part
        for part in (
            requirement,
            specification.goal,
            specification.description,
            " ".join(specification.responsibilities),
        )
        if part
    )
    names: list[str] = []
    for capability in specification.required_capabilities:
        mapped = _SPEC_ALIASES.get(capability, capability)
        if mapped in _SKIP_FROM_SPEC and capability in {
            "text_generation",
            "vision",
            "image_understanding",
            "document_understanding",
            "structured_output",
            "human_approval",
            "tool_calling",
        }:
            continue
        names.append(mapped)
    for capability, pattern in _SIGNALS:
        if pattern.search(haystack):
            names.append(capability)
    for match in _NAMED_CAPABILITY.finditer(haystack):
        names.append(match.group(1))
    if any(item.type == "image" for item in specification.outputs):
        names.append("image_generation")
    unique = list(dict.fromkeys(names))
    if _DENY_WRITE.search(haystack):
        unique = [item for item in unique if item != "workspace_write"]
    return tuple(requirement_for(name) for name in unique)


def claimed_resource_references(*texts: str) -> tuple[str, ...]:
    """Extract hallucinated or copied catalog IDs from free text. Never trust them."""

    found: list[str] = []
    for text in texts:
        for match in _CLAIMED_RESOURCE.finditer(text or ""):
            token = match.group(0)
            if token not in found:
                found.append(token)
    return tuple(found)


def requirement_for(capability: str) -> CapabilityRequirement:
    profile = dict(_PROFILES.get(capability) or {})
    if capability.endswith(("_lookup", "_fetch", "_http")):
        profile.setdefault("network", "required")
        profile.setdefault("side_effect", "read")
        profile.setdefault("approval", "required")
    return CapabilityRequirement(
        capability=capability,
        required=True,
        input_types=tuple(profile.get("input_types") or ()),  # type: ignore[arg-type]
        output_types=tuple(profile.get("output_types") or ()),  # type: ignore[arg-type]
        side_effect=str(profile.get("side_effect") or "none"),  # type: ignore[arg-type]
        network=str(profile.get("network") or "none"),  # type: ignore[arg-type]
        filesystem=str(profile.get("filesystem") or "none"),  # type: ignore[arg-type]
        approval=str(profile.get("approval") or "none"),  # type: ignore[arg-type]
        model_capability=(
            str(profile["model_capability"])
            if profile.get("model_capability")
            else None
        ),
    )


def merge_requirements(
    items: Iterable[CapabilityRequirement],
) -> tuple[CapabilityRequirement, ...]:
    seen: dict[str, CapabilityRequirement] = {}
    for item in items:
        seen.setdefault(item.capability, item)
    return tuple(seen.values())
