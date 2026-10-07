"""Pure request/response shapes for supported synchronous image protocols.

An unknown service begins with the standard Images API. Only missing routes
permit bounded protocol negotiation; a model name never selects a vendor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

ImageProtocol = Literal["openai_images", "images", "image_chat", "dashscope"]
_NATIVE_IMAGE_PATH = "/services/aigc/multimodal-generation/generation"
IMAGE_PROTOCOL_FALLBACKS: dict[ImageProtocol, ImageProtocol] = {
    "openai_images": "images",
    "images": "image_chat",
}


@dataclass(frozen=True)
class ImageRequest:
    path: str
    body: dict[str, Any]
    protocol: ImageProtocol


@dataclass(frozen=True)
class ImageReference:
    value: str
    base64_encoded: bool = False


def image_request(
    base_url: str,
    model_id: str,
    prompt: str,
    *,
    count: int,
    size: str | None,
    protocol: ImageProtocol = "openai_images",
) -> ImageRequest:
    parts = urlsplit(base_url)
    host = (parts.hostname or "").lower()
    native_endpoint = parts.path.rstrip("/").endswith(_NATIVE_IMAGE_PATH)
    native_dashscope = (
        native_endpoint
        or (
            host
            in {
                "dashscope.aliyuncs.com",
                "dashscope-intl.aliyuncs.com",
                "dashscope-us.aliyuncs.com",
            }
            or host.endswith(".maas.aliyuncs.com")
        )
        and parts.path.rstrip("/") == "/api/v1"
    )
    if native_dashscope or protocol == "dashscope":
        parameters: dict[str, Any] = {"n": max(1, count)}
        if size:
            parameters["size"] = size.replace("x", "*")
        return ImageRequest(
            path=base_url if native_endpoint else _NATIVE_IMAGE_PATH,
            body={
                "model": model_id,
                "input": {
                    "messages": [{"role": "user", "content": [{"text": prompt}]}]
                },
                "parameters": parameters,
            },
            protocol="dashscope",
        )
    if protocol == "image_chat":
        return ImageRequest(
            path="/chat/completions",
            body={
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
                "modalities": ["image", "text"],
                "stream": False,
            },
            protocol="image_chat",
        )
    body: dict[str, Any] = {"model": model_id, "prompt": prompt, "n": max(1, count)}
    if size:
        body["size"] = size
    return ImageRequest(
        path="/images" if protocol == "images" else "/images/generations",
        body=body,
        protocol=protocol,
    )


def image_references(payload: Any, protocol: ImageProtocol) -> list[ImageReference]:
    """Extract image references only, never prompts, usage, errors or headers."""
    if not isinstance(payload, dict):
        return []
    if protocol == "dashscope":
        output = payload.get("output")
        choices = output.get("choices") if isinstance(output, dict) else None
        return _choice_images(choices, native=True)
    if protocol == "image_chat":
        return _choice_images(payload.get("choices"), native=False)
    items = payload.get("data") or payload.get("images")
    references: list[ImageReference] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        encoded = item.get("b64_json")
        if isinstance(encoded, str) and encoded:
            references.append(ImageReference(encoded, base64_encoded=True))
        elif isinstance(item.get("url"), str) and item["url"]:
            references.append(ImageReference(item["url"]))
    return references


def _choice_images(choices: Any, *, native: bool) -> list[ImageReference]:
    references: list[ImageReference] = []
    for choice in choices if isinstance(choices, list) else []:
        if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
            continue
        message = choice["message"]
        items = (
            message.get("content")
            if native
            else message.get("images") or message.get("content")
        )
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            image = item.get("image") if native else item.get("image_url")
            url = image.get("url") if isinstance(image, dict) else image
            if isinstance(url, str) and url:
                references.append(ImageReference(url))
    return references
