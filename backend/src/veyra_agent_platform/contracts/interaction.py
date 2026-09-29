"""Agent product interaction_mode. Runtime tool semantics ignore this field."""

from __future__ import annotations

from collections.abc import Mapping

from .typed_io import ARTIFACT_KINDS, TypedField

INTERACTION_AUTO = "auto"
INTERACTION_CHAT = "chat"
INTERACTION_FORM = "form"
INTERACTION_HYBRID = "hybrid"
INTERACTION_MODES = frozenset(
    {INTERACTION_AUTO, INTERACTION_CHAT, INTERACTION_FORM, INTERACTION_HYBRID}
)
_ARTIFACT = ARTIFACT_KINDS | {"artifact"}


def _compact_declared_type(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        kind = str(value.get("artifact_kind") or "").strip()
        declared = str(value.get("type") or "").strip()
        if declared == "artifact":
            return kind or "artifact"
        return kind or declared
    return str(value).strip()


def derive_interaction_mode(input_types: Mapping[str, object]) -> str:
    """Bounded surface choice from typed inputs. Never uses domain keywords."""

    types = [
        item
        for item in (_compact_declared_type(value) for value in input_types.values())
        if item
    ]
    if not types:
        return INTERACTION_CHAT
    artifacts = [item for item in types if item in _ARTIFACT]
    strings = [item for item in types if item == "string"]
    if artifacts and strings:
        return INTERACTION_HYBRID
    if len(types) == 1 and types[0] == "string":
        return INTERACTION_CHAT
    if len(types) >= 2 or artifacts:
        return INTERACTION_FORM
    return INTERACTION_AUTO


def compact_input_types(inputs: Mapping[str, TypedField]) -> dict[str, str]:
    return {name: field.compact_type for name, field in inputs.items()}


def resolve_interaction_mode(declared: str, inputs: Mapping[str, TypedField]) -> str:
    if declared in {INTERACTION_CHAT, INTERACTION_FORM, INTERACTION_HYBRID}:
        return declared
    derived = derive_interaction_mode(compact_input_types(inputs))
    return derived if derived != INTERACTION_AUTO else INTERACTION_CHAT
