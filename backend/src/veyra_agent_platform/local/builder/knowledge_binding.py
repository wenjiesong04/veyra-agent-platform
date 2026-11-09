"""Deterministic Project Knowledge resolution and Agent binding candidates.

The model never chooses a Knowledge document and never copies a content hash.
This module resolves a mention against the Project's own Knowledge inventory and
builds the candidate source with the server-computed lock, so the existing
EditProposal envelope, Draft writer, and validation stay the only write path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af]")
_BINDING_ID = re.compile(r"[^a-z0-9]")
_LOCK_PREFIX_SEPARATOR = "@"
_MIN_ALIAS = 2

MatchStatus = Literal["resolved", "ambiguous", "unresolved"]


@dataclass(frozen=True)
class KnowledgeMatch:
    """A deterministic resolution outcome; ambiguity is never auto-resolved."""

    status: MatchStatus
    selected: dict[str, Any] | None
    candidates: tuple[dict[str, Any], ...]


def _aliases(document: dict[str, Any]) -> tuple[str, ...]:
    processing = document.get("processing") or {}
    names = [str(document.get("name") or ""), str(document.get("slug") or "")]
    # `document.md` is the placeholder name every text-created Knowledge shares,
    # so only an uploaded filename is a user-meaningful alias.
    if processing.get("origin") == "upload":
        filename = str(processing.get("filename") or "")
        names.append(filename)
        names.append(filename.rsplit(".", 1)[0] if "." in filename else filename)
    unique = {
        value.strip().casefold() for value in names if len(value.strip()) >= _MIN_ALIAS
    }
    return tuple(sorted(unique, key=len, reverse=True))


def _mentioned(text: str, alias: str) -> bool:
    if _CJK.search(alias):
        return alias in text
    return bool(
        re.search(r"(?<![a-z0-9_-])" + re.escape(alias) + r"(?![a-z0-9_-])", text)
    )


def resolve_knowledge(
    inventory: list[dict[str, Any]], instruction: str
) -> KnowledgeMatch:
    """Match one Project-owned Knowledge document mentioned in the instruction.

    The most specific phrase the user actually typed becomes the mention. Every
    document whose name still contains that mention stays a candidate, so a
    request for `毕业论文` when `毕业论文-旧版` also exists asks for clarification
    instead of silently picking one.
    """

    text = instruction.casefold()
    spoken = [
        alias
        for document in inventory
        for alias in _aliases(document)
        if _mentioned(text, alias)
    ]
    if not spoken:
        return KnowledgeMatch("unresolved", None, ())
    mention = max(spoken, key=len)
    candidates = tuple(
        document
        for document in inventory
        if any(mention in alias for alias in _aliases(document))
    )
    if len(candidates) == 1:
        return KnowledgeMatch("resolved", candidates[0], candidates)
    return KnowledgeMatch("ambiguous", None, candidates)


def knowledge_reference(document: dict[str, Any]) -> str:
    return f"{document['knowledge_id']}{_LOCK_PREFIX_SEPARATOR}{document['version']}"


def _binding_id(bindings: dict[str, Any], knowledge_id: str) -> str:
    base = f"knowledge_{_BINDING_ID.sub('', knowledge_id.casefold())[:12] or 'context'}"
    if base not in bindings:
        return base
    index = 2
    while f"{base}_{index}" in bindings:
        index += 1
    return f"{base}_{index}"


def bind_knowledge(source: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    """Return the candidate source with declared refs, lock, and Studio binding.

    This mirrors the Studio binding helper so a Builder proposal and a manual
    Studio bind produce the same source shape, including the Canvas card.
    """

    reference = knowledge_reference(document)
    prefix = f"{document['knowledge_id']}{_LOCK_PREFIX_SEPARATOR}"
    candidate = dict(source)
    veyra = dict(candidate["extensions"]["veyra"])
    existing_refs = [
        item
        for item in veyra.get("knowledge_refs", [])
        if not str(item).startswith(prefix)
    ]
    veyra["knowledge_refs"] = [*existing_refs, reference]
    candidate["extensions"] = {**candidate["extensions"], "veyra": veyra}

    ui = dict(candidate["ui"])
    bindings = dict(ui.get("bindings") or {})
    previous = next(
        (
            (identity, binding)
            for identity, binding in bindings.items()
            if binding.get("kind") == "knowledge"
            and str(binding.get("reference", "")).startswith(prefix)
        ),
        None,
    )
    for identity, binding in list(bindings.items()):
        if binding.get("kind") == "knowledge" and str(
            binding.get("reference", "")
        ).startswith(prefix):
            bindings.pop(identity)
    identity = (
        previous[0] if previous else _binding_id(bindings, document["knowledge_id"])
    )
    placed = (
        {"x": previous[1]["x"], "y": previous[1]["y"]}
        if previous
        else {"x": 24 + (len(bindings) % 3) * 220, "y": 24 + (len(bindings) // 3) * 140}
    )
    bindings[identity] = {"kind": "knowledge", "reference": reference, **placed}
    ui["bindings"] = bindings
    candidate["ui"] = ui

    candidate["lock"] = {
        **{
            item: digest
            for item, digest in candidate["lock"].items()
            if not str(item).startswith(prefix)
        },
        reference: document["source_file_hash"],
    }
    return candidate


def knowledge_readiness(document: dict[str, Any]) -> dict[str, Any]:
    """Project the honest index state a Proposal must show before confirmation."""

    processing = document.get("processing") or {}
    status = str(processing.get("index_status") or "not_indexed")
    return {
        "reference": knowledge_reference(document),
        "name": str(document.get("name") or ""),
        "source_file_hash": str(document["source_file_hash"]),
        "index_status": status,
        "chunk_count": processing.get("chunk_count"),
        "failure_reason": processing.get("failure_reason"),
        "runnable": status == "indexed",
        "required_action": None
        if status == "indexed"
        else "build_index"
        if status == "not_indexed"
        else "rebuild_index",
    }
