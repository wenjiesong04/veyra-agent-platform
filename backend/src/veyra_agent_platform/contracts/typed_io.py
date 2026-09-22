"""Canonical Agent/Workflow typed I/O fields.

Legacy compact maps remain valid:

    {"text": "string"}

Rich descriptors are used only when the compact form cannot express the field.
Declared modality is not a runtime capability claim.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, cast

from .common import (
    ContractValidationError,
    freeze_json,
    require_mapping,
    require_string,
    thaw_json,
)

FieldValueType = Literal[
    "string",
    "number",
    "integer",
    "boolean",
    "object",
    "array",
    "table",
    "artifact",
]
ArtifactKind = Literal["image", "pdf", "document", "file", "audio", "video"]
CompactFieldType = Literal[
    "string",
    "number",
    "integer",
    "boolean",
    "object",
    "array",
    "table",
    "image",
    "pdf",
    "document",
    "file",
    "audio",
    "video",
]

SCALAR_TYPES = frozenset({"string", "number", "integer", "boolean"})
JSON_TYPES = frozenset({"object", "array", "table"})
ARTIFACT_KINDS = frozenset({"image", "pdf", "document", "file", "audio", "video"})
COMPACT_TYPES = SCALAR_TYPES | JSON_TYPES | ARTIFACT_KINDS
VALUE_TYPES = SCALAR_TYPES | JSON_TYPES | {"artifact"}
_SLUG = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_MEDIA_TYPE = re.compile(
    r"^(?:application|audio|image|text|video|\*)/"
    r"(?:[a-z0-9][a-z0-9!#$&^_.+-]*|\*)$",
    re.IGNORECASE,
)
_DEFAULT_MEDIA: dict[str, tuple[str, ...]] = {
    "image": ("image/*",),
    "pdf": ("application/pdf",),
    "audio": ("audio/*",),
    "video": ("video/*",),
}
_DESCRIPTOR_FIELDS = {
    "type",
    "artifact_kind",
    "required",
    "multiple",
    "description",
    "accepted_media_types",
    "json_schema",
}
_ARTIFACT_REF_FORBIDDEN = frozenset(
    {
        "bytes",
        "data",
        "content",
        "base64",
        "body",
        "file",
        "path",
        "absolute_path",
        "host_path",
        "file_path",
    }
)


@dataclass(frozen=True)
class TypedField:
    """One named input or output. Wire form may still be a compact type string."""

    type: FieldValueType
    required: bool = True
    multiple: bool = False
    description: str = ""
    artifact_kind: ArtifactKind | None = None
    accepted_media_types: tuple[str, ...] = ()
    json_schema: Mapping[str, Any] | None = None

    @property
    def compact_type(self) -> CompactFieldType:
        if self.type == "artifact":
            if self.artifact_kind is None:
                raise ContractValidationError("artifact fields need artifact_kind")
            return self.artifact_kind
        return cast(CompactFieldType, self.type)

    def is_artifact(self) -> bool:
        return self.type == "artifact"

    def accepts_media(self, media_type: str) -> bool:
        if not self.accepted_media_types:
            return True
        return _media_matches(media_type.casefold(), self.accepted_media_types)

    def is_json(self) -> bool:
        return self.type in JSON_TYPES

    def is_scalar(self) -> bool:
        return self.type in SCALAR_TYPES

    def to_wire(self) -> str | dict[str, Any]:
        if self._compact_wire():
            return self.compact_type
        payload: dict[str, Any] = {"type": self.type}
        if self.type == "artifact":
            payload["artifact_kind"] = self.artifact_kind
        if not self.required:
            payload["required"] = False
        if self.multiple:
            payload["multiple"] = True
        if self.description:
            payload["description"] = self.description
        defaults = _DEFAULT_MEDIA.get(self.compact_type, ())
        if self.accepted_media_types and self.accepted_media_types != defaults:
            payload["accepted_media_types"] = list(self.accepted_media_types)
        if self.json_schema:
            payload["json_schema"] = thaw_json(self.json_schema)
        return payload

    def _compact_wire(self) -> bool:
        defaults = _DEFAULT_MEDIA.get(self.compact_type, ())
        return (
            self.required
            and not self.multiple
            and not self.description
            and self.json_schema is None
            and self.accepted_media_types in {(), defaults}
        )


def parse_typed_fields(value: Any, field: str) -> Mapping[str, TypedField]:
    item = require_mapping(value, field)
    if not item:
        raise ContractValidationError(f"{field} must be a non-empty map")
    parsed: dict[str, TypedField] = {}
    for name, spec in item.items():
        if not isinstance(name, str) or not _SLUG.fullmatch(name):
            raise ContractValidationError(
                f"{field} keys must be slug names such as product-image"
            )
        parsed[name] = parse_typed_field(spec, f"{field}.{name}")
    return MappingProxyType(parsed)


def parse_typed_field(value: Any, field: str) -> TypedField:
    if isinstance(value, str):
        return _from_compact(value, field)
    record = require_mapping(value, field)
    unknown = set(record) - _DESCRIPTOR_FIELDS
    if unknown:
        raise ContractValidationError(
            f"{field} unknown field(s): {', '.join(sorted(unknown))}"
        )
    if "type" not in record:
        raise ContractValidationError(f"{field} missing field(s): type")
    raw_type = require_string(record["type"], f"{field}.type")
    kind = _artifact_kind_of(record.get("artifact_kind"), f"{field}.artifact_kind")
    value_type, artifact_kind = _split_type(raw_type, kind, field)
    required = _optional_bool(record.get("required"), f"{field}.required", default=True)
    multiple = _optional_bool(
        record.get("multiple"), f"{field}.multiple", default=False
    )
    description = ""
    if "description" in record:
        description = require_string(record["description"], f"{field}.description")
        if len(description) > 240:
            raise ContractValidationError(f"{field}.description exceeds 240 characters")
    media = _media_types(record.get("accepted_media_types"), field, artifact_kind)
    schema = _json_schema(record.get("json_schema"), field, value_type)
    return TypedField(
        type=value_type,
        required=required,
        multiple=multiple,
        description=description,
        artifact_kind=artifact_kind,
        accepted_media_types=media,
        json_schema=schema,
    )


def typed_fields_to_wire(fields: Mapping[str, TypedField]) -> dict[str, Any]:
    return {name: item.to_wire() for name, item in fields.items()}


def field_type_name(field: TypedField | str) -> str:
    if isinstance(field, str):
        return field
    return field.compact_type


def compact_type_map(fields: Mapping[str, TypedField]) -> dict[str, str]:
    return {name: field.compact_type for name, field in fields.items()}


def wire_field_compact_type(value: Any) -> str | None:
    """Read a compact type name from wire JSON, a TypedField, or a type string."""

    if isinstance(value, TypedField):
        return value.compact_type
    if isinstance(value, str):
        return value if value in COMPACT_TYPES else None
    if isinstance(value, Mapping):
        raw = value.get("type")
        if not isinstance(raw, str):
            return None
        if raw == "artifact":
            kind = value.get("artifact_kind")
            return kind if kind in ARTIFACT_KINDS else None
        if raw in ARTIFACT_KINDS or raw in VALUE_TYPES - {"artifact"}:
            return raw if raw != "artifact" else None
        return None
    return None


def artifact_id_from_value(value: Any) -> str | None:
    """Read an artifact id from a full ArtifactRef or the compact `$artifact` form."""

    if not isinstance(value, Mapping):
        return None
    if "$artifact" in value:
        if set(value) != {"$artifact"}:
            return None
        shorthand = value.get("$artifact")
        if not isinstance(shorthand, str):
            return None
        ident = shorthand.strip()
        return ident or None
    raw_id = value.get("artifact_id")
    if not isinstance(raw_id, str):
        return None
    ident = raw_id.strip()
    return ident or None


def looks_like_artifact_ref(value: Any) -> bool:
    """True when a value is an ArtifactRef-shaped mapping, never inline bytes."""

    if not isinstance(value, Mapping):
        return False
    if set(value) == {"$artifact"}:
        return artifact_id_from_value(value) is not None
    if value.get("kind") != "artifact":
        return False
    if _ARTIFACT_REF_FORBIDDEN.intersection(value):
        return False
    artifact_id = value.get("artifact_id")
    media_type = value.get("media_type")
    filename = value.get("filename")
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        return False
    if not isinstance(filename, str) or not filename.strip():
        return False
    if not isinstance(media_type, str) or not _MEDIA_TYPE.fullmatch(media_type):
        return False
    for key, item in value.items():
        if key == "size_bytes":
            if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                return False
            continue
        if item is not None and not isinstance(item, str | int | bool):
            return False
    return True


def value_matches_field(field: TypedField, value: Any) -> bool:
    """Type-level Runtime check. Store isolation is enforced later."""

    if field.multiple:
        if not isinstance(value, list):
            return False
        if field.required and not value:
            return False
        inner = TypedField(
            type=field.type,
            required=True,
            multiple=False,
            description=field.description,
            artifact_kind=field.artifact_kind,
            accepted_media_types=field.accepted_media_types,
            json_schema=field.json_schema,
        )
        return all(value_matches_field(inner, item) for item in value)
    if field.is_artifact():
        if not looks_like_artifact_ref(value):
            return False
        if set(value) == {"$artifact"}:
            return True
        media = str(value.get("media_type", "")).casefold()
        return field.accepts_media(media)
    if field.type == "string":
        return isinstance(value, str)
    if field.type == "boolean":
        return isinstance(value, bool)
    if field.type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if field.type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if field.type == "object":
        return isinstance(value, dict)
    if field.type in {"array", "table"}:
        return isinstance(value, list)
    return False


def _from_compact(value: str, field: str) -> TypedField:
    if value not in COMPACT_TYPES:
        raise ContractValidationError(f"{field} type is not supported")
    if value in ARTIFACT_KINDS:
        kind = cast(ArtifactKind, value)
        return TypedField(
            type="artifact",
            artifact_kind=kind,
            accepted_media_types=_DEFAULT_MEDIA.get(kind, ()),
        )
    return TypedField(type=cast(FieldValueType, value))


def _split_type(
    raw_type: str, artifact_kind: ArtifactKind | None, field: str
) -> tuple[FieldValueType, ArtifactKind | None]:
    if raw_type == "artifact":
        if artifact_kind is None:
            raise ContractValidationError(f"{field} artifact fields need artifact_kind")
        return "artifact", artifact_kind
    if raw_type in ARTIFACT_KINDS:
        kind = cast(ArtifactKind, raw_type)
        if artifact_kind is not None and artifact_kind != kind:
            raise ContractValidationError(f"{field} artifact_kind does not match type")
        return "artifact", kind
    if raw_type in VALUE_TYPES - {"artifact"}:
        if artifact_kind is not None:
            raise ContractValidationError(f"{field} artifact_kind is not allowed")
        return cast(FieldValueType, raw_type), None
    raise ContractValidationError(f"{field} type is not supported")


def _artifact_kind_of(value: Any, field: str) -> ArtifactKind | None:
    if value is None:
        return None
    kind = require_string(value, field)
    if kind not in ARTIFACT_KINDS:
        raise ContractValidationError(f"{field} is not a supported artifact kind")
    return cast(ArtifactKind, kind)


def _optional_bool(value: Any, field: str, *, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ContractValidationError(f"{field} must be a boolean")
    return value


def _media_matches(media: str, accepted: tuple[str, ...]) -> bool:
    for pattern in accepted:
        if pattern == "*/*":
            return True
        if pattern.endswith("/*") and media.startswith(pattern[:-1]):
            return True
        if media == pattern:
            return True
    return False


def _media_types(
    value: Any, field: str, artifact_kind: ArtifactKind | None
) -> tuple[str, ...]:
    if value is None:
        return _DEFAULT_MEDIA.get(artifact_kind or "", ())
    if artifact_kind is None:
        raise ContractValidationError(
            f"{field}.accepted_media_types is only valid for artifacts"
        )
    if not isinstance(value, list) or not value:
        raise ContractValidationError(f"{field}.accepted_media_types must be a list")
    if len(value) > 8:
        raise ContractValidationError(f"{field}.accepted_media_types exceeds 8 items")
    parsed: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        media = require_string(
            item, f"{field}.accepted_media_types[{index}]"
        ).casefold()
        if not _MEDIA_TYPE.fullmatch(media):
            raise ContractValidationError(
                f"{field}.accepted_media_types[{index}] is not a media type"
            )
        if media in seen:
            raise ContractValidationError(
                f"{field}.accepted_media_types values must be unique"
            )
        seen.add(media)
        parsed.append(media)
    return tuple(parsed)


def _json_schema(
    value: Any, field: str, value_type: FieldValueType
) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if value_type not in JSON_TYPES:
        raise ContractValidationError(
            f"{field}.json_schema is only valid for JSON types"
        )
    schema = require_mapping(value, f"{field}.json_schema")
    return cast(Mapping[str, Any], freeze_json(dict(schema)))
