"""Project-scoped selections projected from the server-owned Resource Catalog."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from typing import Any

from veyra_agent_platform.contracts.resource import ProjectResourceBinding
from veyra_agent_platform.local.projects.custom_components import (
    CustomComponentError,
    CustomComponentService,
)
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService

from .catalog import ResourceCatalog, ResourceCatalogError

_RUNTIME_PROFILE_LOCK_PREFIX = "veyra.runtime.profile@"


class ProjectResourceError(ValueError):
    """A Project resource selection is invalid or conflicts with source usage."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ProjectResourceService:
    """Manage portable Project bindings without mutating the global Catalog."""

    def __init__(
        self,
        projects: ProjectService,
        catalog: ResourceCatalog,
        custom_components: CustomComponentService | None = None,
    ) -> None:
        self.projects = projects
        self.catalog = catalog
        self.custom_components = custom_components

    def resolve_pin(
        self, project_id: str, reference: str, locked_hash: str | None
    ) -> dict[str, Any]:
        """Resolve only the locally available artifact matching both portable pins."""
        try:
            bindings = self.projects.project_resource_bindings(project_id)
        except ProjectError as exc:
            raise ProjectResourceError(exc.code, str(exc)) from exc
        binding = next((item for item in bindings if item.reference == reference), None)
        if binding is None:
            raise ProjectResourceError(
                "resource_unbound", "Tool resource is not bound to this Project"
            )
        if locked_hash != binding.content_hash:
            raise ProjectResourceError(
                "resource_lock_mismatch", "Agent lock does not match the Project pin"
            )
        try:
            resource = self.catalog.by_reference(reference)
        except ResourceCatalogError as exc:
            raise ProjectResourceError(
                "tool_not_registered",
                "Pinned Tool is not available in the local Catalog",
            ) from exc
        if resource["content_hash"] != binding.content_hash:
            raise ProjectResourceError(
                "project_binding_stale", "Local Catalog cannot resolve the Project pin"
            )
        resource["bound_content_hash"] = binding.content_hash
        return resource

    def list(self, project_id: str) -> dict[str, Any]:
        try:
            bindings = self.projects.project_resource_bindings(project_id)
            usage = self.projects.project_resource_usage(project_id)
        except ProjectError as exc:
            raise ProjectResourceError(exc.code, str(exc)) from exc

        binding_by_reference = {binding.reference: binding for binding in bindings}
        references = set(binding_by_reference) | set(usage)
        custom_by_ref = self._custom_descriptors(project_id)
        resources: list[dict[str, Any]] = []
        missing: list[str] = []
        missing_bindings: list[dict[str, Any]] = []
        seen_custom: set[str] = set()
        for reference in sorted(references):
            if reference.startswith(_RUNTIME_PROFILE_LOCK_PREFIX):
                continue
            custom = custom_by_ref.get(reference)
            if custom is not None:
                resources.append(custom)
                seen_custom.add(reference)
                continue
            try:
                descriptor = self.catalog.by_reference(reference)
            except ResourceCatalogError:
                missing.append(reference)
                if reference in binding_by_reference:
                    missing_bindings.append(
                        {
                            **binding_by_reference[reference].to_dict(),
                            "used_by": usage.get(reference, []),
                        }
                    )
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

        for reference, descriptor in custom_by_ref.items():
            if reference not in seen_custom:
                resources.append(descriptor)

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
            "missing_bindings": missing_bindings,
            "project_count": len(bindings) + len(custom_by_ref),
            "used_count": sum(bool(item["used_by"]) for item in resources),
            "unbound_count": sum(item["scope"] == "used_unbound" for item in resources),
            "builtin_count": sum(item["scope"] == "builtin" for item in resources),
            "stale_count": stale_count,
        }

    def add(
        self,
        project_id: str,
        reference: str,
        *,
        source: str = "manual",
        content_hash: str | None = None,
    ) -> dict[str, Any]:
        with self.projects._writer_lock:
            return self._add(
                project_id, reference, source=source, content_hash=content_hash
            )

    def _add(
        self,
        project_id: str,
        reference: str,
        *,
        source: str,
        content_hash: str | None,
    ) -> dict[str, Any]:
        try:
            current = self.projects.project_resource_bindings(project_id)
        except ProjectError as exc:
            raise ProjectResourceError(exc.code, str(exc)) from exc
        existing = next((item for item in current if item.reference == reference), None)
        if existing is not None:
            if content_hash is not None and content_hash != existing.content_hash:
                raise ProjectResourceError(
                    "resource_binding_conflict",
                    "Project already pins different content; "
                    "remove the unused binding before rebinding.",
                )
            return self.list(project_id)
        try:
            descriptor = self.catalog.by_reference(reference)
        except ResourceCatalogError as exc:
            raise ProjectResourceError(exc.code, str(exc)) from exc
        if content_hash is not None and content_hash != descriptor["content_hash"]:
            raise ProjectResourceError(
                "resource_identity_conflict",
                "Catalog content changed; reload the resource before adding it.",
            )
        if (
            descriptor["kind"] == "component"
            and descriptor.get("component_class", "primitive") == "primitive"
        ):
            raise ProjectResourceError(
                "resource_builtin",
                "platform primitive components are always available",
            )
        try:
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
        with self.projects._writer_lock:
            return self._remove(project_id, reference)

    def _remove(self, project_id: str, reference: str) -> dict[str, Any]:
        try:
            current = self.projects.project_resource_bindings(project_id)
            usage = self.projects.project_resource_usage(
                project_id, include_versions=True
            )
        except ProjectError as exc:
            raise ProjectResourceError(exc.code, str(exc)) from exc
        if reference not in {binding.reference for binding in current}:
            raise ProjectResourceError(
                "resource_not_bound", "resource is not bound to this Project"
            )
        if usage.get(reference):
            raise ProjectResourceError(
                "resource_in_use",
                "resource is still used by an Agent or Workflow "
                "source or saved version",
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

    def _custom_descriptors(self, project_id: str) -> dict[str, dict[str, Any]]:
        if self.custom_components is None:
            return {}
        try:
            return {
                item["reference"]: item
                for item in self.custom_components.descriptors(project_id)
            }
        except (ProjectError, CustomComponentError) as exc:
            code = getattr(exc, "code", "component_invalid")
            raise ProjectResourceError(
                code, "Project Custom Component state is invalid"
            ) from exc
