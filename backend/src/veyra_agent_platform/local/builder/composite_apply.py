"""Atomic composite apply: companion drafts, commit, pin, workflow, rollback."""

from __future__ import annotations

import contextlib
from copy import deepcopy
from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.builder.workflow_orchestration import (
    WorkflowOrchestration,
    materialize_workflow_source,
)
from veyra_agent_platform.local.library.service import LibraryService
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService


class CompositeApplyError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def apply_composite(
    *,
    projects: ProjectService,
    library: LibraryService,
    project_id: str,
    companions: tuple[AgentSource, ...],
    workflow: dict[str, Any],
    flow: tuple[str, ...] = (),
    entity_schema: dict[str, Any] | None = None,
    entity_store: Any | None = None,
) -> dict[str, Any]:
    """Create companion Agents, commit them, pin Workflow AgentCalls."""

    version_ids: dict[str, str] = {}
    source_hashes: dict[str, str] = {}
    installed_agents: list[dict[str, Any]] = []
    created_ids: list[str] = []
    workflow_id = ""
    try:
        for companion in companions:
            created = projects.create_agent_from_source(
                project_id=project_id,
                source=companion,
                preserve_identity=True,
            )
            created_ids.append(companion.agent_id)
            draft = library.draft(project_id, companion.agent_id)
            committed = library.commit(
                project_id=project_id,
                agent_id=companion.agent_id,
                expected_revision=draft["revision"],
                expected_etag=draft["etag"],
                idempotency_key=new_uuid7(),
            )
            version_ids[companion.agent_id] = str(committed["version_id"])
            source_hashes[companion.agent_id] = str(committed["source_hash"])
            installed_agents.append(created)
        workflow_payload = deepcopy(workflow)
        permissions = dict(
            ((workflow_payload.get("extensions") or {}).get("veyra") or {}).get(
                "permissions"
            )
            or {}
        )
        for companion in companions:
            permissions["tools"] = list(
                dict.fromkeys(
                    [*(permissions.get("tools") or []), *companion.permissions.tools]
                )
            )
            permissions["network_hosts"] = list(
                dict.fromkeys(
                    [
                        *(permissions.get("network_hosts") or []),
                        *companion.permissions.network_hosts,
                    ]
                )
            )
            permissions["filesystem_read_roots"] = list(
                dict.fromkeys(
                    [
                        *(permissions.get("filesystem_read_roots") or []),
                        *companion.permissions.filesystem_read_roots,
                    ]
                )
            )
            permissions["filesystem_write_roots"] = list(
                dict.fromkeys(
                    [
                        *(permissions.get("filesystem_write_roots") or []),
                        *companion.permissions.filesystem_write_roots,
                    ]
                )
            )
            if companion.permissions.shell_workspace_only:
                permissions["shell_workspace_only"] = True
        workflow_payload.setdefault("extensions", {}).setdefault("veyra", {})[
            "permissions"
        ] = permissions
        orchestration = WorkflowOrchestration(
            workflow=workflow_payload,
            companions=companions,
            flow=flow,
        )
        source = materialize_workflow_source(
            orchestration, version_ids, source_hashes=source_hashes
        )
        installed = projects.create_workflow_from_source(
            project_id=project_id,
            source=source,
        )
        workflow_id = str(installed.get("workflow_id") or source.workflow_id)
        if entity_schema and entity_store is not None:
            entity_store.define_type(
                project_id,
                str(entity_schema.get("entity") or "ProjectEntity"),
                entity_schema,
            )
        return {
            **installed,
            "companion_agents": installed_agents,
            "pinned_versions": version_ids,
        }
    except Exception as exc:
        if workflow_id:
            with contextlib.suppress(ProjectError, OSError):
                projects.remove_workflow(project_id, workflow_id)
        for agent_id in reversed(created_ids):
            try:
                projects.remove_agent(project_id, agent_id)
            except (ProjectError, OSError):
                continue
        if isinstance(exc, CompositeApplyError):
            raise
        raise CompositeApplyError(
            getattr(exc, "code", "composite_apply_failed"),
            str(exc),
        ) from exc
