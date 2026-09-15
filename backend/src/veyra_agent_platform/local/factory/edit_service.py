"""Generate source-only proposals; explicit commands own all Draft mutations."""

from __future__ import annotations

import json
from contextlib import suppress
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any, Literal

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.common import ContractValidationError, new_uuid7
from veyra_agent_platform.contracts.workflow import WorkflowSource
from veyra_agent_platform.local.builder.harness import BuilderHarness
from veyra_agent_platform.local.library.dependencies import inspect_agent_dependencies
from veyra_agent_platform.local.library.service import DraftConflict, LibraryService
from veyra_agent_platform.local.library.workflow_dependencies import (
    resolve_workflow_calls,
)
from veyra_agent_platform.local.projects.service import ProjectError
from veyra_agent_platform.local.resources import ResourceCatalog

from .client import KimiClient
from .edit_store import EditProposalStore
from .service import FactoryError

TargetKind = Literal["agent", "workflow"]
EditCommand = Literal["apply", "reject", "undo"]
MAX_SOURCE_BYTES = 200_000


class EditProposalService:
    def __init__(
        self,
        store: EditProposalStore,
        library: LibraryService,
        catalog: ResourceCatalog,
        client: KimiClient,
    ) -> None:
        self.store = store
        self.library = library
        self.catalog = catalog
        self.client = client
        self.harness = BuilderHarness(library.projects, catalog)

    def draft(
        self, project_id: str, kind: TargetKind, target_id: str
    ) -> dict[str, Any]:
        reader = (
            self.library.workflow_draft if kind == "workflow" else self.library.draft
        )
        return reader(project_id, target_id)

    def create(
        self,
        project_id: str,
        kind: TargetKind,
        target_id: str,
        instruction: str,
        expected_revision: int,
        expected_etag: str,
    ) -> dict[str, Any]:
        base = self.draft(project_id, kind, target_id)
        if base["revision"] != expected_revision or base["etag"] != expected_etag:
            raise DraftConflict(
                "Save or reload the current Draft before proposing edits"
            )
        if not instruction.strip():
            raise FactoryError("edit_instruction_empty", "Describe the change first")
        permissions = base["source"]["extensions"]["veyra"]["permissions"]
        if any(
            Path(root).is_absolute() or PureWindowsPath(root).is_absolute()
            for field in ("filesystem_read_roots", "filesystem_write_roots")
            for root in permissions.get(field, [])
        ):
            raise FactoryError(
                "edit_source_host_paths",
                "Use Project-relative filesystem permissions before sending this "
                "source to Builder. The Draft is unchanged.",
            )
        encoded = json.dumps(base["source"], ensure_ascii=False)
        if len(encoded.encode()) > MAX_SOURCE_BYTES:
            raise FactoryError(
                "edit_source_too_large", "This source exceeds the edit limit"
            )
        schema = _source_schema(kind)
        messages = self.harness.messages(
            project_id,
            "edit_source",
            target={
                "kind": kind,
                "target_id": target_id,
                "revision": base["revision"],
                "etag": base["etag"],
                "source": base["source"],
            },
            schema=schema,
        )
        self.client.ensure_model()
        messages.append({"role": "user", "content": instruction})
        for _ in range(self.client.settings.repair_attempts):
            completion = self.client.complete(
                messages, response_format={"type": "json_object"}
            )
            try:
                if len(completion.content.encode()) > MAX_SOURCE_BYTES:
                    raise ContractValidationError(
                        "Proposed source exceeds the edit limit"
                    )
                candidate = json.loads(completion.content)
                validation = self._validate(project_id, kind, base["source"], candidate)
                parsed = _parse(kind, candidate).to_dict()
                changes = _changes(base["source"], parsed)
                if not changes:
                    raise ContractValidationError(
                        "The proposal does not change the source"
                    )
            except (ValueError, TypeError, ProjectError) as exc:
                messages.extend(
                    [
                        completion.assistant_message,
                        {"role": "user", "content": str(exc)},
                    ]
                )
                continue
            proposal = {
                "schema_version": "1.0",
                "proposal_id": new_uuid7(),
                "apply_key": new_uuid7(),
                "undo_key": new_uuid7(),
                "project_id": project_id,
                "target_kind": kind,
                "target_id": target_id,
                "instruction": instruction.strip(),
                "created_at": datetime.now(UTC).isoformat(),
                "base_revision": base["revision"],
                "base_etag": base["etag"],
                "previous_source": base["source"],
                "candidate_source": parsed,
                "changes": changes,
                "permission_changes": _changes(
                    base["source"]["extensions"]["veyra"]["permissions"],
                    parsed["extensions"]["veyra"]["permissions"],
                ),
                "impact": {
                    "target_kind": kind,
                    "target_id": target_id,
                    "scope": "single_draft",
                    "immutable_versions_changed": False,
                    "runs_started": False,
                },
                "validation": validation,
                "state": "review",
            }
            self.store.create(proposal)
            return self.get(project_id, proposal["proposal_id"])
        raise FactoryError(
            "edit_generation_invalid",
            "The provider could not produce a valid source change; "
            "the Draft is unchanged",
        )

    def _validate(
        self,
        project_id: str,
        kind: TargetKind,
        previous: dict[str, Any],
        candidate: Any,
    ) -> dict[str, Any]:
        parsed = _parse(kind, candidate)
        normalized = parsed.to_dict()
        for field in (f"{kind}_id", "slug", "component_type"):
            if normalized[field] != previous[field]:
                raise ContractValidationError(
                    "An edit cannot replace the target identity"
                )
        result: dict[str, Any] = {
            "schema_version": "1.0",
            "valid": True,
            "source_hash": parsed.source_hash,
            "behavior_hash": parsed.behavior_hash,
            "lock_hash": parsed.lock_hash,
        }
        if isinstance(parsed, AgentSource):
            result.update(
                inspect_agent_dependencies(
                    self.library.projects, self.catalog, project_id, parsed
                )
            )
            for dependency in result["dependencies"]:
                if dependency["status"] in {
                    "missing",
                    "lock_missing",
                    "lock_mismatch",
                    "kind_mismatch",
                    "context_not_declared",
                    "context_too_large",
                }:
                    raise ContractValidationError(
                        f"Invalid dependency {dependency['reference']}: "
                        f"{dependency['status']}"
                    )
                if (
                    dependency["kind"] != "knowledge"
                    and dependency["reference"] not in previous["lock"]
                ):
                    resource = self.catalog.by_reference(dependency["reference"])
                    if not resource["factory_selectable"] or resource[
                        "availability"
                    ] in {
                        "quarantined",
                        "disabled",
                        "unavailable",
                    }:
                        raise ContractValidationError(
                            "New dependencies must be selectable Factory resources"
                        )
        else:
            calls = resolve_workflow_calls(self.library.repository, project_id, parsed)
            result["agent_calls"] = [
                {
                    "node_id": node,
                    "agent_id": call.agent_id,
                    "version_id": call.version_id,
                }
                for node, call in calls.items()
            ]
        return result

    def get(self, project_id: str, proposal_id: str) -> dict[str, Any]:
        proposal = self.store.get(project_id, proposal_id)
        if proposal is None:
            raise FactoryError("edit_proposal_not_found", "Edit proposal was not found")
        try:
            current = self.draft(
                project_id, proposal["target_kind"], proposal["target_id"]
            )
        except DraftConflict:
            current = None
        applied = self.store.receipt(proposal)
        undone = self.store.receipt(proposal, undo=True)
        if undone:
            proposal["state"] = "undone"
        elif applied:
            proposal["state"] = "applied"
        expected = (
            undone
            or applied
            or {"revision": proposal["base_revision"], "etag": proposal["base_etag"]}
        )
        proposal["stale"] = current is None or any(
            current[key] != expected[key] for key in ("revision", "etag")
        )
        proposal["applied_revision"] = applied["revision"] if applied else None
        proposal.pop("undo_key")
        proposal.pop("apply_key", None)
        proposal.pop("previous_source")
        return proposal

    def list(self, project_id: str, kind: TargetKind, target_id: str) -> dict[str, Any]:
        with suppress(DraftConflict):
            self.draft(project_id, kind, target_id)
        return {
            "schema_version": "1.0",
            "proposals": [
                self.get(project_id, item["proposal_id"])
                for item in self.store.list(project_id, kind, target_id)
            ],
        }

    def command(
        self, project_id: str, proposal_id: str, command: EditCommand, *, confirm: bool
    ) -> dict[str, Any]:
        if not confirm:
            raise FactoryError(
                "edit_confirmation_required", "Explicit confirmation is required"
            )
        with self.library.projects._writer_lock:
            view = self.get(project_id, proposal_id)
            proposal = self.store.get(project_id, proposal_id)
            assert proposal is not None
            desired = {"apply": "applied", "reject": "rejected", "undo": "undone"}[
                command
            ]
            if view["state"] == desired:
                return view
            allowed = "applied" if command == "undo" else "review"
            if view["state"] != allowed:
                raise FactoryError(
                    "edit_proposal_closed", "This proposal cannot accept that command"
                )
            if command == "reject":
                self.store.reject(proposal_id)
            else:
                if view["stale"]:
                    raise DraftConflict(
                        "The Draft changed since this proposal; generate a new proposal"
                    )
                kind = proposal["target_kind"]
                undo = command == "undo"
                candidate = proposal["previous_source" if undo else "candidate_source"]
                if not undo:
                    try:
                        validation = self._validate(
                            project_id, kind, proposal["previous_source"], candidate
                        )
                    except (ContractValidationError, ProjectError) as exc:
                        raise DraftConflict(
                            "Dependencies changed since review; generate a new proposal"
                        ) from exc
                    if validation != proposal["validation"]:
                        raise DraftConflict(
                            "Dependencies changed since review; generate a new proposal"
                        )
                base = (
                    self.store.receipt(proposal)
                    if undo
                    else {
                        "revision": proposal["base_revision"],
                        "etag": proposal["base_etag"],
                    }
                )
                writer = (
                    self.library.replace_workflow_draft
                    if kind == "workflow"
                    else self.library.replace_draft
                )
                writer(
                    project_id=project_id,
                    **{f"{kind}_id": proposal["target_id"]},
                    source=candidate,
                    expected_revision=base["revision"],
                    expected_etag=base["etag"],
                    idempotency_key=proposal["undo_key"]
                    if undo
                    else proposal.get("apply_key", proposal_id),
                )
            return self.get(project_id, proposal_id)


def _parse(kind: TargetKind, source: Any) -> AgentSource | WorkflowSource:
    return (
        WorkflowSource.from_dict(source)
        if kind == "workflow"
        else AgentSource.from_dict(source)
    )


def _source_schema(kind: TargetKind) -> dict[str, Any]:
    for parent in Path(__file__).resolve().parents:
        path = parent / "contracts" / "schemas" / f"{kind}-source.schema.json"
        if path.is_file():
            schema: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return schema
    raise FactoryError("factory_schema_unavailable", "The source schema is unavailable")


def _changes(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        changes = []
        for key in sorted(before.keys() | after.keys()):
            pointer = path + "/" + key.replace("~", "~0").replace("/", "~1")
            if key in before and key in after:
                changes.extend(_changes(before[key], after[key], pointer))
            else:
                changes.append(
                    {
                        "path": pointer,
                        "operation": "add" if key in after else "remove",
                        "before": deepcopy(before.get(key)),
                        "after": deepcopy(after.get(key)),
                    }
                )
        return changes
    return [
        {
            "path": path,
            "operation": "replace",
            "before": deepcopy(before),
            "after": deepcopy(after),
        }
    ]
