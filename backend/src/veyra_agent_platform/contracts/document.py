"""Structured document content. Bytes stay in the Artifact Store."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .common import freeze_json, thaw_json


@dataclass(frozen=True)
class DocumentTable:
    sheet: str
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sheet": self.sheet,
            "headers": list(self.headers),
            "rows": [list(row) for row in self.rows],
        }


@dataclass(frozen=True)
class DocumentContent:
    source_artifact_id: str
    filename: str
    media_type: str
    text_blocks: tuple[str, ...]
    tables: tuple[DocumentTable, ...] = ()
    image_artifact_ids: tuple[str, ...] = ()
    metadata: Mapping[str, str] | None = None

    def plaintext(self, *, limit: int = 24_000) -> str:
        parts = list(self.text_blocks)
        for table in self.tables:
            header = "\t".join(table.headers)
            body = "\n".join("\t".join(row) for row in table.rows)
            block = "\n".join(item for item in (table.sheet, header, body) if item)
            if block:
                parts.append(block)
        text = "\n\n".join(part for part in parts if part).strip()
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_artifact_id": self.source_artifact_id,
            "filename": self.filename,
            "media_type": self.media_type,
            "text_blocks": list(self.text_blocks),
            "tables": [item.to_dict() for item in self.tables],
            "image_artifact_ids": list(self.image_artifact_ids),
        }
        if self.metadata:
            payload["metadata"] = thaw_json(self.metadata)
        return payload


def document_content_from_dict(value: Mapping[str, Any]) -> DocumentContent:
    tables = tuple(
        DocumentTable(
            sheet=str(item.get("sheet") or ""),
            headers=tuple(str(cell) for cell in item.get("headers") or ()),
            rows=tuple(
                tuple(str(cell) for cell in row) for row in item.get("rows") or ()
            ),
        )
        for item in value.get("tables") or ()
        if isinstance(item, Mapping)
    )
    metadata = value.get("metadata")
    return DocumentContent(
        source_artifact_id=str(value.get("source_artifact_id") or ""),
        filename=str(value.get("filename") or ""),
        media_type=str(value.get("media_type") or ""),
        text_blocks=tuple(str(item) for item in value.get("text_blocks") or ()),
        tables=tables,
        image_artifact_ids=tuple(
            str(item) for item in value.get("image_artifact_ids") or ()
        ),
        metadata=freeze_json(dict(metadata)) if isinstance(metadata, Mapping) else None,
    )
