"""Read native Tool files from safe paths or this Run's selected file inputs."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from veyra_agent_platform.contracts.artifact import ArtifactRecord


class ArtifactReader(Protocol):
    def get(self, project_id: str, artifact_id: str) -> dict[str, Any]: ...

    def read_bytes(
        self, project_id: str, artifact_id: str
    ) -> tuple[ArtifactRecord, bytes]: ...


class FileSourceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class NativeFileSources:
    """Selected Run inputs grant access to their files, never arbitrary artifact IDs."""

    def __init__(
        self,
        *,
        project_id: str,
        project_target: Callable[[str], tuple[Path, str]],
        selected_inputs: Mapping[str, Any],
        artifacts: ArtifactReader | None = None,
        on_project_read: Callable[[Path, os.stat_result, bytes], None] | None = None,
    ) -> None:
        self.project_id = project_id
        self.project_target = project_target
        self.selected_inputs = {
            name: dict(value) if isinstance(value, Mapping) else value
            for name, value in selected_inputs.items()
        }
        self.artifacts = artifacts
        self.on_project_read = on_project_read

    def read(self, source: Mapping[str, Any], max_bytes: int) -> tuple[bytes, str]:
        if (
            isinstance(max_bytes, bool)
            or not isinstance(max_bytes, int)
            or max_bytes < 1
        ):
            raise FileSourceError(
                "native_file_limit_invalid", "File size limit is invalid"
            )
        if not isinstance(source, Mapping) or set(source) not in ({"path"}, {"input"}):
            raise FileSourceError(
                "native_file_source_invalid",
                "Choose exactly one Project path or selected Run file input",
            )
        key = next(iter(source))
        name = source[key]
        if not isinstance(name, str) or not name:
            raise FileSourceError(
                "native_file_source_invalid", "File source is invalid"
            )
        if key == "path":
            return self._read_path(name, max_bytes)
        return self._read_input(name, max_bytes)

    def _read_path(self, path: str, max_bytes: int) -> tuple[bytes, str]:
        try:
            target, label = self.project_target(path)
            if target.is_symlink() or not target.is_file():
                raise FileSourceError(
                    "native_file_source_invalid", "Project file must be a regular file"
                )
            flags = (
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0)
            )
            descriptor = os.open(target, flags)
            with os.fdopen(descriptor, "rb") as stream:
                metadata = os.fstat(stream.fileno())
                if not stat.S_ISREG(metadata.st_mode):
                    raise FileSourceError(
                        "native_file_source_invalid",
                        "Project file must be a regular file",
                    )
                if metadata.st_size > max_bytes:
                    raise FileSourceError(
                        "native_file_too_large", "File exceeds the Tool size limit"
                    )
                payload = stream.read(max_bytes + 1)
        except FileSourceError:
            raise
        except (OSError, ValueError) as exc:
            raise FileSourceError(
                getattr(exc, "code", "native_file_unavailable"),
                "Project file could not be read",
            ) from exc
        if len(payload) > max_bytes:
            raise FileSourceError(
                "native_file_too_large", "File exceeds the Tool size limit"
            )
        if self.on_project_read is not None:
            self.on_project_read(target, metadata, payload)
        return payload, label

    def _read_input(self, name: str, max_bytes: int) -> tuple[bytes, str]:
        if name not in self.selected_inputs:
            raise FileSourceError(
                "native_file_input_unavailable",
                "File is not a selected input of this Run",
            )
        reference = self.selected_inputs[name]
        if (
            not isinstance(reference, Mapping)
            or set(reference) != {"kind", "artifact_id", "media_type", "filename"}
            or reference["kind"] != "artifact"
            or any(
                not isinstance(reference[key], str) or not reference[key]
                for key in ("artifact_id", "media_type", "filename")
            )
        ):
            raise FileSourceError(
                "native_file_input_invalid", "Run input is not a file reference"
            )
        if self.artifacts is None:
            raise FileSourceError(
                "native_file_reader_unavailable",
                "Selected Run file reader is unavailable",
            )
        artifact_id = reference["artifact_id"]
        try:
            metadata = self.artifacts.get(self.project_id, artifact_id)
            size = metadata.get("size_bytes")
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise FileSourceError(
                    "native_file_input_invalid", "File metadata is invalid"
                )
            if size > max_bytes:
                raise FileSourceError(
                    "native_file_too_large", "File exceeds the Tool size limit"
                )
            record, payload = self.artifacts.read_bytes(self.project_id, artifact_id)
        except FileSourceError:
            raise
        except (OSError, ValueError) as exc:
            raise FileSourceError(
                getattr(exc, "code", "native_file_unavailable"),
                "Selected Run file could not be read",
            ) from exc
        if not isinstance(payload, bytes):
            raise FileSourceError(
                "native_file_input_invalid", "Run file bytes are invalid"
            )
        if len(payload) > max_bytes:
            raise FileSourceError(
                "native_file_too_large", "File exceeds the Tool size limit"
            )
        if (
            record.project_id != self.project_id
            or record.artifact_id != artifact_id
            or record.size_bytes != size
            or len(payload) != size
            or record.media_type != reference["media_type"]
        ):
            raise FileSourceError(
                "native_file_input_invalid", "Run file metadata does not match"
            )
        return payload, f"input:{name} ({record.filename})"
