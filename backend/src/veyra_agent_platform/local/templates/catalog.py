"""Safe built-in Agent templates available to local Projects."""

from __future__ import annotations

from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.domain.agent_definition import merge_catalog_bindings
from veyra_agent_platform.local.projects.layout import attach_default_canvas_note
from veyra_agent_platform.local.resources import ResourceCatalog

STARTER_TEMPLATE_ID = "veyra.starter-agent@1.0.0"
DOCUMENT_DISTILLER_TEMPLATE_ID = "veyra.document-distiller@1.0.0"
QUESTION_RESEARCHER_TEMPLATE_ID = "veyra.question-researcher@1.0.0"
FILE_SORT_PLANNER_TEMPLATE_ID = "veyra.file-sort-planner@1.0.0"
_RUNTIME_LOCK_DIGEST = "0" * 64
_EMPTY_PERMISSIONS: dict[str, Any] = {
    "network_hosts": [],
    "tools": [],
    "filesystem_read_roots": [],
    "filesystem_write_roots": [],
    "shell_workspace_only": False,
}

_STARTER_SOURCE: dict[str, Any] = {
    "schema_version": "1.0",
    "agentspec_version": "26.1",
    "component_type": "Flow",
    "agent_id": "01a03795-a5b0-7f61-a971-4c55cead5f27",
    "slug": "starter-agent",
    "name": "Starter Agent",
    "description": "A safe local-first starting point for a new Agent.",
    "inputs": {"request": "string"},
    "outputs": {"result": "string"},
    "nodes": [
        {"id": "start", "component_type": "Start"},
        {
            "id": "model",
            "component_type": "Model",
            "model_ref": "model.primary",
            "system_prompt": "Complete the request and return a concise result.",
        },
        {
            "id": "output",
            "component_type": "Output",
            "output_name": "result",
        },
    ],
    "transitions": [
        {"from": "start", "port": "next", "to": "model"},
        {"from": "model", "port": "next", "to": "output"},
    ],
    "extensions": {
        "veyra": {
            "runtime_profile": "veyra-runtime-profile/1",
            "secret_refs": [],
            "permissions": dict(_EMPTY_PERMISSIONS),
            "verification": {"required": False, "checks": []},
            "skill_refs": [],
            "policy_refs": [],
        }
    },
    "ui": attach_default_canvas_note(
        {
            "positions": {
                "start": {"x": 0, "y": 80},
                "model": {"x": 240, "y": 80},
                "output": {"x": 480, "y": 80},
            }
        },
        "A safe local-first starting point. Describe this Agent's purpose, "
        "inputs, outputs, and how to use it.",
    ),
    "lock": {"veyra.runtime.profile@1.0.0": _RUNTIME_LOCK_DIGEST},
}


class AgentTemplateError(ValueError):
    """A template selection is unknown or violates the safe catalog contract."""


class AgentTemplateCatalog:
    """Return validated copies of platform-owned, versioned Agent templates."""

    def __init__(self, resources: ResourceCatalog | None = None) -> None:
        catalog = resources or ResourceCatalog()
        sources = {
            STARTER_TEMPLATE_ID: AgentSource.from_dict(_STARTER_SOURCE),
            DOCUMENT_DISTILLER_TEMPLATE_ID: _work_template(
                catalog,
                agent_id="01a05129-5e8c-7b16-9073-e2bb69930b0a",
                slug="document-distiller",
                name="文档提炼",
                description=(
                    "把长文档或粘贴文本，提炼成你真正需要的结论、证据和待确认项。"
                    "不编造原文没有的事实。"
                ),
                inputs={"source": "string", "need": "string"},
                output="brief",
                prompt=(
                    "你把长材料提炼成用户真正需要的信息。先读 need，再读 source。"
                    "两者冲突时以 need 为准。输出一份马上能用的 brief：结论、"
                    "必须保留的证据、可忽略的内容、待确认项。不要用空泛摘要凑字数。"
                ),
                skill_refs=(
                    "veyra.skill.document-analyzer@1.0.0",
                    "veyra.skill.need-extractor@1.0.0",
                ),
            ),
            QUESTION_RESEARCHER_TEMPLATE_ID: _work_template(
                catalog,
                agent_id="01a05129-5e8c-78d4-a6d3-86906f0f378f",
                slug="question-researcher",
                name="问题研究",
                description=(
                    "根据你的问题和已有材料，整理已知、未知、证据和下一步。"
                    "当前不会上网搜索，也不编造来源。"
                ),
                inputs={"question": "string", "notes": "string"},
                output="brief",
                prompt=(
                    "你根据用户给出的问题和材料把问题查清楚。notes 可以为空。"
                    "不要假装上网搜索，也不要编造来源或文件内容。输出 brief："
                    "已知、未知、证据、推断，以及下一步该收集什么。证据不足时"
                    "明确说缺口，而不是硬写结论。"
                ),
                skill_refs=(
                    "veyra.skill.research-brief@1.0.0",
                    "veyra.skill.evidence-ledger@1.0.0",
                ),
            ),
            FILE_SORT_PLANNER_TEMPLATE_ID: _work_template(
                catalog,
                agent_id="01a05129-5e8c-7f00-a73f-e798911def30",
                slug="file-sort-planner",
                name="文件整理",
                description=(
                    "根据文件清单给出分类、命名和目录方案。"
                    "当前不会真正移动、重命名或删除文件。"
                ),
                inputs={"listing": "string", "goal": "string"},
                output="plan",
                prompt=(
                    "你根据文件清单给出整理方案，而不是真正移动文件。"
                    "listing 是唯一库存。输出 plan：目录树、命名规则、重复处理、"
                    "保留/归档/删除候选，以及风险提示。不要声称文件已经被移动或删除。"
                    "清单不完整时说出来。"
                ),
                skill_refs=(
                    "veyra.skill.file-taxonomy@1.0.0",
                    "veyra.skill.content-planner@1.0.0",
                ),
            ),
        }
        for template_id, source in sources.items():
            _assert_local_only(source, template_id)
        self._order = (
            STARTER_TEMPLATE_ID,
            DOCUMENT_DISTILLER_TEMPLATE_ID,
            QUESTION_RESEARCHER_TEMPLATE_ID,
            FILE_SORT_PLANNER_TEMPLATE_ID,
        )
        self._sources = sources

    def metadata(self) -> list[dict[str, str]]:
        return [
            {
                "template_id": template_id,
                "name": source.name,
                "description": source.description,
                "default_slug": source.slug,
            }
            for template_id, source in (
                (template_id, self._sources[template_id]) for template_id in self._order
            )
        ]

    def source(self, template_id: str) -> AgentSource:
        """Return a validated copy of a registered source without installing it."""
        template = self._sources.get(template_id)
        if template is None:
            raise AgentTemplateError("unknown Agent template")
        return AgentSource.from_dict(template.to_dict())

    def instantiate(
        self, *, template_id: str, slug: str, name: str, description: str
    ) -> AgentSource:
        source = self.source(template_id).to_dict()
        source.update(
            {
                "agent_id": new_uuid7(),
                "slug": slug,
                "name": name,
                "description": description,
            }
        )
        return AgentSource.from_dict(source)


def _work_template(
    catalog: ResourceCatalog,
    *,
    agent_id: str,
    slug: str,
    name: str,
    description: str,
    inputs: dict[str, str],
    output: str,
    prompt: str,
    skill_refs: tuple[str, ...],
) -> AgentSource:
    suffix, skill_lock = _compiled_skills(catalog, skill_refs)
    system_prompt = prompt if not suffix else f"{prompt}\n\n{suffix}"
    bindings = merge_catalog_bindings(
        existing=None,
        skill_refs=skill_refs,
        reserved_ids=("start", "agent", "output"),
    )
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "agentspec_version": "26.1",
        "component_type": "Flow",
        "agent_id": agent_id,
        "slug": slug,
        "name": name,
        "description": description,
        "inputs": inputs,
        "outputs": {output: "string"},
        "nodes": [
            {"id": "start", "component_type": "Start"},
            {
                "id": "agent",
                "component_type": "Agent",
                "model_ref": "model.primary",
                "system_prompt": system_prompt,
            },
            {
                "id": "output",
                "component_type": "Output",
                "output_name": output,
            },
        ],
        "transitions": [
            {"from": "start", "port": "next", "to": "agent"},
            {"from": "agent", "port": "next", "to": "output"},
        ],
        "extensions": {
            "veyra": {
                "runtime_profile": "veyra-runtime-profile/1",
                "secret_refs": [],
                "permissions": dict(_EMPTY_PERMISSIONS),
                "verification": {"required": False, "checks": []},
                "skill_refs": list(skill_refs),
                "policy_refs": [],
            }
        },
        "ui": attach_default_canvas_note(
            {
                "positions": {
                    "start": {"x": 0, "y": 80},
                    "agent": {"x": 240, "y": 80},
                    "output": {"x": 480, "y": 80},
                },
                **({"bindings": bindings} if bindings else {}),
            },
            description,
        ),
        "lock": {
            **skill_lock,
            "veyra.runtime.profile@1.0.0": _RUNTIME_LOCK_DIGEST,
        },
    }
    return AgentSource.from_dict(payload)


def _compiled_skills(
    catalog: ResourceCatalog, references: tuple[str, ...]
) -> tuple[str, dict[str, str]]:
    blocks: list[str] = []
    lock: dict[str, str] = {}
    for reference in references:
        resource = catalog.by_reference(reference)
        instruction = str(resource["spec"].get("instruction", "")).strip()
        if instruction:
            blocks.append(f"[{resource['name']}] {instruction}")
        lock[resource["reference"]] = resource["content_hash"]
    return "\n\n".join(blocks), lock


def _assert_local_only(source: AgentSource, template_id: str) -> None:
    permissions = source.permissions
    if (
        permissions.network_hosts
        or permissions.tools
        or permissions.filesystem_read_roots
        or permissions.filesystem_write_roots
        or permissions.shell_workspace_only
    ):
        raise RuntimeError(f"{template_id} must have no external authority")
    if any(node.component_type.value == "Tool" for node in source.nodes):
        raise RuntimeError(f"{template_id} must not declare Tool nodes")
