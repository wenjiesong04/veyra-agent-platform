"""Derive Runtime model needs from the Builder's structured task plan."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from veyra_agent_platform.contracts.execution_plan import ExecutionPlan
from veyra_agent_platform.contracts.task_structure import TaskStructure
from veyra_agent_platform.local.models.contracts import (
    CAPABILITY_NAME_SET,
    ModelCapabilityRequirement,
)

_MODEL_ALIASES = {
    "image_understanding": "image_input",
    "vision": "image_input",
}
_INPUT_CAPABILITIES = {
    "image": "image_input",
    "audio": "audio_input",
    "video": "video_input",
}
_OUTPUT_CAPABILITIES = {
    "image": "image_generation",
    "audio": "audio_generation",
    "video": "video_generation",
}
_PRIMARY_CAPABILITIES = frozenset(
    {
        "text_input",
        "text_generation",
        "image_input",
        "audio_input",
        "video_input",
        "structured_output",
        "tool_calling",
        "reasoning",
    }
)


@dataclass
class _SlotRequirements:
    required: dict[str, None] = field(default_factory=dict)
    optional: dict[str, None] = field(default_factory=dict)
    reasons: dict[str, None] = field(default_factory=dict)
    sources: dict[str, None] = field(default_factory=dict)

    def add(
        self,
        capability: str,
        *,
        required: bool,
        reason: str,
        source: str,
    ) -> None:
        if required:
            self.required.setdefault(capability, None)
            self.optional.pop(capability, None)
        elif capability not in self.required:
            self.optional.setdefault(capability, None)
        if reason.strip():
            self.reasons.setdefault(reason.strip()[:200], None)
        if source.strip():
            self.sources.setdefault(source.strip()[:160], None)


def derive_model_requirements(
    structure: TaskStructure, plan: ExecutionPlan
) -> tuple[ModelCapabilityRequirement, ...]:
    """Create per-role capability needs without selecting any provider/model ID."""

    actor_ids = tuple(actor.id for actor in plan.actors)
    default_actor_id = actor_ids[0] if actor_ids else None
    structure_actors = {actor.id: actor for actor in structure.actors}
    actor_capabilities = {
        actor.id: {
            _MODEL_ALIASES.get(capability, capability)
            for capability in actor.capabilities
        }
        for actor in plan.actors
    }
    slots: dict[tuple[str | None, str], _SlotRequirements] = {}
    required_by_actor_capability: dict[tuple[str | None, str], bool] = {}

    def actors_for(capability: str) -> tuple[str | None, ...]:
        normalized = _MODEL_ALIASES.get(capability, capability)
        matches = tuple(
            actor_id
            for actor_id in actor_ids
            if normalized in actor_capabilities[actor_id]
        )
        return matches or (default_actor_id,)

    stage_actors = {
        item.id: item.actor
        for item in structure.stages
        if item.actor in actor_capabilities
    }

    def actors_for_boundary(boundary: Any) -> tuple[str | None, ...]:
        matching_step = next(
            (
                step
                for step in plan.steps
                if step.source
                and boundary.source
                and step.source == boundary.source
                and step.agent in actor_capabilities
            ),
            None,
        )
        if matching_step is not None:
            return (matching_step.agent,)
        stage_actor = stage_actors.get(boundary.stage)
        if stage_actor:
            return (stage_actor,)
        if boundary.capability:
            return actors_for(boundary.capability)
        return (default_actor_id,)

    def record_required(
        capability: str,
        required: bool,
        targets: tuple[str | None, ...],
    ) -> None:
        normalized = _MODEL_ALIASES.get(capability, capability)
        if normalized not in CAPABILITY_NAME_SET:
            return
        for actor_id in targets:
            key = (actor_id, normalized)
            required_by_actor_capability[key] = (
                required_by_actor_capability.get(key, False) or required
            )

    for item in structure.inputs:
        capability = _INPUT_CAPABILITIES.get(item.type)
        if capability:
            record_required(capability, item.required, actors_for(capability))
    for item in structure.outputs:
        capability = _OUTPUT_CAPABILITIES.get(item.type)
        if capability:
            record_required(capability, item.required, actors_for(capability))
    for boundary in structure.execution_boundaries:
        targets = actors_for_boundary(boundary)
        if boundary.capability:
            record_required(boundary.capability, boundary.required, targets)

    def add(
        capability: str,
        *,
        actor_id: str | None = None,
        required: bool | None = None,
        reason: str = "",
        source: str = "",
    ) -> None:
        normalized = _MODEL_ALIASES.get(capability, capability)
        if normalized not in CAPABILITY_NAME_SET:
            return
        # V2 companions use the platform JSON-action loop. They do not invoke
        # Provider-native tools or response_format; those features are required
        # only by Runtime paths that actually use their Provider API protocol.
        if normalized in {"tool_calling", "structured_output"}:
            return
        slot = _slot_for(normalized)
        targets = (actor_id,) if actor_id is not None else actors_for(normalized)
        for owner in targets:
            is_required = (
                required
                if required is not None
                else required_by_actor_capability.get((owner, normalized), True)
            )
            slots.setdefault((owner, slot), _SlotRequirements()).add(
                normalized,
                required=is_required,
                reason=reason or structure.summary,
                source=source,
            )

    for actor in plan.actors:
        add(
            "text_generation",
            actor_id=actor.id,
            reason=actor.brief or structure.summary,
            source=f"execution_plan.actors.{actor.id}",
        )

    for structure_actor in structure.actors:
        for capability in structure_actor.capabilities:
            owner = (
                structure_actor.id if structure_actor.id in actor_capabilities else None
            )
            add(
                capability,
                actor_id=owner,
                reason=structure_actor.reason or structure_actor.role,
                source=f"task_structure.actors.{structure_actor.id}",
            )
    for plan_actor in plan.actors:
        source_actor = structure_actors.get(plan_actor.id)
        reason = (
            source_actor.reason
            if source_actor is not None and source_actor.reason
            else plan_actor.brief
        )
        for capability in plan_actor.capabilities:
            add(
                capability,
                actor_id=plan_actor.id,
                reason=reason,
                source=f"execution_plan.actors.{plan_actor.id}",
            )

    for item in structure.inputs:
        capability = _INPUT_CAPABILITIES.get(item.type)
        if capability:
            targets = actors_for(capability)
            add(
                capability,
                actor_id=targets[0] if len(targets) == 1 else None,
                required=item.required,
                reason=item.description or f"The task accepts {item.type} input.",
                source=item.source or f"task_structure.inputs.{item.name}",
            )
    for item in structure.outputs:
        capability = _OUTPUT_CAPABILITIES.get(item.type)
        if capability:
            targets = actors_for(capability)
            add(
                capability,
                actor_id=targets[-1] if len(targets) == 1 else None,
                required=item.required,
                reason=item.description or f"The task produces {item.type} output.",
                source=item.source or f"task_structure.outputs.{item.name}",
            )

    for boundary in structure.execution_boundaries:
        targets = actors_for_boundary(boundary)
        if boundary.capability:
            for owner in targets:
                add(
                    boundary.capability,
                    actor_id=owner,
                    required=boundary.required,
                    reason=boundary.reason,
                    source=boundary.source
                    or f"task_structure.boundaries.{boundary.stage}",
                )

    for capability in plan.capabilities:
        add(
            capability,
            reason=structure.summary,
            source="execution_plan.capabilities",
        )
    for step in plan.steps:
        if step.capability:
            add(
                step.capability,
                actor_id=step.agent if step.agent in actor_capabilities else None,
                reason=step.why,
                source=step.source or f"execution_plan.steps.{step.id}",
            )

    result: list[ModelCapabilityRequirement] = []
    for (actor_id, slot), slot_data in slots.items():
        required_names = tuple(slot_data.required)
        optional_names = tuple(
            name for name in slot_data.optional if name not in slot_data.required
        )
        if not required_names and not optional_names:
            continue
        result.append(
            ModelCapabilityRequirement(
                slot=slot,
                required=required_names,
                optional=optional_names,
                reason="; ".join(slot_data.reasons)[:600],
                source="; ".join(slot_data.sources)[:600],
                required_for_run=bool(required_names),
                actor_id=actor_id,
            )
        )
    return tuple(result)


def _slot_for(capability: str) -> str:
    if capability in {"image_generation", "image_editing"}:
        return "image"
    if capability in {
        "audio_input",
        "audio_generation",
        "speech_to_text",
        "text_to_speech",
    }:
        return "audio"
    if capability in {"video_input", "video_generation"}:
        return "video"
    if capability == "embeddings":
        return "embedding"
    if capability == "reranking":
        return "reranker"
    if capability in _PRIMARY_CAPABILITIES:
        return "primary"
    return "primary"
