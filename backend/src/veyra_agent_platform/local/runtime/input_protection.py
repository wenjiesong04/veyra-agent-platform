"""Protect native Project inputs using append-only, Run-owned evidence."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from veyra_agent_platform.local.storage.repositories import LocalRepository

from .workflow_store import WorkflowRunStore


class InputProtectionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class InputProtectionScope:
    project_id: str
    owner_kind: Literal["agent", "workflow"]
    owner_run_id: str

    def to_dict(self) -> dict[str, str]:
        return {"scope_kind": self.owner_kind, "scope_run_id": self.owner_run_id}


def _run_tables(kind: str) -> tuple[str, str]:
    if kind == "agent":
        return "runtime_runs", "runtime_run_events"
    if kind == "workflow":
        return "workflow_runs", "workflow_run_events"
    raise InputProtectionError(
        "input_protection_scope_invalid", "Input protection Run kind is unsupported"
    )


def _relative_path(project_root: Path, path: Path) -> str:
    try:
        root = project_root.resolve(strict=True)
        candidate = path if path.is_absolute() else root / path
        relative = candidate.resolve().relative_to(root).as_posix()
        if relative == "." or not root.is_dir():
            raise ValueError("not a Project file")
        return relative
    except (OSError, ValueError, RuntimeError) as exc:
        raise InputProtectionError(
            "input_protection_path_invalid", "Input protection requires a Project file"
        ) from exc


def _payload(value: str) -> dict[str, Any]:
    try:
        result = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise InputProtectionError(
            "input_protection_record_invalid", "Input protection evidence is invalid"
        ) from exc
    if not isinstance(result, dict):
        raise InputProtectionError(
            "input_protection_record_invalid", "Input protection evidence is invalid"
        )
    return result


class InputProtectionStore:
    def __init__(self, repository: LocalRepository) -> None:
        self.repository = repository
        self.workflow_runs = WorkflowRunStore(repository)

    def scope_for_run(
        self, project_id: str, run_kind: str, run_id: str
    ) -> InputProtectionScope | None:
        _, event_table = _run_tables(run_kind)
        try:
            with closing(self.repository._connect()) as connection:
                self._require_run(connection, project_id, run_kind, run_id)
                row = connection.execute(
                    f"SELECT payload_json FROM {event_table} WHERE run_id = ? "
                    "AND kind = 'run.created' ORDER BY sequence LIMIT 1",
                    (run_id,),
                ).fetchone()
                if row is None:
                    return None
                protection = _payload(row["payload_json"]).get("input_protection")
                if protection is None:
                    return None
                if (
                    not isinstance(protection, dict)
                    or set(protection) != {"scope_kind", "scope_run_id"}
                    or protection["scope_kind"] not in ("agent", "workflow")
                    or not isinstance(protection["scope_run_id"], str)
                    or not protection["scope_run_id"]
                ):
                    raise InputProtectionError(
                        "input_protection_scope_invalid",
                        "Input protection scope is invalid",
                    )
                scope = InputProtectionScope(
                    project_id, protection["scope_kind"], protection["scope_run_id"]
                )
                self._validate_scope(connection, scope)
                return scope
        except sqlite3.Error as exc:
            raise self._unavailable() from exc

    def validate_scope(self, scope: InputProtectionScope | None) -> None:
        if scope is None:
            return
        try:
            with closing(self.repository._connect()) as connection:
                self._validate_scope(connection, scope)
        except sqlite3.Error as exc:
            raise self._unavailable() from exc

    def protect_project_file(
        self,
        scope: InputProtectionScope | None,
        project_root: Path,
        path: Path,
        stat: os.stat_result,
        contents: bytes,
    ) -> None:
        if scope is None:
            return
        evidence: dict[str, Any] = {
            "relative_path": _relative_path(project_root, path),
            "st_dev": stat.st_dev,
            "st_ino": stat.st_ino,
            "sha256": hashlib.sha256(contents).hexdigest(),
            "byte_count": len(contents),
        }
        try:
            # Deduplication and append share the repository's BEGIN IMMEDIATE lock.
            with self.repository.transaction() as connection:
                self._validate_scope(connection, scope)
                protected = self._file_records(connection, scope, "input.protected")
                if evidence in protected:
                    return
                output_identity = {
                    key: evidence[key] for key in ("relative_path", "st_dev", "st_ino")
                }
                if not any(
                    self._matches(item, evidence["relative_path"], stat)
                    for item in protected
                ) and output_identity in self._file_records(
                    connection, scope, "input.output_created"
                ):
                    return
                self._event(connection, scope, "input.protected", evidence)
        except sqlite3.Error as exc:
            raise self._unavailable() from exc

    def record_output_file(
        self,
        scope: InputProtectionScope | None,
        project_root: Path,
        path: Path,
        stat: os.stat_result,
    ) -> None:
        if scope is None:
            return
        evidence: dict[str, Any] = {
            "relative_path": _relative_path(project_root, path),
            "st_dev": stat.st_dev,
            "st_ino": stat.st_ino,
        }
        try:
            with self.repository.transaction() as connection:
                self._validate_scope(connection, scope)
                if evidence not in self._file_records(
                    connection, scope, "input.output_created"
                ):
                    self._event(connection, scope, "input.output_created", evidence)
        except sqlite3.Error as exc:
            raise self._unavailable() from exc

    def assert_writable(
        self,
        scope: InputProtectionScope | None,
        project_root: Path,
        path: Path,
        stat: os.stat_result | None = None,
    ) -> None:
        if scope is None:
            return
        relative = _relative_path(project_root, path)
        if stat is None:
            try:
                target = path if path.is_absolute() else project_root / path
                stat = target.stat()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise self._unavailable() from exc
        try:
            with closing(self.repository._connect()) as connection:
                self._validate_scope(connection, scope)
                for evidence in self._file_records(
                    connection, scope, "input.protected"
                ):
                    if self._matches(evidence, relative, stat):
                        raise InputProtectionError(
                            "input_file_protected",
                            "This file is a protected input; choose another output",
                        )
        except sqlite3.Error as exc:
            raise self._unavailable() from exc

    def _validate_scope(
        self, connection: sqlite3.Connection, scope: InputProtectionScope
    ) -> None:
        self._require_run(
            connection, scope.project_id, scope.owner_kind, scope.owner_run_id
        )

    def _require_run(
        self,
        connection: sqlite3.Connection,
        project_id: str,
        run_kind: str,
        run_id: str,
    ) -> None:
        run_table, _ = _run_tables(run_kind)
        row = connection.execute(
            f"SELECT project_id FROM {run_table} WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None or row["project_id"] != project_id:
            raise InputProtectionError(
                "input_protection_scope_unavailable",
                "Input protection owner is unavailable in this Project",
            )

    def _file_records(
        self,
        connection: sqlite3.Connection,
        scope: InputProtectionScope,
        kind: Literal["input.protected", "input.output_created"],
    ) -> list[dict[str, Any]]:
        _, event_table = _run_tables(scope.owner_kind)
        fields = {"relative_path", "st_dev", "st_ino"}
        number_fields = ["st_dev", "st_ino"]
        if kind == "input.protected":
            fields.update(("sha256", "byte_count"))
            number_fields.append("byte_count")
        records = []
        for row in connection.execute(
            f"SELECT payload_json FROM {event_table} WHERE run_id = ? "
            "AND kind = ? ORDER BY sequence",
            (scope.owner_run_id, kind),
        ):
            evidence = _payload(row["payload_json"])
            relative = evidence.get("relative_path")
            digest = evidence.get("sha256")
            if (
                set(evidence) != fields
                or not isinstance(relative, str)
                or not relative
                or PurePosixPath(relative).is_absolute()
                or PurePosixPath(relative).as_posix() != relative
                or relative == "."
                or ".." in PurePosixPath(relative).parts
                or any(
                    type(evidence.get(key)) is not int or evidence[key] < 0
                    for key in number_fields
                )
                or (
                    kind == "input.protected"
                    and (
                        not isinstance(digest, str)
                        or len(digest) != 64
                        or any(
                            character not in "0123456789abcdef" for character in digest
                        )
                    )
                )
            ):
                raise InputProtectionError(
                    "input_protection_record_invalid",
                    "Input protection evidence is invalid",
                )
            records.append(evidence)
        return records

    def _event(
        self,
        connection: sqlite3.Connection,
        scope: InputProtectionScope,
        kind: str,
        evidence: dict[str, Any],
    ) -> None:
        if scope.owner_kind == "agent":
            self.repository.add_run_events(
                connection, scope.owner_run_id, [(None, kind, evidence)]
            )
        else:
            self.workflow_runs.event(
                connection, scope.owner_run_id, None, kind, evidence
            )

    @staticmethod
    def _matches(
        evidence: dict[str, Any], relative: str, stat: os.stat_result | None
    ) -> bool:
        return evidence["relative_path"] == relative or (
            stat is not None
            and evidence["st_dev"] == stat.st_dev
            and evidence["st_ino"] == stat.st_ino
        )

    @staticmethod
    def _unavailable() -> InputProtectionError:
        return InputProtectionError(
            "input_protection_unavailable",
            "Input file protection could not be verified",
        )
