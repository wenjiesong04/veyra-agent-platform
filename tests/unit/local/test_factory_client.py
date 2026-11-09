from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from veyra_agent_platform.local.factory.client import (
    FactoryProviderError,
    HttpKimiTransport,
    completion_timeout,
    visible_json_field,
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


def test_rate_limit_preserves_safe_type_code_and_wait_hint_without_raw_body() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"Retry-After": "60"},
            json={
                "error": {
                    "type": "rate_limit_error",
                    "code": "tokens_per_minute",
                    "message": "private request text sk-secret must not be retained",
                }
            },
        )

    transport = _transport(handler)
    try:
        transport.complete([{"role": "user", "content": "hello"}])
    except FactoryProviderError as exc:
        assert exc.code == "factory_rate_limited"
        assert exc.details == {
            "http_status": "429",
            "provider_error_type": "rate_limit_error",
            "provider_error_code": "tokens_per_minute",
            "retry_after_seconds": "60",
        }
        assert "private request text" not in str(exc.details)
        assert "sk-secret" not in str(exc.details)
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


def test_visible_reply_grows_before_the_json_closes() -> None:
    assert visible_json_field('{"intent":"create","message":"正在', "message") == "正在"
    assert visible_json_field('{"message":"你好\\n世界"}', "message") == "你好\n世界"


def test_streamed_completion_publishes_the_visible_reply() -> None:
    import json

    seen: list[str] = []

    def frame(content: str, finish: str | None = None) -> str:
        choice: dict[str, object] = {"delta": {"content": content}}
        if finish:
            choice["finish_reason"] = finish
        return "data: " + json.dumps({"id": "c1", "choices": [choice]}) + "\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "kimi-k3"}]})
        body = (
            frame('{"message":"')
            + frame("你好，这是一段设计解读")
            + frame('"}', "stop")
            + "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=body)

    transport = _transport(handler)
    completion = transport.complete(
        [{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
        on_visible=seen.append,
    )
    assert completion.content.startswith('{"message":')
    assert seen
    assert seen[-1].startswith("你好")


def test_semantic_plan_read_is_not_cut_off() -> None:
    assert completion_timeout(None).read is None
    assert completion_timeout(90).read == 90


def test_quota_exhaustion_is_not_reported_as_transient_rate_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "error": {
                    "type": "exceeded_current_quota_error",
                    "message": "private account value",
                }
            },
        )

    with pytest.raises(FactoryProviderError) as caught:
        _transport(handler).complete([{"role": "user", "content": "hello"}])
    assert caught.value.code == "factory_quota_exhausted"
    assert (caught.value.details or {})[
        "provider_error_type"
    ] == "exceeded_current_quota_error"
    assert "private account" not in str(caught.value)


def test_purpose_effort_override_preserves_the_default_semantic_effort() -> None:
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
        )

    transport = _transport(handler)
    transport.complete(
        [{"role": "user", "content": "classify"}], reasoning_effort="low"
    )
    transport.complete([{"role": "user", "content": "plan"}])
    assert bodies[0]["reasoning_effort"] == "low"
    assert bodies[1]["reasoning_effort"] == "high"


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
