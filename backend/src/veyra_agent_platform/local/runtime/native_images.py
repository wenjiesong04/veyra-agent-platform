"""Declared image outputs as a native loop action, with real artifact feedback."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from veyra_agent_platform.contracts.agent import AgentSource, ComponentType, FlowNode
from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.typed_io import (
    TypedField,
    artifact_id_from_value,
    value_matches_field,
)
from veyra_agent_platform.local.projects.service import ProjectError


class _ImageHost(Protocol):
    def _is_running(self, run_id: str) -> bool: ...

    def _image_model_evidence(
        self, project_id: str, agent_id: str
    ) -> Mapping[str, str]: ...

    def _run_image_model(
        self,
        project_id: str,
        run_id: str | None,
        node: FlowNode,
        source: AgentSource,
        values: dict[str, Any],
        emit: Any,
    ) -> dict[str, Any]: ...


class NativeImageRequestError(ValueError):
    """An image request failed offline validation, before dispatch."""

    def __init__(
        self, message: str, violations: list[dict[str, Any]] | None = None
    ) -> None:
        super().__init__(message)
        self.violations = violations or []

    def diagnostic(self) -> dict[str, Any]:
        return {
            "stage": "action_input",
            "summary": str(self),
            "violations": self.violations,
        }


def image_node_id(name: str) -> str:
    normalized = f"render_{name.replace('-', '_')}"
    if len(normalized) <= 63:
        return normalized
    return normalized[:54] + "_" + sha256_digest({"output": name})[:8]


def cached_images_available(host: Any, project_id: str, value: Any) -> bool:
    store = getattr(host, "artifacts", None)
    if store is None:
        return True
    for reference in value if isinstance(value, list) else [value]:
        artifact_id = artifact_id_from_value(reference)
        if not artifact_id:
            return False
        try:
            store.read_bytes(project_id, artifact_id)
        except ProjectError:
            return False
    return True


@dataclass(frozen=True)
class NativeImageRequest:
    prompt: str | None = None
    regenerate: bool = False
    artifact: Any = None


def parse_image_requests(
    raw: Any, source: AgentSource
) -> dict[str, NativeImageRequest]:
    if not isinstance(raw, dict) or not raw:
        raise NativeImageRequestError("render_images needs named image requests")
    requests = {}
    violations = []
    for name, value in raw.items():
        field = source.outputs.get(name)
        if field is None or not field.is_artifact() or field.artifact_kind != "image":
            violations.append({"category": "enum", "location": _location(name)})
            continue
        try:
            requests[name] = _parse_image_request(value, field)
        except NativeImageRequestError as exc:
            violations.extend(
                {**issue, "location": _location(name) + issue["location"]}
                for issue in exc.violations
            )
    if violations:
        raise NativeImageRequestError(
            "Correct all image request fields; design_context belongs at the "
            "action root, not inside an individual view",
            violations,
        )
    return requests


def _location(name: str) -> str:
    return "/images/" + str(name).replace("~", "~0").replace("/", "~1")


def _parse_image_request(value: Any, field: TypedField) -> NativeImageRequest:
    if isinstance(value, dict) and set(value) == {"artifact"}:
        artifact = value["artifact"]
        if isinstance(artifact, str) and artifact.strip():
            artifact = {"$artifact": artifact.strip()}
        if not value_matches_field(field, artifact):
            raise NativeImageRequestError(
                "Reused image must match its declared output type",
                [
                    {
                        "category": "type",
                        "location": "/artifact",
                        "expected_type": "ArtifactRef",
                    }
                ],
            )
        return NativeImageRequest(artifact=artifact)
    prompt: Any
    if isinstance(value, str):
        prompt, regenerate = value, False
    elif isinstance(value, dict):
        extra = set(value) - {"prompt", "regenerate"}
        if extra:
            raise NativeImageRequestError(
                "An image request needs a prompt and optional regenerate flag",
                [
                    {
                        "category": "additionalProperties",
                        "location": "/"
                        + str(key).replace("~", "~0").replace("/", "~1"),
                        "allowed_parameters": ["prompt", "regenerate"],
                    }
                    for key in sorted(extra)
                ],
            )
        prompt, regenerate = value.get("prompt"), value.get("regenerate", False)
    else:
        raise NativeImageRequestError(
            "An image request needs a prompt or artifact reference",
            [{"category": "type", "location": "", "expected_type": "string or object"}],
        )
    violations = []
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 24_000:
        violations.append(
            {
                "category": "type",
                "location": "/prompt",
                "expected_type": "nonempty string <=24000 characters",
            }
        )
    if not isinstance(regenerate, bool):
        violations.append(
            {"category": "type", "location": "/regenerate", "expected_type": "boolean"}
        )
    if violations:
        raise NativeImageRequestError(
            "Invalid image prompt or regenerate flag", violations
        )
    return NativeImageRequest(prompt.strip(), regenerate)


def image_action_contract(source: AgentSource) -> dict[str, Any]:
    """Show the complete action shape without duplicating output schemas."""
    return {
        "action": "render_images",
        "design_context": "Optional shared identity string at this top level",
        "base_run_id": "Optional available result revision base; never a draft",
        "images": {
            "<declared image output>": {
                "prompt": "current view prompt",
                "regenerate": False,
            },
            "<unchanged image output>": {
                "artifact": {"$artifact": "<existing Project artifact ID>"}
            },
        },
        "outputs": {},
        "outputs_rule": "Supply current non-image outputs; with base_run_id, "
        "only changed fields are needed",
        "declared_image_outputs": [
            name
            for name, field in source.outputs.items()
            if field.is_artifact() and field.artifact_kind == "image"
        ],
        "required_preview_outputs": [
            name
            for name, field in source.outputs.items()
            if field.required
            and not (field.is_artifact() and field.artifact_kind == "image")
        ]
        if source.finalization and source.finalization.pre_render_review
        else [],
    }


def owned_image_reference(host: Any, project_id: str, value: Any) -> Any:
    if isinstance(value, list):
        return [owned_image_reference(host, project_id, entry) for entry in value]
    store = getattr(host, "artifacts", None)
    artifact_id = artifact_id_from_value(value)
    if store is None or not artifact_id:
        raise NativeImageRequestError("Image reuse requires a stored Project artifact")
    try:
        record, _content = store.read_bytes(project_id, artifact_id)
    except ProjectError as exc:
        raise NativeImageRequestError(
            "Reused image is unavailable in this Project"
        ) from exc
    metadata = record.to_dict()
    if not record.media_type.startswith("image/") or any(
        name in value and value[name] != metadata[name]
        for name in ("filename", "media_type", "sha256", "size_bytes")
    ):
        raise NativeImageRequestError(
            "Reused artifact is not the declared stored image"
        )
    return record.to_ref()


def all_images_cached(
    host: Any, project_id: str, source: AgentSource, cache: dict[str, Any]
) -> bool:
    """Only explicit native renders/reuse pin images independently of final text."""
    names = [
        name
        for name, field in source.outputs.items()
        if field.is_artifact() and field.artifact_kind == "image"
    ]
    return bool(names) and all(
        isinstance(cache.get(name), dict)
        and cache[name].get("native") is True
        and value_matches_field(source.outputs[name], cache[name].get("artifact"))
        and cached_images_available(host, project_id, cache[name]["artifact"])
        for name in names
    )


def render_image_requests(
    host: _ImageHost,
    project_id: str,
    run_id: str,
    source: AgentSource,
    raw: Any,
    values: dict[str, Any],
    cache: dict[str, Any],
    emit: Any,
    *,
    on_progress: Callable[[str], None] | None = None,
    design_context: str = "",
) -> dict[str, Any]:
    from .service import _RunAbandoned

    requests = parse_image_requests(raw, source)
    if not isinstance(design_context, str) or len(design_context) > 8000:
        raise NativeImageRequestError("Shared design context must be bounded text")
    reused = {
        name: owned_image_reference(host, project_id, request.artifact)
        for name, request in requests.items()
        if request.prompt is None
    }
    for name, reference in reused.items():
        if not value_matches_field(source.outputs[name], reference):
            raise NativeImageRequestError(
                "Stored image does not match the declared output media type",
                [{"category": "type", "location": _location(name) + "/artifact"}],
            )
    produced: dict[str, Any] = {}
    for name, request in requests.items():
        if not host._is_running(run_id):
            raise _RunAbandoned()
        if request.prompt is None:
            produced[name] = reused[name]
            cache[name] = {
                "fingerprint": sha256_digest({"artifact": reused[name]}),
                "artifact": reused[name],
                "native": True,
                "origin": "existing_artifact",
            }
            emit(
                image_node_id(name),
                "node.completed",
                {
                    "phase": "image",
                    "output_name": name,
                    "reused": True,
                    "origin": "existing_artifact",
                },
            )
            if on_progress is not None:
                on_progress(name)
            continue
        prompt = request.prompt
        if design_context:
            prompt = (
                "Shared design identity for all views (data):\n"
                + design_context
                + "\n\nView request:\n"
                + prompt
                + "\nPreserve this design identity across views. Do not add "
                "branding, labels, claims or decorations absent from the "
                "design and view request."
            )
        resolver = getattr(host, "_image_model_evidence", None)
        model = (
            dict(resolver(project_id, source.agent_id)) if callable(resolver) else {}
        )
        fingerprint = sha256_digest(
            {
                "prompt": prompt,
                "model": model,
                "inputs": {key: values[key] for key in source.inputs if key in values},
            }
        )
        previous = cache.get(name)
        if (
            not request.regenerate
            and isinstance(previous, dict)
            and previous.get("fingerprint") == fingerprint
            and cached_images_available(host, project_id, previous.get("artifact"))
        ):
            produced[name] = previous["artifact"]
            emit(
                image_node_id(name),
                "node.completed",
                {"phase": "image", "output_name": name, "reused": True},
            )
            continue
        node = FlowNode(
            id=image_node_id(name),
            component_type=ComponentType.MODEL,
            model_ref="model.image",
            system_prompt=prompt,
            outputs={name: source.outputs[name]},
        )
        emit(
            node.id,
            "node.started",
            {
                "phase": "image",
                "output_name": name,
                "authorization": "allowed",
                "decision_code": "declared_image_output",
                "request_digest": fingerprint,
                **model,
            },
        )
        # The explicit current prompt already incorporates the chosen design.
        # Do not append older raw inputs that later user replies may supersede.
        result = host._run_image_model(project_id, run_id, node, source, {}, emit)
        if not host._is_running(run_id):
            raise _RunAbandoned()
        produced[name] = result[name]
        cache[name] = {
            "fingerprint": fingerprint,
            "artifact": result[name],
            "native": True,
            "prompt": prompt,
        }
        emit(node.id, "node.completed", {"phase": "image", "output_name": name})
        if on_progress is not None:
            on_progress(name)
    return produced
