"""Sniff artifact bytes. Client MIME is not trusted alone."""

from __future__ import annotations

import re
import unicodedata
from pathlib import PurePosixPath

from veyra_agent_platform.contracts.typed_io import ArtifactKind

MAX_ARTIFACT_UPLOAD_BYTES = 8_000_000
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_FORBIDDEN_SUFFIXES = {
    ".html",
    ".htm",
    ".svg",
    ".js",
    ".mjs",
    ".exe",
    ".bat",
    ".cmd",
    ".sh",
    ".ps1",
    ".php",
    ".key",
    ".pem",
    ".p12",
    ".token",
}
_IMAGE_SUFFIXES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
_PDF_SUFFIXES = {".pdf": "application/pdf"}
_DOCUMENT_SUFFIXES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".rtf": "application/rtf",
}


class ArtifactIntakeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def sanitize_filename(filename: str | None) -> str:
    if not filename:
        raise ArtifactIntakeError("artifact_filename_invalid", "Use a plain filename")
    normalized = unicodedata.normalize("NFKC", filename).replace("\\", "/")
    name = PurePosixPath(normalized).name
    if name in {".", ".."} or name.startswith("."):
        raise ArtifactIntakeError("artifact_filename_invalid", "Use a plain filename")
    if _CONTROL.search(name) or "/" in name or "\\" in name:
        raise ArtifactIntakeError("artifact_filename_invalid", "Use a plain filename")
    if len(name) > 180:
        raise ArtifactIntakeError("artifact_filename_invalid", "Filename is too long")
    suffix = PurePosixPath(name.lower()).suffix
    if suffix in _FORBIDDEN_SUFFIXES:
        raise ArtifactIntakeError(
            "artifact_filename_invalid", "This file type cannot be uploaded"
        )
    return name


def inspect_artifact(
    filename: str, contents: bytes, claimed_type: str | None = None
) -> tuple[str, ArtifactKind]:
    if not contents:
        raise ArtifactIntakeError("artifact_empty", "Artifact upload is empty")
    if len(contents) > MAX_ARTIFACT_UPLOAD_BYTES:
        raise ArtifactIntakeError(
            "artifact_too_large",
            "Artifact upload exceeds 8,000,000 bytes",
        )
    sniffed = _sniff(contents)
    suffix = PurePosixPath(filename.lower()).suffix
    if sniffed is not None:
        media_type, kind = sniffed
        expected = {**_IMAGE_SUFFIXES, **_PDF_SUFFIXES}.get(suffix)
        if expected and expected != media_type:
            raise ArtifactIntakeError(
                "artifact_type_mismatch",
                "File extension does not match the file contents",
            )
        if claimed_type and not _claimed_matches(claimed_type, media_type, kind):
            raise ArtifactIntakeError(
                "artifact_type_mismatch",
                "Declared media type does not match the file contents",
            )
        return media_type, kind
    if suffix in _DOCUMENT_SUFFIXES:
        return _DOCUMENT_SUFFIXES[suffix], "document"
    if suffix in _IMAGE_SUFFIXES or suffix in _PDF_SUFFIXES:
        raise ArtifactIntakeError(
            "artifact_type_mismatch",
            "File extension does not match the file contents",
        )
    return "application/octet-stream", "file"


def _claimed_matches(claimed: str, media_type: str, kind: ArtifactKind) -> bool:
    claimed = claimed.strip().casefold()
    if not claimed:
        return True
    if claimed == media_type:
        return True
    if claimed.endswith("/*"):
        return media_type.startswith(claimed[:-1])
    if claimed in {"image", "pdf", "document", "file"}:
        return claimed == kind
    return False


def _sniff(contents: bytes) -> tuple[str, ArtifactKind] | None:
    if contents.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "image"
    if contents.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "image"
    if contents.startswith(b"GIF87a") or contents.startswith(b"GIF89a"):
        return "image/gif", "image"
    if contents.startswith(b"RIFF") and contents[8:12] == b"WEBP":
        return "image/webp", "image"
    if contents.startswith(b"%PDF"):
        return "application/pdf", "pdf"
    return None
