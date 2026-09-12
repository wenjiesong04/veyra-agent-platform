"""Project-scoped selections projected from the server-owned Resource Catalog."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from typing import Any

from veyra_agent_platform.contracts.resource import ProjectResourceBinding
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService

from .catalog import ResourceCatalog, ResourceCatalogError


class ProjectResourceError(ValueError):
    """A Project resource selection is invalid or conflicts with source usage."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ProjectResourceService:
    """Manage portable Project bindings without mutating the global Catalog."""

    def __init__(self, projects: ProjectService, catalog: ResourceCatalog) -> None:
        self.projects = projects
        self.catalog = catalog

    def list(self, project_id: str) -> dict[str, Any]:
        try:
            bindings = self.projects.project_resource_bindings(project_id)
            usage = self.projects.project_resource_usage(project_id)
        except ProjectError as exc:
            raise ProjectResourceError(exc.code, str(exc)) from exc

        binding_by_reference = {binding.reference: binding for binding in bindings}
        references = set(binding_by_reference) | set(usage)
        resources: list[dict[str, Any]] = []
        missing: list[str] = []
        for reference in sorted(references):
            try:
                descriptor = self.catalog.by_reference(reference)
            except ResourceCatalogError:
                missing.append(reference)
                continue
            binding = binding_by_reference.get(reference)
            resources.append(
                self._project_descriptor(
                    descriptor,
                    scope="project" if binding is not None else "used_unbound",
                    binding=binding,
                    used_by=usage.get(reference, []),
                )
            )

        for descriptor in self.catalog.resources()["resources"]:
            if (
                descriptor["kind"] == "component"
                and descriptor.get("component_class", "primitive") == "primitive"
            ):
                resources.append(
                    self._project_descriptor(
                        descriptor, scope="builtin", binding=None, used_by=[]
                    )
                )

        resources.sort(
            key=lambda item: (
                {"project": 0, "used_unbound": 1, "builtin": 2}[item["scope"]],
                item["kind"],
                item["name"],
            )
        )
        stale_count = sum(item.get("binding_status") == "stale" for item in resources)
        return {
            "schema_version": "1.0",
            "project_id": project_id,
            "resources": resources,
            "missing_references": missing,
            "project_count": sum(item["scope"] == "project" for item in resources),
            "used_count": sum(bool(item["used_by"]) for item in resources),
            "unbound_count": sum(item["scope"] == "used_unbound" for item in resources),
            "builtin_count": sum(item["scope"] == "builtin" for item in resources),
            "stale_count": stale_count,
        }

    def add(
        self, project_id: str, reference: str, *, source: str = "manual"
    ) -> dict[str, Any]:
        try:
            descriptor = self.catalog.by_reference(reference)
        except ResourceCatalogError as exc:
            raise ProjectResourceError(exc.code, str(exc)) from exc
        if (
            descriptor["kind"] == "component"
            and descriptor.get("component_class", "primitive") == "primitive"
        ):
            raise ProjectResourceError(
                "resource_builtin",
                "platform primitive components are always available",
            )
        try:
            current = self.projects.project_resource_bindings(project_id)
            if any(binding.reference == reference for binding in current):
                return self.list(project_id)
            binding = ProjectResourceBinding.from_dict(
                {
                    "reference": reference,
                    "content_hash": descriptor["content_hash"],
                    "source": source,
                }
            )
            return self._replace(project_id, (*current, binding))
        except ProjectError as exc:
            raise ProjectResourceError(exc.code, str(exc)) from exc

    def remove(self, project_id: str, reference: str) -> dict[str, Any]:
        try:
            current = self.projects.project_resource_bindings(project_id)
            usage = self.projects.project_resource_usage(project_id)
        except ProjectError as exc:
            raise ProjectResourceError(exc.code, str(exc)) from exc
        if reference not in {binding.reference for binding in current}:
            raise ProjectResourceError(
                "resource_not_bound", "resource is not bound to this Project"
            )
        if usage.get(reference):
            raise ProjectResourceError(
                "resource_in_use",
                "resource is still used by an Agent or Workflow",
            )
        return self._replace(
            project_id,
            tuple(binding for binding in current if binding.reference != reference),
        )

    def _replace(
        self, project_id: str, bindings: tuple[ProjectResourceBinding, ...]
    ) -> dict[str, Any]:
        try:
            self.projects.replace_project_resource_bindings(project_id, bindings)
        except ProjectError as exc:
            raise ProjectResourceError(exc.code, str(exc)) from exc
        return self.list(project_id)

    @staticmethod
    def _project_descriptor(
        descriptor: dict[str, Any],
        *,
        scope: str,
        binding: ProjectResourceBinding | None,
        used_by: Sequence[dict[str, str]],
    ) -> dict[str, Any]:
        result = deepcopy(descriptor)
        result.update(
            {
                "scope": scope,
                "binding_status": (
                    "builtin"
                    if scope == "builtin"
                    else "unbound"
                    if binding is None
                    else "current"
                    if binding.content_hash == descriptor["content_hash"]
                    else "stale"
                ),
                "binding_source": binding.source if binding is not None else None,
                "bound_content_hash": (
                    binding.content_hash if binding is not None else None
                ),
                "used_by": used_by,
            }
        )
        return result
