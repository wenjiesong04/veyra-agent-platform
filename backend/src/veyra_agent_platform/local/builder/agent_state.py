"""Source-owned state contracts for autonomous Agents and their explicit Apply."""

from __future__ import annotations

import json
from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.task_structure import StateRequirement
from veyra_agent_platform.contracts.typed_io import parse_typed_field
from veyra_agent_platform.local.state.entity_store import EntityStore


def state_instructions(state: StateRequirement) -> str:
    return (
        "Persistent state contract:\n"
        + json.dumps(state.to_dict(), ensure_ascii=False, sort_keys=True)
        + "\nUse this exact entity type and declared identity/fields. Query existing "
        "records before creating or updating. Query filters are exact matches over "
        "data fields. If identity is unknown or multiple records match, ask the "
        "user; never guess an entity_id. A truncated query cannot prove absence: "
        "narrow the query or ask for a known record. Preserve returned entity_id "
        "when updating. Merge changes into existing data; retain other fields. "
        "Create only when the user requested a new record and an untruncated "
        "query found no match. Never claim persistence before a successful write "
        "receipt. Respect all requested confirmation steps."
    )


def source_state_schema(source: AgentSource) -> dict[str, Any] | None:
    state = source.state_contract
    if state is None:
        return None
    if state.identity not in state.fields and state.identity != "entity_id":
        raise ValueError("Agent state identity must name a declared field or entity_id")
    for kind in state.fields.values():
        if kind != "artifact":
            parse_typed_field(kind, "state.field")
    if state_instructions(state) not in source.instructions:
        raise ValueError("Agent state metadata does not match its instructions")
    return state.to_dict()


def check_agent_state(
    project_id: str, source: AgentSource, store: EntityStore | None
) -> None:
    schema = source_state_schema(source)
    if schema is None:
        return
    if store is None:
        raise ValueError("Agent persistent state storage is unavailable")
    existing = store.read_type_schema(project_id, schema["entity"])
    if existing is not None and existing != schema:
        raise ValueError(
            "Agent state type conflicts with an existing Project definition"
        )


def register_agent_state(
    project_id: str, source: AgentSource, store: EntityStore | None
) -> None:
    schema = source_state_schema(source)
    if schema is not None:
        if store is None:
            raise ValueError("Agent persistent state storage is unavailable")
        store.ensure_type(project_id, schema["entity"], schema)
