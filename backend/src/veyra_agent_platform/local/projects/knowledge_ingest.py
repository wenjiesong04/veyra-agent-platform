"""Bounded UTF-8 Knowledge intake; file registration is not retrieval indexing."""

from __future__ import annotations

import hashlib
import re
from pathlib import PurePath
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from veyra_agent_platform.contracts.common import ContractValidationError, require_uuid7

MAX_KNOWLEDGE_UPLOAD_BYTES = 1_000_000


class KnowledgeIntakeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class KnowledgeCloudFileReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["cloud_file"] = "cloud_file"
    file_id: str

    @field_validator("file_id")
    @classmethod
    def validate_file_id(cls, value: str) -> str:
        try:
            return require_uuid7(value, "file_id")
        except ContractValidationError as error:
            raise ValueError("file_id is invalid") from error


class KnowledgeOrigin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["upload"] = "upload"
    filename: str
    media_type: Literal["text/plain", "text/markdown"]
    uploaded_content_hash: str


def parse_upload(filename: str | None, contents: bytes) -> tuple[str, KnowledgeOrigin]:
    if (
        not filename
        or len(filename) > 255
        or filename.startswith(".")
        or re.search(r"[/\\\x00-\x1f\x7f]", filename)
    ):
        raise KnowledgeIntakeError("knowledge_filename_invalid", "Use a plain filename")
    if re.match(
        r"(?:env|credentials?|secrets?|passwords?|id_(?:rsa|dsa|ecdsa|ed25519))(?:[._-]|$)",
        filename,
        re.IGNORECASE,
    ) or set(PurePath(filename.lower()).suffixes) & {".key", ".pem", ".p12", ".token"}:
        raise KnowledgeIntakeError(
            "knowledge_filename_invalid", "Secret-like files cannot be uploaded"
        )
    suffix = PurePath(filename).suffix.lower()
    if suffix not in {".txt", ".md"}:
        raise KnowledgeIntakeError(
            "knowledge_type_unsupported", "Knowledge upload supports .txt and .md only"
        )
    if len(contents) > MAX_KNOWLEDGE_UPLOAD_BYTES:
        raise KnowledgeIntakeError(
            "knowledge_upload_too_large", "Knowledge upload exceeds 1,000,000 bytes"
        )
    try:
        text = contents.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KnowledgeIntakeError(
            "knowledge_parse_failed", "Knowledge upload must be UTF-8 text"
        ) from exc
    if any(ord(char) < 32 and char not in "\t\n\r" for char in text):
        raise KnowledgeIntakeError(
            "knowledge_parse_failed",
            "Knowledge upload contains binary control characters",
        )
    return text, KnowledgeOrigin(
        filename=filename,
        media_type="text/plain" if suffix == ".txt" else "text/markdown",
        uploaded_content_hash=hashlib.sha256(contents).hexdigest(),
    )
