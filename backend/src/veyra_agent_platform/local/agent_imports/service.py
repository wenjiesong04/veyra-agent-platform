"""Analyze external Agent files and translate them into Veyra drafts."""

from __future__ import annotations

import io
import json
import os
import re
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

import yaml  # type: ignore[import-untyped]

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.common import (
    ContractValidationError,
    new_uuid7,
    require_uuid7,
)
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService
from veyra_agent_platform.local.resources import ResourceCatalog, ResourceCatalogError

IMPORT_SCHEMA = "agent.import.v1"
IR_SCHEMA = "agent.import.ir.v1"
COMPATIBILITY_SCHEMA = "agent.import.compatibility.v1"
MANIFEST_SCHEMA = "agent.import.manifest.v1"
MAX_ARCHIVE_BYTES = 12_000_000
MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 10_000_000
MAX_FILES = 256

_YAML_SUFFIXES = {".yaml", ".yml"}
_TEXT_SUFFIXES = _YAML_SUFFIXES | {".md", ".markdown", ".txt", ".json", ".toml"}
_FORBIDDEN_NAMES = {".env", "credentials.json", "id_rsa"}
_FORBIDDEN_SUFFIXES = {".key", ".pem", ".p12", ".token"}
_CODE_SUFFIXES = {".py", ".js", ".ts", ".sh", ".bat", ".exe", ".bin"}
_UNIX_SYMLINK_MODE = 0o120000
_FIELD_NAME = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_SECRET_MARKERS = (
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN OPENSSH PRIVATE KEY-----",
    b"ghp_",
    b"github_pat_",
    b"AKIA",
)
_TOOL_ALIASES = {
    "filesystem": "veyra.tool.filesystem.read",
    "filesystem-read": "veyra.tool.filesystem.read",
    "filesystem.read": "veyra.tool.filesystem.read",
    "filesystem_read": "veyra.tool.filesystem.read",
    "filesystem-list": "veyra.tool.filesystem.list",
    "filesystem.list": "veyra.tool.filesystem.list",
    "filesystem_search": "veyra.tool.filesystem.search",
    "filesystem-search": "veyra.tool.filesystem.search",
    "filesystem.search": "veyra.tool.filesystem.search",
    "filesystem-write": "veyra.tool.filesystem.write",
    "filesystem.write": "veyra.tool.filesystem.write",
    "filesystem_write": "veyra.tool.filesystem.write",
    "search": "veyra.tool.web.search",
    "web-search": "veyra.tool.web.search",
    "web.search": "veyra.tool.web.search",
    "web_search": "veyra.tool.web.search",
    "browser": "veyra.tool.browser.navigate",
    "browser.navigate": "veyra.tool.browser.navigate",
    "http": "veyra.tool.http.request",
    "http-request": "veyra.tool.http.request",
    "http.request": "veyra.tool.http.request",
    "github": "veyra.tool.github.read",
    "github-read": "veyra.tool.github.read",
    "github.read": "veyra.tool.github.read",
}
_SUPPORTED_TYPES = {"string", "boolean", "integer", "number", "object", "array"}


class AgentImportError(ValueError):
    """An external Agent source cannot be analyzed or applied."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AgentImportService:
    """Keep external input as an analyzed draft until the user applies it."""

    def __init__(
        self,
        root: Path,
        projects: ProjectService,
        catalog: ResourceCatalog,
    ) -> None:
        self.root = root
        self.projects = projects
        self.catalog = catalog

    def analyze_file(self, *, filename: str | None, contents: bytes) -> dict[str, Any]:
        if not isinstance(filename, str) or not filename.strip():
            raise AgentImportError(
                "agent_import_filename_invalid", "A source filename is required"
            )
        normalized_name = Path(filename.replace("\\", "/")).name
        lower_name = normalized_name.lower()
        if lower_name.endswith(".zip"):
            files = _archive_files(contents)
            return self._analyze(files, source_kind="zip", source_name=normalized_name)
        if Path(normalized_name).suffix.lower() not in _YAML_SUFFIXES:
            raise AgentImportError(
                "agent_import_file_type_invalid",
                "Agent import accepts YAML or ZIP files",
            )
        _assert_body(contents)
        return self._analyze(
            {normalized_name: contents}, source_kind="yaml", source_name=normalized_name
        )

    def analyze_folder(self, path: str) -> dict[str, Any]:
        files, source_name = _folder_files(path)
        return self._analyze(files, source_kind="folder", source_name=source_name)

    def analyze_uploaded_folder(
        self, files: Mapping[str, bytes], *, source_name: str | None = None
    ) -> dict[str, Any]:
        """Analyze a browser-provided folder without materializing it on disk."""
        normalized: dict[str, bytes] = {}
        total = 0
        for raw_path, body in files.items():
            path = _safe_relative_path(raw_path)
            _assert_allowed_input_path(path)
            _assert_body(body)
            if len(normalized) >= MAX_FILES:
                raise AgentImportError(
                    "agent_import_folder_too_large",
                    "Agent folder contains too many files",
                )
            total += len(body)
            if total > MAX_TOTAL_BYTES:
                raise AgentImportError(
                    "agent_import_folder_too_large",
                    "Agent folder files exceed the total size limit",
                )
            normalized[path] = body
        if not normalized:
            raise AgentImportError(
                "agent_import_source_missing", "The selected Agent folder is empty"
            )
        return self._analyze(
            normalized,
            source_kind="folder",
            source_name=source_name or _folder_display_name(normalized),
        )

    def get(self, import_id: str) -> dict[str, Any]:
        record = self._read_record(import_id)
        return dict(record)

    def apply(
        self,
        import_id: str,
        *,
        project_id: str,
        confirm: bool,
        name: str | None = None,
        description: str | None = None,
        parent_agent_id: str | None = None,
    ) -> dict[str, Any]:
        if not confirm:
            raise AgentImportError(
                "agent_import_confirmation_required",
                "Explicit confirmation is required to apply an Agent import",
            )
        record = self._read_record(import_id)
        previous = record.get("applied_agent")
        if isinstance(previous, dict):
            return {
                "schema_version": IMPORT_SCHEMA,
                "import": record,
                "agent": previous,
            }
        generated = record.get("generated_source")
        if not isinstance(generated, dict):
            raise AgentImportError(
                "agent_import_record_invalid",
                "Import record has no generated Agent source",
            )
        try:
            source = AgentSource.from_dict(generated)
        except (ContractValidationError, TypeError, ValueError) as exc:
            raise AgentImportError(
                "agent_import_record_invalid", "Generated Agent source is invalid"
            ) from exc
        manifest = record.get("manifest")
        if not isinstance(manifest, dict):
            raise AgentImportError(
                "agent_import_record_invalid",
                "Import record has no compatibility manifest",
            )
        try:
            created = self.projects.create_agent_from_source(
                project_id=project_id,
                source=source,
                name=name,
                description=description,
                parent_agent_id=parent_agent_id,
                extra_files={
                    "import/manifest.json": (
                        json.dumps(
                            manifest, ensure_ascii=False, sort_keys=True, indent=2
                        )
                        + "\n"
                    ).encode("utf-8")
                },
            )
        except ProjectError as exc:
            raise AgentImportError(exc.code, str(exc)) from exc
        record["state"] = "applied"
        record["applied_agent"] = created
        self._write_record(record)
        return {"schema_version": IMPORT_SCHEMA, "import": record, "agent": created}

    def _analyze(
        self,
        files: Mapping[str, bytes],
        *,
        source_kind: str,
        source_name: str,
    ) -> dict[str, Any]:
        for body in files.values():
            _scan_secret_markers(body)
        candidates = sorted(
            (path for path in files if Path(path).suffix.lower() in _YAML_SUFFIXES),
            key=_candidate_key,
        )
        if not candidates:
            raise AgentImportError(
                "agent_import_source_missing", "No YAML Agent definition was found"
            )
        parse_failures = 0
        for source_path in candidates:
            try:
                payload = _yaml_mapping(files[source_path])
            except AgentImportError:
                parse_failures += 1
                if len(candidates) == 1:
                    raise
                continue
            if _looks_like_veyra_source(payload):
                try:
                    source = AgentSource.from_dict(payload)
                except (ContractValidationError, TypeError, ValueError) as exc:
                    raise AgentImportError(
                        "agent_import_veyra_invalid",
                        "The file looks like a Veyra Agent but does not satisfy "
                        "the Veyra source contract",
                    ) from exc
                return self._record_from_veyra(
                    source,
                    source_kind=source_kind,
                    source_name=source_name,
                    source_path=source_path,
                    files=files,
                )
            if _looks_like_generic_source(payload):
                return self._record_from_generic(
                    payload,
                    source_kind=source_kind,
                    source_name=source_name,
                    source_path=source_path,
                    files=files,
                )
        if parse_failures == len(candidates):
            raise AgentImportError(
                "agent_import_yaml_invalid",
                "The YAML Agent definition could not be parsed",
            )
        raise AgentImportError(
            "agent_import_format_unknown",
            "No supported generic Agent definition was found in the source",
        )

    def _record_from_veyra(
        self,
        source: AgentSource,
        *,
        source_kind: str,
        source_name: str,
        source_path: str,
        files: Mapping[str, bytes],
    ) -> dict[str, Any]:
        capabilities = [
            {
                "kind": "agent_source",
                "original": "Veyra Agent Source",
                "status": "supported",
                "reason": "The source already matches the Veyra Agent contract",
                "included": True,
            }
        ]
        manifest = self._manifest(
            source_kind=source_kind,
            source_name=source_name,
            source_path=source_path,
            files=files,
            detected_format="veyra_agent_yaml",
            compatibility=1.0,
            capabilities=capabilities,
            warnings=[],
        )
        return self._persist(
            source_kind=source_kind,
            source_name=source_name,
            source_path=source_path,
            detected_format="veyra_agent_yaml",
            compatibility=1.0,
            preview=_source_preview(source, files, source_path),
            capabilities=capabilities,
            warnings=[],
            generated_source=source.to_dict(),
            manifest=manifest,
        )

    def _record_from_generic(
        self,
        payload: Mapping[str, Any],
        *,
        source_kind: str,
        source_name: str,
        source_path: str,
        files: Mapping[str, bytes],
    ) -> dict[str, Any]:
        metadata = payload.get("metadata")
        metadata_map = metadata if isinstance(metadata, Mapping) else {}
        nested_spec = payload.get("spec")
        spec = nested_spec if isinstance(nested_spec, Mapping) else payload
        warnings: list[dict[str, Any]] = []
        capabilities: list[dict[str, Any]] = []
        name = _clean_text(
            spec.get("name") or metadata_map.get("name") or payload.get("name"),
            _display_name(source_path),
            field="name",
            limit=120,
        )
        description = _clean_text(
            spec.get("description")
            or metadata_map.get("description")
            or payload.get("description"),
            "Imported external Agent.",
            field="description",
            limit=500,
        )
        instructions_value = _first_value(
            spec, "instructions", "prompt", "system_prompt", "systemPrompt"
        )
        instructions = _instruction_text(
            instructions_value, source_path, files, warnings
        )
        if not instructions:
            for candidate in (
                "prompts/system.md",
                "prompt.md",
                "instructions.md",
                "system.md",
            ):
                instructions = _instruction_text(
                    {"file": candidate},
                    source_path,
                    files,
                    warnings,
                    missing_is_silent=True,
                )
                if instructions:
                    break
        if instructions:
            capabilities.append(
                _capability(
                    "instructions",
                    "instructions",
                    "supported",
                    "Mapped to the Veyra model system prompt",
                )
            )
        else:
            warnings.append(
                _warning("instructions_missing", "No prompt or instructions were found")
            )
            capabilities.append(
                _capability(
                    "instructions",
                    "instructions",
                    "unsupported",
                    "Add instructions in Studio before running",
                )
            )
            instructions = "Complete the imported request and return a useful result."

        model_value = spec.get("model")
        model = _model_summary(model_value)
        capabilities.append(
            _capability(
                "model",
                "model",
                "partial",
                "Mapped to model.primary; configure the provider API in Settings",
            )
        )
        if isinstance(model_value, Mapping) and any(
            key in model_value for key in ("api_key", "apiKey", "token", "secret")
        ):
            warnings.append(
                _warning(
                    "model_credentials_ignored",
                    "Model credential fields were ignored; use the host Keychain",
                )
            )

        inputs = _field_map(spec.get("inputs", spec.get("input")), "request", warnings)
        outputs = _field_map(
            spec.get("outputs", spec.get("output")), "result", warnings
        )
        capabilities.extend(
            [
                _capability(
                    "inputs", "inputs", "supported", "Mapped to Veyra Agent inputs"
                ),
                _capability(
                    "outputs", "outputs", "supported", "Mapped to Veyra Agent outputs"
                ),
            ]
        )

        tool_resources, tool_names = self._tools(
            spec.get("tools"), inputs, capabilities, warnings
        )
        skill_refs, skill_locks, inline_skills, skill_names = self._skills(
            spec.get("skills"), source_path, files, capabilities, warnings
        )
        if inline_skills:
            instructions = f"{instructions}\n\n" + "\n\n".join(inline_skills)

        knowledge_value = spec.get("knowledge")
        knowledge_files = _knowledge_files(files)
        knowledge_entries = _string_values(knowledge_value)
        if knowledge_entries or knowledge_files:
            capabilities.append(
                _capability(
                    "knowledge",
                    "knowledge",
                    "partial",
                    "References are preserved for review; bind Veyra Knowledge "
                    "explicitly before running",
                )
            )
            warnings.append(
                _warning(
                    "knowledge_requires_binding",
                    "Knowledge files were preserved but not auto-injected into Runtime",
                )
            )

        workflow_value = _first_value(spec, "workflow", "steps", "nodes")
        if workflow_value is not None:
            capabilities.append(
                _capability(
                    "workflow",
                    "workflow",
                    "partial",
                    "The external workflow is preserved for review but not executed",
                )
            )
            warnings.append(
                _warning(
                    "workflow_requires_review",
                    "External workflow steps were not executed during import",
                )
            )

        permissions_value = spec.get("permissions")
        if permissions_value is not None:
            capabilities.append(
                _capability(
                    "permissions",
                    "permissions",
                    "partial",
                    "Raw external permissions are advisory; Veyra permissions "
                    "were recomputed from mapped tools",
                )
            )
            warnings.append(
                _warning(
                    "permissions_recomputed",
                    "External permission declarations do not grant Veyra access",
                )
            )

        known_fields = {
            "name",
            "description",
            "instructions",
            "prompt",
            "system_prompt",
            "systemPrompt",
            "model",
            "inputs",
            "input",
            "outputs",
            "output",
            "tools",
            "skills",
            "knowledge",
            "workflow",
            "steps",
            "nodes",
            "permissions",
            "resources",
            "version",
            "temperature",
        }
        unknown = sorted(set(spec) - known_fields)
        for field in unknown:
            warnings.append(
                _warning(
                    "unsupported_field",
                    f"External field {field} was not mapped",
                    path=str(field),
                )
            )
        if unknown:
            capabilities.append(
                _capability(
                    "extensions",
                    ", ".join(unknown),
                    "partial",
                    "Unknown fields remain in the compatibility report",
                )
            )

        source = _generated_source(
            name=name,
            description=description,
            instructions=instructions,
            inputs=inputs,
            outputs=outputs,
            tools=tool_resources,
            skill_refs=skill_refs,
            skill_locks=skill_locks,
        )
        compatibility = _compatibility(capabilities)
        manifest = self._manifest(
            source_kind=source_kind,
            source_name=source_name,
            source_path=source_path,
            files=files,
            detected_format="generic_yaml",
            compatibility=compatibility,
            capabilities=capabilities,
            warnings=warnings,
            model=model,
            knowledge_files=knowledge_files,
        )
        preview = {
            "name": name,
            "description": description,
            "instructions": instructions,
            "model": model,
            "inputs": inputs,
            "outputs": outputs,
            "tools": tool_names,
            "skills": skill_names,
            "knowledge_files": knowledge_files,
            "workflow_present": workflow_value is not None,
        }
        return self._persist(
            source_kind=source_kind,
            source_name=source_name,
            source_path=source_path,
            detected_format="generic_yaml",
            compatibility=compatibility,
            preview=preview,
            capabilities=capabilities,
            warnings=warnings,
            generated_source=source.to_dict(),
            manifest=manifest,
        )

    def _tools(
        self,
        value: object,
        inputs: Mapping[str, str],
        capabilities: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        resources: list[dict[str, Any]] = []
        names: list[str] = []
        for item in _list_values(value):
            label = _entry_name(item)
            if not label:
                warnings.append(
                    _warning("tool_entry_invalid", "A Tool entry has no name")
                )
                capabilities.append(
                    _capability(
                        "tool",
                        "unknown",
                        "unsupported",
                        "The Tool entry has no usable name",
                    )
                )
                continue
            names.append(label)
            resource_id = _TOOL_ALIASES.get(_tool_key(label))
            if resource_id is None:
                capabilities.append(
                    _capability(
                        "tool",
                        label,
                        "unsupported",
                        "No compatible Veyra Runtime adapter is registered",
                        included=False,
                    )
                )
                warnings.append(
                    _warning(
                        "unsupported_capability",
                        f"Tool {label} has no compatible Veyra adapter",
                    )
                )
                continue
            try:
                resource = self.catalog.detail(resource_id, "1.0.0")
            except (ResourceCatalogError, ValueError):
                capabilities.append(
                    _capability(
                        "tool",
                        label,
                        "unsupported",
                        "The mapped Veyra Tool is not available in this installation",
                        included=False,
                    )
                )
                warnings.append(
                    _warning(
                        "tool_unavailable",
                        f"Mapped Tool {resource_id} is not available",
                    )
                )
                continue
            mapping = _tool_mapping(resource_id, inputs)
            resource_spec = resource.get("spec")
            approval_required = (
                bool(resource_spec.get("approval_required"))
                if isinstance(resource_spec, Mapping)
                else False
            )
            reason = "Mapped to a Veyra Runtime adapter"
            status = "supported"
            included = True
            if mapping is None:
                status = "partial"
                included = False
                reason = (
                    "Recognized, but the imported inputs do not provide a Tool "
                    "input mapping"
                )
                warnings.append(
                    _warning(
                        "tool_input_mapping_required",
                        f"Tool {label} needs an input mapping in Canvas",
                    )
                )
            elif approval_required:
                status = "partial"
                included = False
                reason = (
                    "Recognized, but it requires an explicit approval path before "
                    "execution"
                )
                warnings.append(
                    _warning(
                        "tool_approval_path_required",
                        f"Tool {label} was not auto-wired because it requires approval",
                    )
                )
            capability = _capability(
                "tool",
                label,
                status,
                reason,
                reference=f"{resource_id}@1.0.0",
                included=included,
            )
            capabilities.append(capability)
            if included:
                resources.append({"resource": resource, "mapping": mapping})
        return resources, names

    def _skills(
        self,
        value: object,
        source_path: str,
        files: Mapping[str, bytes],
        capabilities: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> tuple[list[str], dict[str, str], list[str], list[str]]:
        references: list[str] = []
        locks: dict[str, str] = {}
        inline: list[str] = []
        names: list[str] = []
        for item in _list_values(value):
            label = _entry_name(item) or "inline skill"
            names.append(label)
            reference = _entry_reference(item)
            if reference:
                try:
                    resource = self.catalog.by_reference(reference)
                except (ResourceCatalogError, ValueError):
                    capabilities.append(
                        _capability(
                            "skill",
                            label,
                            "unsupported",
                            "The referenced Skill is not available in this Veyra "
                            "installation",
                            reference=reference,
                            included=False,
                        )
                    )
                    warnings.append(
                        _warning(
                            "skill_unavailable",
                            f"Skill {reference} was not found in the Veyra Catalog",
                        )
                    )
                    continue
                if (
                    resource.get("kind") != "skill"
                    or resource.get("availability") != "ready"
                ):
                    capabilities.append(
                        _capability(
                            "skill",
                            label,
                            "unsupported",
                            "The referenced resource is not an enabled Veyra Skill",
                            reference=reference,
                            included=False,
                        )
                    )
                    warnings.append(
                        _warning(
                            "skill_unavailable",
                            f"Skill {reference} is not ready for Runtime use",
                        )
                    )
                    continue
                references.append(reference)
                locks[reference] = str(resource["content_hash"])
                capabilities.append(
                    _capability(
                        "skill",
                        label,
                        "supported",
                        "Locked to the installed Veyra Skill",
                        reference=reference,
                        included=True,
                    )
                )
                continue
            instruction = _entry_instruction(item)
            if instruction:
                inline.append(f"[Imported Skill: {label}]\n{instruction}")
                capabilities.append(
                    _capability(
                        "skill",
                        label,
                        "partial",
                        "Embedded instruction was folded into the model prompt; it "
                        "is not executable code",
                        included=True,
                    )
                )
                warnings.append(
                    _warning(
                        "skill_embedded_in_prompt",
                        f"Skill {label} was embedded into the generated prompt",
                    )
                )
            else:
                capabilities.append(
                    _capability(
                        "skill",
                        label,
                        "unsupported",
                        "No Veyra Skill reference or inline instruction was found",
                        included=False,
                    )
                )
                warnings.append(
                    _warning(
                        "skill_reference_required",
                        f"Skill {label} needs a Veyra reference or instruction",
                    )
                )
        return references, locks, inline, names

    def _manifest(
        self,
        *,
        source_kind: str,
        source_name: str,
        source_path: str,
        files: Mapping[str, bytes],
        detected_format: str,
        compatibility: float,
        capabilities: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
        model: dict[str, Any] | None = None,
        knowledge_files: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": MANIFEST_SCHEMA,
            "source_kind": source_kind,
            "source_name": source_name,
            "source_path": source_path,
            "source_files": sorted(files),
            "knowledge_files": list(knowledge_files or []),
            "detected_format": detected_format,
            "compatibility": compatibility,
            "capabilities": capabilities,
            "warnings": warnings,
            "model": model,
        }

    def _persist(
        self,
        *,
        source_kind: str,
        source_name: str,
        source_path: str,
        detected_format: str,
        compatibility: float,
        preview: dict[str, Any],
        capabilities: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
        generated_source: dict[str, Any],
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        import_id = new_uuid7()
        record = {
            "schema_version": IMPORT_SCHEMA,
            "import_id": import_id,
            "state": "analyzed",
            "source_kind": source_kind,
            "source_name": source_name,
            "source_path": source_path,
            "detected_format": detected_format,
            "compatibility": compatibility,
            "preview": preview,
            "ir": {
                "schema_version": IR_SCHEMA,
                "detected_format": detected_format,
                "source_path": source_path,
                **preview,
            },
            "capabilities": capabilities,
            "warnings": warnings,
            "compatibility_report": {
                "schema_version": COMPATIBILITY_SCHEMA,
                "score": compatibility,
                "capabilities": capabilities,
                "warnings": warnings,
            },
            "generated_source": generated_source,
            "manifest": {**manifest, "import_id": import_id},
        }
        self._write_record(record)
        return record

    def _read_record(self, import_id: str) -> dict[str, Any]:
        try:
            normalized = require_uuid7(import_id, "import_id")
        except ContractValidationError as exc:
            raise AgentImportError(
                "agent_import_not_found", "Agent import was not found"
            ) from exc
        target = self.root / normalized / "record.json"
        try:
            record = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AgentImportError(
                "agent_import_not_found", "Agent import was not found"
            ) from exc
        if not isinstance(record, dict) or record.get("import_id") != normalized:
            raise AgentImportError(
                "agent_import_record_invalid", "Agent import record is invalid"
            )
        return record

    def _write_record(self, record: dict[str, Any]) -> None:
        import_id = record.get("import_id")
        if not isinstance(import_id, str):
            raise AgentImportError(
                "agent_import_record_invalid", "Agent import ID is invalid"
            )
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        target_dir = self.root / import_id
        target_dir.mkdir(mode=0o700, exist_ok=True)
        temporary = target_dir / f".record.{new_uuid7()}.tmp"
        try:
            temporary.write_text(
                json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, target_dir / "record.json")
        finally:
            temporary.unlink(missing_ok=True)


def _archive_files(contents: bytes) -> dict[str, bytes]:
    if not isinstance(contents, bytes) or len(contents) > MAX_ARCHIVE_BYTES:
        raise AgentImportError(
            "agent_import_archive_too_large", "Agent ZIP exceeds the import size limit"
        )
    try:
        archive = zipfile.ZipFile(io.BytesIO(contents))
    except zipfile.BadZipFile as exc:
        raise AgentImportError(
            "agent_import_archive_invalid", "Agent ZIP is not a valid archive"
        ) from exc
    files: dict[str, bytes] = {}
    total = 0
    with archive:
        for info in archive.infolist():
            if info.is_dir() or info.filename.endswith("/"):
                continue
            if info.flag_bits & 0x1 or _is_symlink(info):
                raise AgentImportError(
                    "agent_import_archive_invalid",
                    "Agent ZIP cannot contain encrypted files or links",
                )
            if len(files) >= MAX_FILES:
                raise AgentImportError(
                    "agent_import_archive_too_large",
                    "Agent ZIP contains too many files",
                )
            path = _safe_relative_path(info.filename)
            if info.file_size > MAX_FILE_BYTES:
                raise AgentImportError(
                    "agent_import_file_too_large",
                    "An imported file exceeds the 1 MiB limit",
                )
            try:
                body = archive.read(info)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise AgentImportError(
                    "agent_import_archive_invalid",
                    "An imported ZIP member could not be read",
                ) from exc
            _assert_allowed_input_path(path)
            _assert_body(body)
            total += len(body)
            if total > MAX_TOTAL_BYTES:
                raise AgentImportError(
                    "agent_import_archive_too_large",
                    "Imported files exceed the total size limit",
                )
            files[path] = body
    if not files:
        raise AgentImportError(
            "agent_import_source_missing", "The ZIP does not contain files"
        )
    return files


def _folder_files(path: str) -> tuple[dict[str, bytes], str]:
    if not isinstance(path, str) or not path.strip():
        raise AgentImportError(
            "agent_import_folder_invalid", "An Agent folder path is required"
        )
    selected = Path(path).expanduser()
    if selected.is_symlink() or not selected.is_dir():
        raise AgentImportError(
            "agent_import_folder_invalid", "The selected Agent folder is unavailable"
        )
    try:
        root = selected.resolve(strict=True)
    except OSError as exc:
        raise AgentImportError(
            "agent_import_folder_invalid", "The selected Agent folder is unavailable"
        ) from exc
    files: dict[str, bytes] = {}
    total = 0
    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        for directory in list(directories):
            directory_path = current_path / directory
            if directory_path.is_symlink():
                raise AgentImportError(
                    "agent_import_folder_invalid",
                    "Agent folders cannot contain symbolic links",
                )
            if directory in {
                ".git",
                "node_modules",
                "build",
                "cache",
                "runtime",
                ".venv",
                "venv",
            }:
                directories.remove(directory)
        for filename in filenames:
            file_path = current_path / filename
            if file_path.is_symlink():
                raise AgentImportError(
                    "agent_import_folder_invalid",
                    "Agent folders cannot contain symbolic links",
                )
            try:
                relative = file_path.relative_to(root).as_posix()
                if file_path.stat().st_size > MAX_FILE_BYTES:
                    raise AgentImportError(
                        "agent_import_file_too_large",
                        "An imported file exceeds the 1 MiB limit",
                    )
                body = file_path.read_bytes()
            except OSError as exc:
                raise AgentImportError(
                    "agent_import_folder_invalid",
                    "An Agent folder file could not be read",
                ) from exc
            if len(files) >= MAX_FILES:
                raise AgentImportError(
                    "agent_import_folder_too_large",
                    "Agent folder contains too many files",
                )
            _assert_allowed_input_path(relative)
            _assert_body(body)
            total += len(body)
            if total > MAX_TOTAL_BYTES:
                raise AgentImportError(
                    "agent_import_folder_too_large",
                    "Agent folder files exceed the total size limit",
                )
            files[relative] = body
    if not files:
        raise AgentImportError(
            "agent_import_source_missing", "The selected Agent folder is empty"
        )
    return files, root.name


def _safe_relative_path(raw: str) -> str:
    if (
        not isinstance(raw, str)
        or not raw
        or "\\" in raw
        or "\x00" in raw
        or ":" in raw
    ):
        raise AgentImportError(
            "agent_import_path_invalid", "An imported path is unsafe"
        )
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", "..", "~"} for part in path.parts):
        raise AgentImportError(
            "agent_import_path_invalid", "An imported path escapes its root"
        )
    return path.as_posix()


def _assert_allowed_input_path(path: str) -> None:
    basename = Path(path).name.lower()
    suffix = Path(path).suffix.lower()
    if basename in _FORBIDDEN_NAMES or suffix in _FORBIDDEN_SUFFIXES:
        raise AgentImportError(
            "agent_import_secret_file",
            "Imported Agent sources cannot contain secret files",
        )
    if suffix in _CODE_SUFFIXES:
        # Code may be retained as a reference file, but it is never imported as
        # an executable capability or run by the importer.
        return


def _assert_body(body: bytes) -> None:
    if not isinstance(body, bytes) or len(body) > MAX_FILE_BYTES:
        raise AgentImportError(
            "agent_import_file_too_large", "An imported file exceeds the 1 MiB limit"
        )
    _scan_secret_markers(body)


def _scan_secret_markers(body: bytes) -> None:
    if any(marker in body for marker in _SECRET_MARKERS):
        raise AgentImportError(
            "agent_import_secret_detected",
            "Imported Agent files contain a credential marker",
        )


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == _UNIX_SYMLINK_MODE


def _candidate_key(path: str) -> tuple[int, int, str]:
    name = Path(path).name.lower()
    priority = {
        "agent.vagent.yaml": 0,
        "agent.vagent.yml": 0,
        "agent.yaml": 1,
        "agent.yml": 1,
        "manifest.yaml": 2,
        "manifest.yml": 2,
        "config.yaml": 3,
        "config.yml": 3,
    }.get(name, 10)
    return priority, path.count("/"), path


def _yaml_mapping(body: bytes) -> dict[str, Any]:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AgentImportError(
            "agent_import_yaml_invalid", "Agent YAML must be UTF-8"
        ) from exc
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise AgentImportError(
            "agent_import_yaml_invalid", "Agent YAML could not be parsed"
        ) from exc
    if not isinstance(loaded, dict):
        raise AgentImportError(
            "agent_import_yaml_invalid", "Agent YAML must contain an object"
        )
    return loaded


def _looks_like_veyra_source(payload: Mapping[str, Any]) -> bool:
    return payload.get("agentspec_version") == "26.1" or (
        payload.get("component_type") == "Flow" and "extensions" in payload
    )


def _looks_like_generic_source(payload: Mapping[str, Any]) -> bool:
    keys = {
        "name",
        "description",
        "instructions",
        "prompt",
        "system_prompt",
        "systemPrompt",
        "model",
        "inputs",
        "input",
        "outputs",
        "output",
        "tools",
        "skills",
        "knowledge",
        "workflow",
        "steps",
        "nodes",
        "permissions",
        "resources",
        "spec",
        "metadata",
    }
    return bool(set(payload) & keys)


def _first_value(mapping: Mapping[str, Any], *keys: str) -> object:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _clean_text(value: object, default: str, *, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        return default
    normalized = value.strip()
    if "\x00" in normalized or len(normalized) > limit:
        raise AgentImportError(
            "agent_import_field_invalid", f"Imported {field} is too large or invalid"
        )
    return normalized


def _instruction_text(
    value: object,
    source_path: str,
    files: Mapping[str, bytes],
    warnings: list[dict[str, Any]],
    *,
    missing_is_silent: bool = False,
) -> str:
    if isinstance(value, str):
        return _clean_text(value, "", field="instructions", limit=20_000)
    if isinstance(value, list):
        parts = [
            item.strip() for item in value if isinstance(item, str) and item.strip()
        ]
        return _clean_text("\n\n".join(parts), "", field="instructions", limit=20_000)
    if isinstance(value, Mapping):
        reference = value.get("file") or value.get("path")
        if not isinstance(reference, str) or not reference.strip():
            return ""
        try:
            resolved = _resolve_reference(source_path, reference)
        except AgentImportError:
            warnings.append(
                _warning(
                    "referenced_file_invalid",
                    "Prompt file reference is unsafe",
                    path=reference,
                )
            )
            return ""
        body = files.get(resolved)
        if body is None:
            if not missing_is_silent:
                warnings.append(
                    _warning(
                        "referenced_file_missing",
                        f"Prompt file {reference} was not found",
                        path=reference,
                    )
                )
            return ""
        try:
            return _clean_text(
                body.decode("utf-8"), "", field="instructions", limit=20_000
            )
        except UnicodeDecodeError:
            warnings.append(
                _warning(
                    "referenced_file_not_text",
                    f"Prompt file {reference} is not UTF-8 text",
                    path=reference,
                )
            )
            return ""
    return ""


def _resolve_reference(source_path: str, reference: str) -> str:
    if not reference.strip() or "\\" in reference:
        raise AgentImportError(
            "agent_import_path_invalid", "Referenced file path is unsafe"
        )
    base = PurePosixPath(source_path).parent
    return _safe_relative_path((base / reference).as_posix())


def _field_map(
    value: object,
    fallback: str,
    warnings: list[dict[str, Any]],
) -> dict[str, str]:
    raw_items: list[tuple[object, object]] = []
    if isinstance(value, Mapping):
        raw_items = list(value.items())
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, Mapping):
                raw_items.append(
                    (item.get("name") or item.get("id"), item.get("type", "string"))
                )
            elif isinstance(item, str):
                raw_items.append((item, "string"))
    elif value is not None:
        warnings.append(
            _warning("fields_invalid", "Inputs or outputs were not a map or list")
        )
    result: dict[str, str] = {}
    for raw_name, raw_type in raw_items:
        if not isinstance(raw_name, str) or not raw_name.strip():
            warnings.append(
                _warning("field_invalid", "An input or output has no usable name")
            )
            continue
        name = _field_name(raw_name, len(result))
        field_type = raw_type.strip().lower() if isinstance(raw_type, str) else "string"
        if field_type not in _SUPPORTED_TYPES:
            warnings.append(
                _warning(
                    "field_type_review",
                    f"Field {raw_name} type {field_type} was mapped to string",
                )
            )
            field_type = "string"
        result[name] = field_type
    if not result:
        result[fallback] = "string"
    return result


def _field_name(value: str, index: int) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.strip().lower()).strip("-")
    if not normalized or not normalized[0].isalpha():
        normalized = f"field-{normalized}" if normalized else f"field-{index + 1}"
    normalized = normalized[:63]
    candidate = normalized
    # The caller handles duplicate map keys by replacing the candidate with a
    # deterministic indexed name; this helper keeps only the contract shape.
    if not _FIELD_NAME.fullmatch(candidate):
        candidate = f"field-{index + 1}"
    return candidate


def _list_values(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, Mapping):
        return [
            dict(item, name=str(key))
            if isinstance(item, Mapping)
            else {"name": str(key)}
            for key, item in value.items()
        ]
    return [value]


def _string_values(value: object) -> list[str]:
    result: list[str] = []
    for item in _list_values(value):
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        elif isinstance(item, Mapping):
            candidate = item.get("path") or item.get("file") or item.get("name")
            if isinstance(candidate, str) and candidate.strip():
                result.append(candidate.strip())
    return result


def _entry_name(item: object) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, Mapping):
        for key in ("name", "id", "tool", "uses", "reference", "ref"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _entry_reference(item: object) -> str | None:
    if not isinstance(item, Mapping):
        return (
            item.strip()
            if isinstance(item, str) and item.strip().startswith("veyra.")
            else None
        )
    for key in ("reference", "ref", "uses"):
        value = item.get(key)
        if isinstance(value, str) and value.strip().startswith("veyra."):
            return value.strip()
    return None


def _entry_instruction(item: object) -> str:
    if isinstance(item, Mapping):
        value = item.get("instruction") or item.get("content") or item.get("prompt")
        return value.strip() if isinstance(value, str) and value.strip() else ""
    return ""


def _tool_key(label: str) -> str:
    return label.strip().lower().replace(" ", "-")


def _tool_mapping(resource_id: str, inputs: Mapping[str, str]) -> dict[str, str] | None:
    keys = {key.lower(): key for key in inputs}

    def choose(preferred: tuple[str, ...]) -> str | None:
        for name in preferred:
            if name in keys:
                return keys[name]
        return next(iter(inputs), None)

    if resource_id in {"veyra.tool.filesystem.read", "veyra.tool.filesystem.list"}:
        source = choose(("path", "file", "file-path", "source"))
        return {"path": source} if source else None
    if resource_id == "veyra.tool.filesystem.search":
        query = choose(("query", "search", "topic", "question"))
        return {"query": query} if query else None
    if resource_id == "veyra.tool.github.read":
        source = choose(("path", "repository", "repo"))
        return {"path": source} if source else None
    return None


def _permission_state(
    resources: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    values: dict[str, set[str]] = {
        "network_hosts": set(),
        "tools": set(),
        "filesystem_read_roots": set(),
        "filesystem_write_roots": set(),
    }
    shell_workspace_only = False
    secret_refs: set[str] = set()
    for item in resources:
        resource = item["resource"]
        required = resource.get("required_permissions")
        if isinstance(required, Mapping):
            for key in (
                "network_hosts",
                "tools",
                "filesystem_read_roots",
                "filesystem_write_roots",
            ):
                current = required.get(key)
                if isinstance(current, list):
                    values[key].update(
                        value for value in current if isinstance(value, str)
                    )
            if required.get("shell_workspace_only") is True:
                shell_workspace_only = True
        spec = resource.get("spec")
        if isinstance(spec, Mapping) and isinstance(spec.get("secret_ref"), str):
            secret_refs.add(str(spec["secret_ref"]))
    return (
        {
            "network_hosts": sorted(values["network_hosts"]),
            "tools": sorted(values["tools"]),
            "filesystem_read_roots": sorted(values["filesystem_read_roots"]),
            "filesystem_write_roots": sorted(values["filesystem_write_roots"]),
            "shell_workspace_only": shell_workspace_only,
        },
        sorted(secret_refs),
    )


def _generated_source(
    *,
    name: str,
    description: str,
    instructions: str,
    inputs: Mapping[str, str],
    outputs: Mapping[str, str],
    tools: list[dict[str, Any]],
    skill_refs: list[str],
    skill_locks: Mapping[str, str],
) -> AgentSource:
    permissions, secret_refs = _permission_state(tools)
    nodes: list[dict[str, Any]] = [
        {"id": "start", "component_type": "Start"},
        {
            "id": "model",
            "component_type": "Model",
            "model_ref": "model.primary",
            "system_prompt": instructions,
        },
    ]
    positions: dict[str, dict[str, int]] = {
        "start": {"x": 0, "y": 80},
        "model": {"x": 240, "y": 80},
    }
    for index, item in enumerate(tools):
        node_id = f"tool_{index}"
        node: dict[str, Any] = {
            "id": node_id,
            "component_type": "Tool",
            "uses": item["resource"]["reference"],
        }
        mapping = item.get("mapping")
        if isinstance(mapping, Mapping):
            node["input_mapping"] = dict(mapping)
        nodes.append(node)
        positions[node_id] = {"x": 480 + index * 240, "y": 80}
    output_id = "output"
    output_x = 480 + len(tools) * 240
    nodes.append(
        {
            "id": output_id,
            "component_type": "Output",
            "output_name": next(iter(outputs)),
        }
    )
    positions[output_id] = {"x": output_x, "y": 80}
    chain = ["model", *[node["id"] for node in nodes[2:-1]], output_id]
    transitions: list[dict[str, str]] = [
        {"from": "start", "port": "next", "to": chain[0]}
    ]
    transitions.extend(
        {"from": left, "port": "next", "to": right}
        for left, right in zip(chain, chain[1:], strict=False)
    )
    payload = {
        "schema_version": "1.0",
        "agentspec_version": "26.1",
        "component_type": "Flow",
        "agent_id": new_uuid7(),
        "slug": _field_name(name, 0),
        "name": name,
        "description": description,
        "inputs": dict(inputs),
        "outputs": dict(outputs),
        "nodes": nodes,
        "transitions": transitions,
        "extensions": {
            "veyra": {
                "runtime_profile": "veyra-runtime-profile/1",
                "secret_refs": secret_refs,
                "permissions": permissions,
                "verification": {"required": False, "checks": []},
                "skill_refs": list(skill_refs),
                "policy_refs": [],
            }
        },
        "ui": {"positions": positions},
        "lock": {
            "veyra.runtime.profile@1.0.0": "0" * 64,
            **dict(skill_locks),
            **{
                item["resource"]["reference"]: item["resource"]["content_hash"]
                for item in tools
            },
        },
    }
    return AgentSource.from_dict(payload)


def _model_summary(value: object) -> dict[str, Any]:
    if isinstance(value, str) and value.strip():
        return {"model_id": value.strip()[:128]}
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key in (
            "provider",
            "model",
            "model_id",
            "base_url",
            "api_base",
            "api_base_url",
        ):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                result[key] = item.strip()[:256]
        return result
    return {}


def _knowledge_files(files: Mapping[str, bytes]) -> list[str]:
    result: list[str] = []
    for path in sorted(files):
        parts = PurePosixPath(path).parts
        if "knowledge" in parts and Path(path).suffix.lower() in _TEXT_SUFFIXES:
            result.append(path)
    return result


def _source_preview(
    source: AgentSource, files: Mapping[str, bytes], source_path: str
) -> dict[str, Any]:
    model_nodes = [node for node in source.nodes if node.model_ref is not None]
    instructions = model_nodes[0].system_prompt if model_nodes else ""
    return {
        "name": source.name,
        "description": source.description,
        "instructions": instructions,
        "model": {"model_ref": model_nodes[0].model_ref} if model_nodes else {},
        "inputs": dict(source.inputs),
        "outputs": dict(source.outputs),
        "tools": [node.uses for node in source.nodes if node.uses],
        "skills": list(source.skill_refs),
        "knowledge_files": _knowledge_files(files),
        "workflow_present": False,
        "source_path": source_path,
    }


def _capability(
    kind: str, original: str, status: str, reason: str, **extra: Any
) -> dict[str, Any]:
    return {
        "kind": kind,
        "original": original,
        "status": status,
        "reason": reason,
        **extra,
    }


def _warning(code: str, message: str, *, path: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code, "message": message}
    if path is not None:
        result["path"] = path
    return result


def _compatibility(capabilities: list[dict[str, Any]]) -> float:
    if not capabilities:
        return 0.0
    score = sum(
        1.0
        if capability.get("status") == "supported"
        else 0.5
        if capability.get("status") == "partial"
        else 0.0
        for capability in capabilities
    )
    return round(score / len(capabilities), 2)


def _display_name(source_path: str) -> str:
    stem = Path(source_path).stem
    if stem.lower() == "agent" and Path(source_path).parent.name:
        stem = Path(source_path).parent.name
    return _clean_text(
        stem.replace("-", " ").replace("_", " ").title(),
        "Imported Agent",
        field="name",
        limit=120,
    )


def _folder_display_name(files: Mapping[str, bytes]) -> str:
    first = sorted(files)[0]
    top_level = PurePosixPath(first).parts[0]
    return _clean_text(
        top_level.replace("-", " ").replace("_", " ").title(),
        "Imported Agent",
        field="name",
        limit=120,
    )
