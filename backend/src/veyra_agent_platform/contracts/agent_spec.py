"""Builder specification captured before a SemanticPlan is compiled."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from .common import (
    SCHEMA_VERSION,
    ContractValidationError,
    require_keys,
    require_list,
    require_mapping,
    require_schema_version,
    require_string,
)
from .semantic_plan import SemanticField, _optional_required, _optional_text, _phrases
from .typed_io import ARTIFACT_KINDS, COMPACT_TYPES

CapabilityNeed = Literal[
    "text_generation",
    "vision",
    "document_understanding",
    "image_generation",
    "filesystem_read",
    "filesystem_write",
    "human_approval",
    "structured_output",
    "tool_calling",
    "web_search",
    "http_request",
    "browser_navigate",
    "workspace_read",
    "workspace_search",
    "workspace_list",
    "workspace_write",
    "shell_exec",
    "github_read",
    "github_write",
    "mcp_call",
    "research_planning",
    "evidence_synthesis",
    "document_analysis",
    "content_planning",
    "need_extraction",
    "file_taxonomy",
    "project_knowledge",
    "knowledge_access",
    "image_understanding",
    "local_only",
    "verification_required",
    "external_write_approval",
    "entity_read",
    "entity_write",
]
PLATFORM_CAPABILITIES: tuple[str, ...] = (
    "text_generation",
    "vision",
    "document_understanding",
    "image_generation",
    "filesystem_read",
    "filesystem_write",
    "human_approval",
    "structured_output",
    "tool_calling",
    "web_search",
    "http_request",
    "browser_navigate",
    "workspace_read",
    "workspace_search",
    "workspace_list",
    "workspace_write",
    "shell_exec",
    "github_read",
    "github_write",
    "mcp_call",
    "research_planning",
    "evidence_synthesis",
    "document_analysis",
    "content_planning",
    "need_extraction",
    "file_taxonomy",
    "project_knowledge",
    "knowledge_access",
    "image_understanding",
    "local_only",
    "verification_required",
    "external_write_approval",
    "entity_read",
    "entity_write",
)
_CAPABILITIES = set(PLATFORM_CAPABILITIES)
_EXTRA_CAPABILITY = re.compile(r"^[a-z][a-z0-9_]{2,62}$")
_CAPABILITY_ALIASES = {
    "document": "document_understanding",
    "filesystem": "filesystem_read",
    "knowledge_access": "project_knowledge",
    "image_understanding": "vision",
}
SPECIFICATION_GAP_KEYS = frozenset(
    {
        "goal",
        "output",
        "input_type",
        "output_type",
        "required_capability",
        "success_criteria",
        "contradictory_requirements",
        "unsupported_capability",
        "approval_requirement",
    }
)
_SPEC_KEYS = {
    "schema_version",
    "name",
    "suggested_name",
    "goal",
    "description",
    "inputs",
    "outputs",
    "responsibilities",
    "human_interaction",
    "human_interactions",
    "required_capabilities",
    "success_criteria",
}
_FIELD_KEYS = {
    "id",
    "name",
    "type",
    "required",
    "description",
    "multiple",
    "source",
    "success_criteria",
}


@dataclass(frozen=True)
class AgentSpecification:
    schema_version: str
    goal: str
    suggested_name: str
    description: str
    inputs: tuple[SemanticField, ...]
    outputs: tuple[SemanticField, ...]
    responsibilities: tuple[str, ...]
    human_interactions: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    success_criteria: tuple[str, ...]

    @property
    def name(self) -> str:
        return self.suggested_name

    @property
    def human_interaction(self) -> tuple[str, ...]:
        return self.human_interactions

    @classmethod
    def from_dict(cls, data: Any) -> AgentSpecification:
        item = require_mapping(data, "agent specification")
        require_keys(
            item,
            allowed=_SPEC_KEYS,
            required={"schema_version", "goal", "description", "inputs", "outputs"},
        )
        require_schema_version(item)
        suggested = item.get("suggested_name") or item.get("name")
        spec = cls(
            schema_version=SCHEMA_VERSION,
            goal=require_string(item["goal"], "goal"),
            suggested_name=require_string(suggested, "suggested_name"),
            description=require_string(item["description"], "description"),
            inputs=_spec_fields(item["inputs"], "inputs", 16),
            outputs=_spec_fields(item["outputs"], "outputs", 8),
            responsibilities=_phrases(
                item.get("responsibilities") or [], "responsibilities", 12
            ),
            human_interactions=_phrases(
                item.get("human_interactions") or item.get("human_interaction") or [],
                "human_interactions",
                4,
            ),
            required_capabilities=_normalize_capabilities(
                item.get("required_capabilities") or []
            ),
            success_criteria=_phrases(
                item.get("success_criteria") or [], "success_criteria", 8
            ),
        )
        if not spec.outputs:
            raise ContractValidationError("agent specification needs outputs")
        return spec

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.suggested_name,
            "suggested_name": self.suggested_name,
            "goal": self.goal,
            "description": self.description,
            "inputs": [_spec_field_dict(item) for item in self.inputs],
            "outputs": [_spec_field_dict(item) for item in self.outputs],
            "responsibilities": list(self.responsibilities),
            "human_interactions": list(self.human_interactions),
            "human_interaction": list(self.human_interactions),
            "required_capabilities": list(self.required_capabilities),
            "success_criteria": list(self.success_criteria),
        }

    def inferred_capabilities(self) -> tuple[str, ...]:
        found: list[str] = ["text_generation"]
        input_types = {item.type for item in self.inputs}
        output_types = {item.type for item in self.outputs}
        if "image" in input_types:
            found.append("vision")
        if input_types & {"pdf", "document", "file", "collection", "table"}:
            found.append("document_understanding")
        if "image" in output_types:
            found.append("image_generation")
        if output_types & {"object", "array", "table"}:
            found.append("structured_output")
        if any(
            item.type in ARTIFACT_KINDS for item in self.outputs if item.type != "image"
        ):
            found.append("structured_output")
        if self.human_interactions:
            found.append("human_approval")
        return tuple(dict.fromkeys([*found, *self.required_capabilities]))


def _normalize_capabilities(value: Any) -> tuple[str, ...]:
    capabilities = _phrases(value, "required_capabilities", 16)
    normalized: list[str] = []
    unknown: list[str] = []
    for name in capabilities:
        mapped = _CAPABILITY_ALIASES.get(name, name)
        extra = _EXTRA_CAPABILITY.fullmatch(mapped) is not None
        if mapped not in _CAPABILITIES and not extra:
            unknown.append(name)
            continue
        if mapped not in normalized:
            normalized.append(mapped)
    if unknown:
        raise ContractValidationError(
            "code=UNKNOWN_CAPABILITY path=required_capabilities "
            f"actual={','.join(unknown)}"
        )
    return tuple(normalized)


def _spec_fields(value: Any, field: str, limit: int) -> tuple[SemanticField, ...]:
    items = require_list(value, field)
    if len(items) > limit:
        raise ContractValidationError(f"{field} exceeds {limit} items")
    parsed: list[SemanticField] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        record = require_mapping(item, f"{field}[{index}]")
        require_keys(
            record,
            allowed=_FIELD_KEYS,
            required=set(),
        )
        name = str(record.get("name") or record.get("id") or "").strip()
        if not name:
            raise ContractValidationError(f"{field}[{index}].name must not be empty")
        kind = record.get("type")
        if kind not in COMPACT_TYPES:
            raise ContractValidationError(f"{field}[{index}].type is not supported")
        multiple = record.get("multiple")
        if multiple is None:
            many = False
        elif isinstance(multiple, bool):
            many = multiple
        else:
            raise ContractValidationError(
                f"{field}[{index}].multiple must be a boolean"
            )
        key = name.casefold()
        if key in seen:
            raise ContractValidationError(f"{field} names must be unique")
        seen.add(key)
        parsed.append(
            SemanticField(
                name=name,
                type=kind,
                description=_optional_text(
                    record.get("description"), f"{field}[{index}].description", 240
                ),
                multiple=many,
                required=_optional_required(record.get("required"), field, index),
                source=_optional_text(
                    record.get("source"), f"{field}[{index}].source", 160
                ),
            )
        )
    return tuple(parsed)


def _spec_field_dict(field: SemanticField) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": field.name,
        "name": field.name,
        "type": field.type,
        "required": field.required,
        "description": field.description,
    }
    if field.multiple:
        payload["multiple"] = True
    if field.source:
        payload["source"] = field.source
    return payload
