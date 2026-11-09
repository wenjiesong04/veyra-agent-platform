"""Project-owned Custom Component lifecycle: draft, validate, pin, deprecate."""

from __future__ import annotations

import builtins
import hashlib
import json
import os
import re
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from veyra_agent_platform.contracts.agent import PermissionContract
from veyra_agent_platform.contracts.common import (
    SCHEMA_VERSION,
    ContractValidationError,
    new_uuid7,
)
from veyra_agent_platform.contracts.custom_component import (
    CustomComponentDefinition,
    CustomComponentDependency,
    CustomComponentImplementationKind,
    CustomComponentLifecycle,
    CustomComponentReadiness,
    empty_permissions,
    permissions_subset,
)
from veyra_agent_platform.contracts.resource import (
    ComponentClass,
    ResourceKind,
    ResourceManifest,
    ResourceRef,
    component_storage_path,
)
from veyra_agent_platform.local.projects.layout import ensure_project_layout
from veyra_agent_platform.local.projects.service import ProjectService
from veyra_agent_platform.local.resources.catalog import (
    ResourceCatalog,
    ResourceCatalogError,
)

_SLUG = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_SLUG_NOISE = re.compile(r"[^a-z0-9]+")
_DRAFT_VERSION = "0.0.0"


class CustomComponentError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _CustomComponentRecord(TypedDict):
    root: Path
    draft: CustomComponentDefinition | None
    versions: list[CustomComponentDefinition]
    deprecated: list[str]
    definition: CustomComponentDefinition


class CustomComponentService:
    """Persist Custom Components under components/composite/{slug}/."""

    def __init__(self, projects: ProjectService, catalog: ResourceCatalog) -> None:
        self.projects = projects
        self.catalog = catalog
        self.project_resource_readiness: (
            Callable[[dict[str, Any]], dict[str, Any]] | None
        ) = None
        self.model_recipe_configured: Callable[[], bool] | None = None

    def list(self, project_id: str) -> dict[str, Any]:
        records = self._records(project_id)
        return {
            "schema_version": SCHEMA_VERSION,
            "project_id": project_id,
            "components": [self._summary(item) for item in records],
        }

    def get(
        self,
        project_id: str,
        component_id: str,
        *,
        version: str | None = None,
    ) -> dict[str, Any]:
        record = self._record(project_id, component_id)
        if version is None or version == _DRAFT_VERSION:
            if record["draft"] is None:
                if version == _DRAFT_VERSION:
                    raise CustomComponentError(
                        "component_draft_missing", "Custom Component draft is missing"
                    )
                published = record["versions"]
                if not published:
                    raise CustomComponentError(
                        "component_not_found", "Custom Component version is missing"
                    )
                return self._public(published[-1], record)
            return self._public(record["draft"], record)
        definition = next(
            (item for item in record["versions"] if item.version == version),
            None,
        )
        if definition is None:
            raise CustomComponentError(
                "component_not_found", "Custom Component version is missing"
            )
        return self._public(definition, record)

    def find_builder_proposal(
        self, project_id: str, proposal_id: str
    ) -> dict[str, Any] | None:
        """Find the durable component receipt for an idempotent Builder proposal."""

        for record in self._records(project_id):
            for definition in reversed(record["versions"]):
                if definition.metadata.get("builder.proposal_id") == proposal_id:
                    return self._public(definition, record)
            if (
                record["draft"] is not None
                and record["draft"].metadata.get("builder.proposal_id") == proposal_id
            ):
                return self._public(record["draft"], record)
        return None

    def resolve(self, project_id: str, reference: str) -> CustomComponentDefinition:
        ref = ResourceRef.from_string(reference, "custom component")
        record = self._record(project_id, ref.resource_id)
        if record["definition"].project_id != project_id:
            raise CustomComponentError(
                "component_project_mismatch",
                "Custom Component does not belong to this Project",
            )
        if ref.version == _DRAFT_VERSION:
            raise CustomComponentError(
                "component_not_pinned",
                "Agent cannot pin a mutable Custom Component draft",
            )
        definition = next(
            (item for item in record["versions"] if item.version == ref.version),
            None,
        )
        if definition is None:
            raise CustomComponentError(
                "component_not_found", "Pinned Custom Component version is missing"
            )
        return definition

    def descriptors(self, project_id: str) -> builtins.list[dict[str, Any]]:
        usage = self.projects.project_resource_usage(project_id, include_versions=True)
        descriptors: list[dict[str, Any]] = []
        for record in self._records(project_id):
            for definition in record["versions"]:
                descriptors.append(
                    self._descriptor(
                        definition, record, usage.get(definition.ref(), [])
                    )
                )
        return descriptors

    def create_draft(
        self,
        project_id: str,
        payload: dict[str, Any],
        *,
        component_id: str | None = None,
    ) -> dict[str, Any]:
        with self.projects._writer_lock:
            _, root, manifest_path, previous, manifest = (
                self.projects._project_manifest_state(project_id)
            )
            occupied_names = {
                self._read_name(root, entry.slug) for entry in manifest.components
            }
            occupied_slugs = {entry.slug for entry in manifest.components}
            display_name = self.projects._allocate_agent_name(
                str(
                    payload.get("display_name")
                    or payload.get("name")
                    or "New Component"
                ),
                occupied_names,
            )
            slug = self.projects._allocate_agent_slug(
                _component_slug(display_name), occupied_slugs
            )
            now = _utc_now()
            component_id = component_id or new_uuid7()
            definition = CustomComponentDefinition.from_dict(
                {
                    "schema_version": SCHEMA_VERSION,
                    "component_id": component_id,
                    "project_id": project_id,
                    "slug": slug,
                    "display_name": display_name,
                    "description": str(
                        payload.get("description") or "A Project Custom Component."
                    ),
                    "version": _DRAFT_VERSION,
                    "inputs": payload.get("inputs") or {"input": "object"},
                    "outputs": payload.get("outputs") or {"output": "object"},
                    "implementation": payload.get("implementation")
                    or {
                        "kind": "model_recipe",
                        "instruction": "Describe the reusable capability.",
                        "model_ref": "model.primary",
                    },
                    "metadata": payload.get("metadata") or {},
                    "dependencies": payload.get("dependencies") or [],
                    "required_permissions": payload.get("required_permissions")
                    or empty_permissions(),
                    "provenance": payload.get("provenance") or "manual",
                    "lifecycle": "draft",
                    "created_at": now,
                    "updated_at": now,
                }
            )
            validated = self._validate_definition(project_id, definition, persist=False)
            self._install_package(
                project_id=project_id,
                root=root,
                manifest_path=manifest_path,
                previous_manifest_text=previous,
                manifest=manifest,
                definition=validated,
                draft=True,
            )
            return self.get(project_id, component_id)

    def update_draft(
        self, project_id: str, component_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        with self.projects._writer_lock:
            record = self._record(project_id, component_id)
            current = record["draft"] or (
                record["versions"][-1] if record["versions"] else None
            )
            if current is None:
                raise CustomComponentError(
                    "component_not_found", "Custom Component is missing"
                )
            now = _utc_now()
            merged = current.to_dict()
            for key in (
                "display_name",
                "description",
                "inputs",
                "outputs",
                "implementation",
                "metadata",
                "dependencies",
                "required_permissions",
                "provenance",
            ):
                if key in payload:
                    merged[key] = payload[key]
            merged["version"] = _DRAFT_VERSION
            merged["lifecycle"] = "draft"
            merged["updated_at"] = now
            if record["draft"] is None:
                merged["created_at"] = now
            definition = self._validate_definition(
                project_id, CustomComponentDefinition.from_dict(merged), persist=False
            )
            self._write_draft(record["root"], definition)
            return self.get(project_id, component_id)

    def validate(
        self, project_id: str, component_id: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if payload:
            self.update_draft(project_id, component_id, payload)
        record = self._record(project_id, component_id)
        current = record["draft"] or (
            record["versions"][-1] if record["versions"] else None
        )
        if current is None:
            raise CustomComponentError(
                "component_not_found", "Custom Component is missing"
            )
        definition = self._validate_definition(project_id, current, persist=False)
        return self._public(definition, record)

    def publish(
        self,
        project_id: str,
        component_id: str,
        *,
        version: str | None = None,
    ) -> dict[str, Any]:
        with self.projects._writer_lock:
            record = self._record(project_id, component_id)
            draft = record["draft"]
            if draft is None:
                raise CustomComponentError(
                    "component_draft_missing",
                    "Publish requires an editable Custom Component draft",
                )
            published = self._validate_definition(project_id, draft, persist=False)
            if (
                published.implementation.kind
                is CustomComponentImplementationKind.COMPOSITE_GRAPH
            ):
                published = CustomComponentDefinition.from_dict(
                    {
                        **published.to_dict(),
                        "readiness": "design_only",
                    }
                )
            elif published.readiness is CustomComponentReadiness.UNAVAILABLE:
                raise CustomComponentError(
                    "component_unavailable",
                    "Custom Component dependencies are unavailable",
                )
            next_version = version or _next_version(
                [item.version for item in record["versions"]]
            )
            existing = {item.version for item in record["versions"]}
            if next_version in existing:
                raise CustomComponentError(
                    "component_version_exists",
                    "Published Custom Component versions are immutable",
                )
            if record["versions"] and _semver_tuple(next_version) <= _semver_tuple(
                record["versions"][-1].version
            ):
                raise CustomComponentError(
                    "component_version_not_greater",
                    "New Custom Component versions must increase semver",
                )
            now = _utc_now()
            frozen = CustomComponentDefinition.from_dict(
                {
                    **published.to_dict(),
                    "version": next_version,
                    "lifecycle": "active",
                    "updated_at": now,
                }
            )
            versions_dir = record["root"] / "versions"
            versions_dir.mkdir(mode=0o700, exist_ok=True)
            self.projects.atomic_write(
                versions_dir / f"{next_version}.json",
                self.projects._canonical_source(frozen.to_dict()),
            )
            draft_path = record["root"] / "draft.json"
            if draft_path.exists():
                draft_path.unlink()
            self._write_manifest(record["root"], frozen)
            self._replace_listing(project_id, frozen)
            return self.get(project_id, component_id, version=next_version)

    def install_synced_definition(
        self, project_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Install one validated published definition without executing it."""
        definition = CustomComponentDefinition.from_dict(payload)
        if definition.project_id != project_id or definition.version == _DRAFT_VERSION:
            raise CustomComponentError(
                "component_project_mismatch", "synced Component definition is invalid"
            )
        with self.projects._writer_lock:
            project = self.projects.repository.project(project_id)
            if project is None:
                raise CustomComponentError("component_not_found", "Project is missing")
            root = self.projects._existing_root(project["root_path"])
            manifest_path = self.projects._safe_file(
                root, Path("project.vproject.yaml")
            )
            package = root / "components" / "composite" / definition.slug
            if package.exists():
                record = self._record(project_id, definition.component_id)
                existing = next(
                    (
                        item
                        for item in record["versions"]
                        if item.version == definition.version
                    ),
                    None,
                )
                if existing is not None:
                    if existing.content_hash() != definition.content_hash():
                        raise CustomComponentError(
                            "component_integrity_conflict",
                            "immutable Component version hash differs",
                        )
                    return self.get(
                        project_id, definition.component_id, version=definition.version
                    )
            else:
                _, _, _, previous, manifest = self.projects._project_manifest_state(
                    project_id
                )
                staging = (
                    package.parent / f".{definition.slug}.veyra-sync-{new_uuid7()}"
                )
                staging.mkdir(mode=0o700, parents=True)
                try:
                    self._write_manifest(staging, definition)
                    (staging / "versions").mkdir(mode=0o700)
                    self.projects.atomic_write(
                        staging / "versions" / f"{definition.version}.json",
                        self.projects._canonical_source(definition.to_dict()),
                    )
                    self.projects._fsync_tree(staging)
                    os.replace(staging, package)
                    listing = manifest.to_dict()
                    listing.setdefault("components", []).append(
                        {
                            "kind": "component",
                            "resource_id": definition.component_id,
                            "slug": definition.slug,
                            "version": definition.version,
                            "path": component_storage_path(
                                ComponentClass.COMPOSITE, definition.slug
                            ),
                            "component_class": "composite",
                        }
                    )
                    self.projects.atomic_write(
                        manifest_path, self.projects._canonical_source(listing)
                    )
                    self.projects.index(root)
                except BaseException:
                    if staging.exists():
                        shutil.rmtree(staging, ignore_errors=True)
                    if package.exists():
                        shutil.rmtree(package, ignore_errors=True)
                    self.projects.atomic_write(manifest_path, previous)
                    raise
            versions = package / "versions"
            versions.mkdir(mode=0o700, exist_ok=True)
            self.projects.atomic_write(
                versions / f"{definition.version}.json",
                self.projects._canonical_source(definition.to_dict()),
            )
            self._write_manifest(package, definition)
            self._replace_listing(project_id, definition)
            return self.get(
                project_id, definition.component_id, version=definition.version
            )

    def deprecate(
        self, project_id: str, component_id: str, version: str
    ) -> dict[str, Any]:
        with self.projects._writer_lock:
            record = self._record(project_id, component_id)
            if version not in {item.version for item in record["versions"]}:
                raise CustomComponentError(
                    "component_not_found", "Custom Component version is missing"
                )
            deprecated = set(record["deprecated"]) | {version}
            self.projects.atomic_write(
                record["root"] / "lifecycle.json",
                self.projects._canonical_source(
                    {"schema_version": SCHEMA_VERSION, "deprecated": sorted(deprecated)}
                ),
            )
            return self.get(project_id, component_id, version=version)

    def delete_draft(self, project_id: str, component_id: str) -> dict[str, Any]:
        with self.projects._writer_lock:
            record = self._record(project_id, component_id)
            if record["versions"]:
                draft_path = record["root"] / "draft.json"
                if not draft_path.exists():
                    raise CustomComponentError(
                        "component_in_use",
                        "Published Custom Component versions cannot be deleted; "
                        "deprecate the version instead.",
                    )
                draft_path.unlink()
                return self.list(project_id)
            usage = self.projects.project_resource_usage(
                project_id, include_versions=True
            )
            if any(reference.startswith(f"{component_id}@") for reference in usage):
                raise CustomComponentError(
                    "component_in_use",
                    "Custom Component is still referenced by an Agent or Workflow",
                )
            shutil.rmtree(record["root"])
            self._remove_listing(project_id, component_id)
            return self.list(project_id)

    def resolve_dependency(
        self, project_id: str, dependency: CustomComponentDependency
    ) -> dict[str, Any]:
        try:
            resource = self.catalog.by_reference(dependency.reference)
        except ResourceCatalogError as exc:
            raise CustomComponentError(
                "unavailable_dependency",
                "Pinned Custom Component dependency is not in the local Catalog",
            ) from exc
        if resource["content_hash"] != dependency.content_hash:
            raise CustomComponentError(
                "dependency_lock_mismatch",
                "Custom Component dependency no longer matches the pinned hash",
            )
        bindings = {
            item.reference: item
            for item in self.projects.project_resource_bindings(project_id)
        }
        binding = bindings.get(dependency.reference)
        if binding is None:
            raise CustomComponentError(
                "dependency_not_project_bound",
                "Custom Component dependencies must be bound to this Project",
            )
        if resource.get("kind") not in {"tool", "mcp_tool"}:
            raise CustomComponentError(
                "dependency_not_tool", "Custom Component dependency must be a Tool"
            )
        if binding.content_hash != dependency.content_hash:
            raise CustomComponentError(
                "dependency_lock_mismatch",
                "Project Tool pin does not match the Custom Component lock",
            )
        resource = dict(resource)
        resource["bound_content_hash"] = dependency.content_hash
        return resource

    def _validate_definition(
        self,
        project_id: str,
        definition: CustomComponentDefinition,
        *,
        persist: bool,
    ) -> CustomComponentDefinition:
        del persist
        if definition.project_id != project_id:
            raise CustomComponentError(
                "component_project_mismatch",
                "Custom Component does not belong to this Project",
            )
        derived = PermissionContract.from_dict(empty_permissions())
        dependencies = list(definition.dependencies)
        readiness = CustomComponentReadiness.READY
        kind = definition.implementation.kind
        if kind is not CustomComponentImplementationKind.TOOL_WRAPPER and dependencies:
            raise CustomComponentError(
                "unsupported_dependency_kind",
                "V1 only supports exact Tool dependencies on tool_wrapper components",
            )
        if kind is CustomComponentImplementationKind.COMPOSITE_GRAPH:
            readiness = CustomComponentReadiness.DESIGN_ONLY
            if definition.implementation.graph is None:
                raise CustomComponentError(
                    "composite_graph_not_implemented",
                    "composite_graph is design-only in this slice",
                )
        elif kind is CustomComponentImplementationKind.MODEL_RECIPE:
            if any(field.is_artifact() for field in definition.inputs.values()) or any(
                field.is_artifact() for field in definition.outputs.values()
            ):
                readiness = CustomComponentReadiness.REQUIRES_CONFIGURATION
            if (
                self.model_recipe_configured is not None
                and not self.model_recipe_configured()
            ):
                readiness = CustomComponentReadiness.REQUIRES_CONFIGURATION
        elif kind is CustomComponentImplementationKind.TOOL_WRAPPER:
            reference = definition.implementation.tool_reference
            assert reference is not None
            if definition.dependencies and (
                len(definition.dependencies) != 1
                or definition.dependencies[0].reference != reference
            ):
                raise CustomComponentError(
                    "dependency_reference_mismatch",
                    "tool_wrapper dependencies must match its selected Tool reference",
                )
            bindings = {
                item.reference: item
                for item in self.projects.project_resource_bindings(project_id)
            }
            binding = bindings.get(reference)
            try:
                resource = self.catalog.by_reference(reference)
            except ResourceCatalogError as exc:
                raise CustomComponentError(
                    "unavailable_dependency",
                    "Tool wrapper must pin a Catalog Tool",
                ) from exc
            if binding is None:
                raise CustomComponentError(
                    "dependency_not_project_bound",
                    "Tool wrapper must use a Tool already bound to this Project",
                )
            if resource.get("kind") not in {"tool", "mcp_tool"}:
                raise CustomComponentError(
                    "dependency_not_tool", "Tool wrapper dependency must be a Tool"
                )
            digest = binding.content_hash
            if (
                definition.dependencies
                and definition.dependencies[0].content_hash != digest
            ):
                raise CustomComponentError(
                    "dependency_lock_mismatch",
                    "tool_wrapper dependency hash must match the Project Tool pin",
                )
            projected = resource
            if self.project_resource_readiness is not None:
                projected = self.project_resource_readiness(
                    {
                        **resource,
                        "scope": "project",
                        "binding_status": (
                            "current" if digest == resource["content_hash"] else "stale"
                        ),
                        "bound_content_hash": digest,
                    }
                )
            if digest != resource["content_hash"]:
                readiness = CustomComponentReadiness.UNAVAILABLE
            elif (
                projected.get("availability") == "requires_configuration"
                or projected.get("runtime_status") == "runtime_not_configured"
            ):
                readiness = CustomComponentReadiness.REQUIRES_CONFIGURATION
            elif (
                projected.get("availability") != "ready"
                or projected.get("runtime_status") != "supported"
            ):
                readiness = CustomComponentReadiness.UNAVAILABLE
            derived = PermissionContract.from_dict(resource["required_permissions"])
            dependencies = [
                CustomComponentDependency.from_dict(
                    {"reference": reference, "content_hash": digest}
                )
            ]
        elif kind is CustomComponentImplementationKind.TRANSFORM:
            readiness = CustomComponentReadiness.READY
        if not permissions_subset(definition.required_permissions, derived):
            raise CustomComponentError(
                "permission_overgrant",
                "Custom Component cannot declare permissions beyond its dependencies",
            )
        payload = definition.to_dict()
        payload["required_permissions"] = derived.to_dict()
        payload["dependencies"] = [item.to_dict() for item in dependencies]
        payload["readiness"] = readiness.value
        return CustomComponentDefinition.from_dict(payload)

    def _records(self, project_id: str) -> builtins.list[_CustomComponentRecord]:
        _, root, _, _, manifest = self.projects._project_manifest_state(project_id)
        records: list[_CustomComponentRecord] = []
        for entry in manifest.components:
            if entry.component_class is not ComponentClass.COMPOSITE:
                continue
            records.append(
                self._load_record(project_id, root, entry.resource_id, entry.slug)
            )
        return records

    def _record(self, project_id: str, component_id: str) -> _CustomComponentRecord:
        _, root, _, _, manifest = self.projects._project_manifest_state(project_id)
        entry = next(
            (item for item in manifest.components if item.resource_id == component_id),
            None,
        )
        if entry is None:
            raise CustomComponentError(
                "component_not_found", "Custom Component is not in this Project"
            )
        return self._load_record(project_id, root, component_id, entry.slug)

    def _load_record(
        self, project_id: str, project_root: Path, component_id: str, slug: str
    ) -> _CustomComponentRecord:
        package = self.projects._safe_directory(
            project_root, Path(component_storage_path(ComponentClass.COMPOSITE, slug))
        )
        draft = _read_definition(package / "draft.json")
        versions: list[CustomComponentDefinition] = []
        versions_dir = package / "versions"
        if versions_dir.is_dir():
            for path in sorted(versions_dir.glob("*.json")):
                loaded = _read_definition(path)
                if loaded is not None:
                    versions.append(loaded)
        versions.sort(key=lambda item: _semver_tuple(item.version))
        lifecycle_path = package / "lifecycle.json"
        deprecated: list[str] = []
        if lifecycle_path.is_file():
            payload = json.loads(lifecycle_path.read_text(encoding="utf-8"))
            deprecated = [
                str(item)
                for item in payload.get("deprecated", [])
                if isinstance(item, str)
            ]
        current = draft or (versions[-1] if versions else None)
        if current is None or current.component_id != component_id:
            raise CustomComponentError(
                "component_not_found", "Custom Component package is incomplete"
            )
        if current.project_id != project_id:
            raise CustomComponentError(
                "component_project_mismatch",
                "Custom Component does not belong to this Project",
            )
        return {
            "root": package,
            "draft": draft,
            "versions": versions,
            "deprecated": deprecated,
            "definition": current,
        }

    def _install_package(
        self,
        *,
        project_id: str,
        root: Path,
        manifest_path: Path,
        previous_manifest_text: str,
        manifest: Any,
        definition: CustomComponentDefinition,
        draft: bool,
    ) -> None:
        ensure_project_layout(root)
        relative = component_storage_path(ComponentClass.COMPOSITE, definition.slug)
        composite_root = self.projects._safe_directory(
            root, Path("components") / "composite"
        )
        target = composite_root / definition.slug
        if target.exists() or target.is_symlink():
            raise CustomComponentError(
                "component_path_exists", "Custom Component path already exists"
            )
        staging = composite_root / f".{definition.slug}.veyra-staging-{new_uuid7()}"
        listing = manifest.to_dict()
        listing.setdefault("components", []).append(
            {
                "kind": "component",
                "resource_id": definition.component_id,
                "slug": definition.slug,
                "version": definition.version if not draft else _DRAFT_VERSION,
                "path": relative,
                "component_class": "composite",
            }
        )
        try:
            staging.mkdir(mode=0o700, parents=True)
            self._write_manifest(staging, definition)
            self.projects.atomic_write(
                staging / "draft.json",
                self.projects._canonical_source(definition.to_dict()),
            )
            self.projects._fsync_tree(staging)
            os.replace(staging, target)
            self.projects.atomic_write(
                manifest_path, self.projects._canonical_source(listing)
            )
            self.projects.index(root)
        except BaseException:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            self.projects.atomic_write(manifest_path, previous_manifest_text)
            raise
        del project_id

    def _write_draft(
        self, package: Path, definition: CustomComponentDefinition
    ) -> None:
        self.projects.atomic_write(
            package / "draft.json",
            self.projects._canonical_source(definition.to_dict()),
        )

    def _write_manifest(
        self, package: Path, definition: CustomComponentDefinition
    ) -> None:
        self.projects.atomic_write(
            package / "resource.yaml",
            self.projects._canonical_source(
                ResourceManifest(
                    schema_version=SCHEMA_VERSION,
                    kind=ResourceKind.COMPONENT,
                    resource_id=definition.component_id,
                    version=definition.version,
                    slug=definition.slug,
                    name=definition.display_name,
                    description=definition.description,
                    component_class=ComponentClass.COMPOSITE,
                ).to_dict()
            ),
        )

    def _replace_listing(
        self, project_id: str, definition: CustomComponentDefinition
    ) -> None:
        _, root, manifest_path, _, manifest = self.projects._project_manifest_state(
            project_id
        )
        payload = manifest.to_dict()
        components = []
        for item in payload.get("components", []):
            if item.get("resource_id") == definition.component_id:
                item = dict(item)
                item["version"] = definition.version
                item["slug"] = definition.slug
            components.append(item)
        payload["components"] = components
        self.projects.atomic_write(
            manifest_path, self.projects._canonical_source(payload)
        )
        self.projects.index(root)

    def _remove_listing(self, project_id: str, component_id: str) -> None:
        _, root, manifest_path, _, manifest = self.projects._project_manifest_state(
            project_id
        )
        payload = manifest.to_dict()
        payload["components"] = [
            item
            for item in payload.get("components", [])
            if item.get("resource_id") != component_id
        ]
        self.projects.atomic_write(
            manifest_path, self.projects._canonical_source(payload)
        )
        self.projects.index(root)

    def _read_name(self, root: Path, slug: str) -> str:
        path = (
            root
            / component_storage_path(ComponentClass.COMPOSITE, slug)
            / "resource.yaml"
        )
        if not path.is_file():
            return slug
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return slug
        return str(payload.get("name") or slug)

    def _summary(self, record: _CustomComponentRecord) -> dict[str, Any]:
        current = record["draft"] or record["definition"]
        latest = record["versions"][-1] if record["versions"] else None
        return {
            "schema_version": SCHEMA_VERSION,
            "component_id": current.component_id,
            "project_id": current.project_id,
            "slug": current.slug,
            "display_name": current.display_name,
            "description": current.description,
            "draft": None
            if record["draft"] is None
            else self._public(record["draft"], record),
            "latest_version": None if latest is None else latest.version,
            "versions": [
                {
                    "version": item.version,
                    "reference": item.ref(),
                    "lifecycle": (
                        "deprecated"
                        if item.version in record["deprecated"]
                        else "active"
                    ),
                    "implementation_kind": item.implementation.kind.value,
                    "readiness": item.readiness.value,
                    "content_hash": item.content_hash(),
                }
                for item in record["versions"]
            ],
        }

    def _public(
        self, definition: CustomComponentDefinition, record: _CustomComponentRecord
    ) -> dict[str, Any]:
        payload = definition.to_dict()
        payload["reference"] = definition.ref()
        payload["content_hash"] = definition.content_hash()
        payload["deprecated"] = definition.version in record["deprecated"]
        if definition.version in record["deprecated"]:
            payload["lifecycle"] = CustomComponentLifecycle.DEPRECATED.value
        return payload

    def _descriptor(
        self,
        definition: CustomComponentDefinition,
        record: _CustomComponentRecord,
        used_by: builtins.list[dict[str, str]],
    ) -> dict[str, Any]:
        deprecated = definition.version in record["deprecated"]
        availability = definition.readiness.value
        runtime_status = (
            "runtime_not_supported"
            if availability == "design_only"
            else "runtime_not_configured"
            if availability == "requires_configuration"
            else "supported"
            if availability == "ready"
            else "runtime_not_supported"
        )
        if deprecated:
            availability = "disabled"
        return {
            "schema_version": SCHEMA_VERSION,
            "resource_id": definition.component_id,
            "kind": "component",
            "component_class": "composite",
            "version": definition.version,
            "reference": definition.ref(),
            "name": definition.display_name,
            "description": definition.description,
            "origin": "project",
            "content_hash": definition.content_hash(),
            "availability": availability,
            "factory_selectable": not deprecated,
            "runtime_status": runtime_status,
            "required_permissions": definition.required_permissions.to_dict(),
            "tags": ["custom-component", definition.implementation.kind.value],
            "spec": {
                "implementation_kind": definition.implementation.kind.value,
                "inputs": definition.to_dict()["inputs"],
                "outputs": definition.to_dict()["outputs"],
                "ui": {
                    "category": "custom",
                    "icon": "box",
                    "title": definition.display_name,
                },
            },
            "scope": "project",
            "binding_status": "current",
            "binding_source": "manual",
            "bound_content_hash": definition.content_hash(),
            "used_by": used_by,
        }


def _component_slug(name: str) -> str:
    folded = _SLUG_NOISE.sub("-", name.casefold()).strip("-")[:48].strip("-")
    if folded and _SLUG.fullmatch(folded):
        return folded
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
    return f"component-{digest}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _semver_tuple(value: str) -> tuple[int, int, int]:
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def _next_version(existing: list[str]) -> str:
    if not existing:
        return "1.0.0"
    major, minor, patch = _semver_tuple(max(existing, key=_semver_tuple))
    return f"{major}.{minor}.{patch + 1}"


def _read_definition(path: Path) -> CustomComponentDefinition | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return CustomComponentDefinition.from_dict(payload)
    except (OSError, json.JSONDecodeError, ContractValidationError, TypeError):
        raise CustomComponentError(
            "component_invalid", "Custom Component definition is invalid"
        ) from None
