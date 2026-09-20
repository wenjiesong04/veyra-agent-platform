from __future__ import annotations

from collections.abc import Callable

import httpx

from veyra_agent_platform.local.factory.client import (
    FactoryProviderError,
    HttpKimiTransport,
)
from veyra_agent_platform.local.factory.config import FactorySettings


def test_http_transport_discovers_kimi_k3_and_omits_fixed_sampling() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "kimi-k3"}]})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "ok",
                            "reasoning_content": "secret-thought",
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    transport = HttpKimiTransport(
        FactorySettings(model_base_url="https://api.moonshot.cn/v1"),
        http_client=httpx.Client(
            base_url="https://api.moonshot.cn/v1",
            transport=httpx.MockTransport(handler),
        ),
    )
    assert transport.models() == ("kimi-k3",)
    completion = transport.complete(
        [{"role": "user", "content": "hello"}],
        response_format={"type": "json_schema", "json_schema": {"name": "x"}},
    )
    assert completion.content == "ok"
    assert completion.assistant_message["reasoning_content"] == "secret-thought"
    posted = captured[1]
    body = posted.read()
    assert b"temperature" not in body
    assert b"top_p" not in body
    assert b"kimi-k3" in body
    assert b"reasoning_effort" in body


def test_http_transport_omits_reasoning_effort_for_unknown_host() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )

    transport = HttpKimiTransport(
        FactorySettings(model_base_url="https://llm.example.test/v1"),
        http_client=httpx.Client(
            base_url="https://llm.example.test/v1",
            transport=httpx.MockTransport(handler),
        ),
    )
    transport.complete([{"role": "user", "content": "hello"}])
    body = captured[0].read()
    assert b"reasoning_effort" not in body
    assert b"max_completion_tokens" in body


def test_http_transport_maps_unauthorized_without_leaking_bodies() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    transport = HttpKimiTransport(
        FactorySettings(),
        http_client=httpx.Client(
            base_url="https://api.moonshot.cn/v1",
            transport=httpx.MockTransport(handler),
        ),
    )
    try:
        transport.models()
    except FactoryProviderError as exc:
        assert exc.code == "factory_unauthorized"
        assert "bad key" not in str(exc)
        assert exc.details == {"http_status": "401"}
    else:
        raise AssertionError("expected FactoryProviderError")


def test_http_transport_maps_forbidden_without_leaking_bodies() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "no access sk-secret"}})

    transport = _transport(handler)
    try:
        transport.complete([{"role": "user", "content": "hello"}])
    except FactoryProviderError as exc:
        assert exc.code == "factory_forbidden"
        assert "sk-secret" not in str(exc)
        assert exc.details == {"http_status": "403"}
    else:
        raise AssertionError("expected FactoryProviderError")


def test_http_transport_maps_rate_limit_without_leaking_bodies() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "slow down sk-secret"}})

    transport = _transport(handler)
    try:
        transport.complete([{"role": "user", "content": "hello"}])
    except FactoryProviderError as exc:
        assert exc.code == "factory_rate_limited"
        assert "sk-secret" not in str(exc)
        assert exc.details == {"http_status": "429"}
    else:
        raise AssertionError("expected FactoryProviderError")


def test_http_transport_maps_provider_failure() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "upstream boom"}})

    transport = _transport(handler)
    try:
        transport.complete([{"role": "user", "content": "hello"}])
    except FactoryProviderError as exc:
        assert exc.code == "factory_provider_error"
        assert "upstream boom" not in str(exc)
        assert exc.details == {"http_status": "503"}
    else:
        raise AssertionError("expected FactoryProviderError")


def test_http_transport_maps_invalid_schema_to_typed_diagnostic() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "type": "invalid_request_error",
                    "message": (
                        "Invalid request: response_format.json_schema is not a "
                        "valid moonshot flavored json schema, details: "
                        "<At path '$defs.required_capabilities.properties."
                        "component_types.items': type is not defined> sk-secret"
                    ),
                }
            },
        )

    transport = _transport(handler)
    try:
        transport.complete(
            [{"role": "user", "content": "hello"}],
            response_format={"type": "json_schema", "json_schema": {"name": "x"}},
        )
    except FactoryProviderError as exc:
        assert exc.code == "factory_request_invalid"
        assert "sk-secret" not in str(exc)
        assert "Authorization" not in str(exc)
        assert exc.details is not None
        assert exc.details["http_status"] == "400"
        assert exc.details["provider_error_type"] == "invalid_request_error"
        assert (
            exc.details["rejected_field"]
            == "$defs.required_capabilities.properties.component_types.items"
        )
        assert "sk-secret" not in exc.details["bounded_message"]
        assert "invalid_request_error" in str(exc)
    else:
        raise AssertionError("expected FactoryProviderError")


def _transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> HttpKimiTransport:
    return HttpKimiTransport(
        FactorySettings(),
        http_client=httpx.Client(
            base_url="https://api.moonshot.cn/v1",
            transport=httpx.MockTransport(handler),
        ),
    )
