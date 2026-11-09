"""Native files retain source bytes without importing Run artifacts into Projects."""

from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from veyra_agent_platform.contracts.artifact import ArtifactRecord
from veyra_agent_platform.local.runtime.file_sources import (
    FileSourceError,
    NativeFileSources,
)


class SelectedArtifacts:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.record = ArtifactRecord(
            artifact_id="art_selected",
            project_id="project-1",
            sha256=hashlib.sha256(payload).hexdigest(),
            filename="orders.csv",
            media_type="text/csv",
            size_bytes=len(payload),
            storage_ref="private-object-store",
            source_kind="upload",
            created_at="2026-10-09T00:00:00Z",
        )
        self.calls: list[tuple[str, str, str]] = []

    def get(self, project_id: str, artifact_id: str) -> dict[str, Any]:
        self.calls.append(("metadata", project_id, artifact_id))
        return self.record.to_dict()

    def read_bytes(
        self, project_id: str, artifact_id: str
    ) -> tuple[ArtifactRecord, bytes]:
        self.calls.append(("bytes", project_id, artifact_id))
        return self.record, self.payload


def _reader(
    root: Path,
    artifacts: SelectedArtifacts | None,
    selected_inputs: dict[str, Any] | None = None,
) -> NativeFileSources:
    def target(path: str) -> tuple[Path, str]:
        candidate = root / path
        if Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError("escaped Project")
        return candidate, path

    return NativeFileSources(
        project_id="project-1",
        project_target=target,
        selected_inputs=selected_inputs or {},
        artifacts=artifacts,
    )


def test_project_file_bytes_and_visible_relative_label_are_preserved(
    tmp_path: Path,
) -> None:
    payload = b'\xef\xbb\xbforder,amount\r\n"a,b",0.10\r\n'
    (tmp_path / "orders.csv").write_bytes(payload)
    artifacts = SelectedArtifacts(b"other file")
    reader = _reader(tmp_path, artifacts)

    assert reader.read({"path": "orders.csv"}, len(payload)) == (payload, "orders.csv")
    assert (tmp_path / "orders.csv").read_bytes() == payload
    assert artifacts.calls == []


def test_selected_run_file_uses_project_scoped_artifact_bytes_without_materializing(
    tmp_path: Path,
) -> None:
    payload = b'order,amount,note\nA,0.10,"two\nphysical lines"\n'
    artifacts = SelectedArtifacts(payload)
    reader = _reader(tmp_path, artifacts, {"orders": artifacts.record.to_ref()})

    actual, label = reader.read({"input": "orders"}, len(payload))

    assert actual == payload
    assert label == "input:orders (orders.csv)"
    assert "art_selected" not in label and "private-object-store" not in label
    assert artifacts.calls == [
        ("metadata", "project-1", "art_selected"),
        ("bytes", "project-1", "art_selected"),
    ]
    assert list(tmp_path.iterdir()) == []


def test_path_mode_does_not_require_an_artifact_reader(tmp_path: Path) -> None:
    payload = b"order,amount\nA,1\n"
    (tmp_path / "orders.csv").write_bytes(payload)
    assert _reader(tmp_path, None).read({"path": "orders.csv"}, len(payload)) == (
        payload,
        "orders.csv",
    )


def test_selected_file_without_an_artifact_reader_has_a_clear_failure(
    tmp_path: Path,
) -> None:
    artifacts = SelectedArtifacts(b"order,amount\nA,1\n")
    reader = _reader(tmp_path, None, {"orders": artifacts.record.to_ref()})
    with pytest.raises(FileSourceError) as error:
        reader.read({"input": "orders"}, 100)
    assert error.value.code == "native_file_reader_unavailable"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "source",
    [
        {},
        {"path": "orders.csv", "input": "orders"},
        {"artifact_id": "art_selected"},
        {"input": "orders", "artifact_id": "art_selected"},
        {"path": "orders.csv", "extra": True},
        {"path": None},
        {"input": ""},
        ["orders"],
    ],
)
def test_ambiguous_or_unknown_source_syntax_never_reads_bytes(
    tmp_path: Path, source: Any
) -> None:
    artifacts = SelectedArtifacts(b"order,amount\nA,1\n")
    reader = _reader(tmp_path, artifacts, {"orders": artifacts.record.to_ref()})

    with pytest.raises(FileSourceError) as error:
        reader.read(source, 100)
    assert error.value.code == "native_file_source_invalid"
    assert artifacts.calls == []
    assert list(tmp_path.iterdir()) == []


def test_an_unselected_artifact_cannot_be_addressed_as_a_run_input(
    tmp_path: Path,
) -> None:
    artifacts = SelectedArtifacts(b"private contents")
    reader = _reader(tmp_path, artifacts, {"orders": artifacts.record.to_ref()})

    with pytest.raises(FileSourceError) as error:
        reader.read({"input": "art_selected"}, 100)
    assert error.value.code == "native_file_input_unavailable"
    assert artifacts.calls == []


@pytest.mark.parametrize(
    "value",
    [
        "orders.csv",
        {"artifact_id": "art_selected"},
        {"kind": "collection", "items": []},
        {"$artifact": "art_selected"},
        [{"kind": "artifact", "artifact_id": "art_selected"}],
        {
            "kind": "artifact",
            "artifact_id": "art_selected",
            "media_type": "text/csv",
            "filename": "orders.csv",
            "bytes": "injected",
        },
    ],
)
def test_selected_input_must_be_a_single_validated_file_reference(
    tmp_path: Path, value: Any
) -> None:
    artifacts = SelectedArtifacts(b"order,amount\nA,1\n")
    reader = _reader(tmp_path, artifacts, {"orders": value})

    with pytest.raises(FileSourceError) as error:
        reader.read({"input": "orders"}, 100)
    assert error.value.code == "native_file_input_invalid"
    assert artifacts.calls == []


@pytest.mark.parametrize("limit", [0, -1, True, "100", 1.5])
def test_invalid_size_limits_fail_before_either_reader(
    tmp_path: Path, limit: Any
) -> None:
    artifacts = SelectedArtifacts(b"order,amount\nA,1\n")
    reader = _reader(tmp_path, artifacts, {"orders": artifacts.record.to_ref()})

    with pytest.raises(FileSourceError) as error:
        reader.read({"input": "orders"}, limit)
    assert error.value.code == "native_file_limit_invalid"
    assert artifacts.calls == []


def test_oversized_selected_artifact_is_rejected_before_reading_object_bytes(
    tmp_path: Path,
) -> None:
    artifacts = SelectedArtifacts(b"a" * 11)
    reader = _reader(tmp_path, artifacts, {"orders": artifacts.record.to_ref()})

    with pytest.raises(FileSourceError) as error:
        reader.read({"input": "orders"}, 10)
    assert error.value.code == "native_file_too_large"
    assert artifacts.calls == [("metadata", "project-1", "art_selected")]
    assert list(tmp_path.iterdir()) == []


def test_oversized_project_file_is_rejected_without_changing_it(tmp_path: Path) -> None:
    payload = b"a" * 11
    (tmp_path / "orders.csv").write_bytes(payload)
    reader = _reader(tmp_path, SelectedArtifacts(b"other"))

    with pytest.raises(FileSourceError) as error:
        reader.read({"path": "orders.csv"}, 10)
    assert error.value.code == "native_file_too_large"
    assert (tmp_path / "orders.csv").read_bytes() == payload


@pytest.mark.parametrize("kind", ["directory", "missing", "symlink", "fifo"])
def test_project_source_must_be_a_regular_file(tmp_path: Path, kind: str) -> None:
    target = tmp_path / "source"
    if kind == "directory":
        target.mkdir()
    elif kind == "symlink":
        original = tmp_path / "original.csv"
        original.write_bytes(b"private original")
        target.symlink_to(original)
    elif kind == "fifo":
        os.mkfifo(target)
    reader = _reader(tmp_path, SelectedArtifacts(b"other"))

    with pytest.raises(FileSourceError) as error:
        reader.read({"path": "source"}, 100)
    assert error.value.code == "native_file_source_invalid"


@pytest.mark.parametrize(
    "changed", ["project_id", "artifact_id", "size_bytes", "media_type"]
)
def test_artifact_identity_size_and_type_must_still_match_on_read(
    tmp_path: Path, changed: str
) -> None:
    artifacts = SelectedArtifacts(b"order,amount\nA,1\n")
    reference = artifacts.record.to_ref()
    original_get = artifacts.get
    metadata = artifacts.record.to_dict()
    artifacts.get = lambda project_id, artifact_id: metadata  # type: ignore[method-assign]
    changes: dict[str, Any] = {
        "project_id": "different-project",
        "artifact_id": "different-artifact",
        "size_bytes": len(artifacts.payload) + 1,
        "media_type": "image/png",
    }
    artifacts.record = replace(artifacts.record, **{changed: changes[changed]})
    reader = _reader(tmp_path, artifacts, {"orders": reference})

    with pytest.raises(FileSourceError) as error:
        reader.read({"input": "orders"}, 100)
    assert error.value.code == "native_file_input_invalid"
    assert list(tmp_path.iterdir()) == []
    artifacts.get = original_get  # type: ignore[method-assign]


def test_project_target_failure_is_typed_without_exposing_private_paths(
    tmp_path: Path,
) -> None:
    reader = _reader(tmp_path, SelectedArtifacts(b"other"))
    with pytest.raises(FileSourceError) as error:
        reader.read({"path": "../outside.csv"}, 100)
    assert error.value.code == "native_file_unavailable"
    assert "outside.csv" not in str(error.value)


def test_artifact_storage_failure_remains_a_typed_read_failure(tmp_path: Path) -> None:
    artifacts = SelectedArtifacts(b"order,amount\nA,1\n")

    def corrupted(project_id: str, artifact_id: str) -> tuple[ArtifactRecord, bytes]:
        raise ValueError("private-object-store corrupted hash")

    artifacts.read_bytes = corrupted  # type: ignore[method-assign]
    reader = _reader(tmp_path, artifacts, {"orders": artifacts.record.to_ref()})

    with pytest.raises(FileSourceError) as error:
        reader.read({"input": "orders"}, 100)
    assert error.value.code == "native_file_unavailable"
    assert "private-object-store" not in str(error.value)
    assert list(tmp_path.iterdir()) == []
