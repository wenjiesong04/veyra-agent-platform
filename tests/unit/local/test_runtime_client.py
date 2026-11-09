from __future__ import annotations

import json
from base64 import b64encode
from types import SimpleNamespace

import httpx
import pytest

from veyra_agent_platform.local.runtime.client import (
    HttpRuntimeTransport,
    RuntimeCompletion,
    RuntimeModelClient,
    RuntimeProviderError,
    RuntimeSettings,
)
from veyra_agent_platform.local.runtime.credentials import (
    ProviderCredentialError,
    provider_base_url,
)

PNG = b"\x89PNG\r\n\x1a\nsynthetic-image-content"
ENCODED_PNG = b64encode(PNG).decode("ascii")
DATA_PNG = f"data:image/png;base64,{ENCODED_PNG}"


def _image_transport(base_url: str, handler, **settings) -> HttpRuntimeTransport:
    return HttpRuntimeTransport(
        RuntimeSettings(
            model_base_url=base_url, model_id="synthetic-model", **settings
        ),
        http_client=httpx.Client(
            base_url=base_url, transport=httpx.MockTransport(handler)
        ),
    )


def test_http_transport_omits_fixed_sampling() -> None:
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
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    transport = HttpRuntimeTransport(
        RuntimeSettings(model_base_url="https://api.moonshot.cn/v1"),
        http_client=httpx.Client(
            base_url="https://api.moonshot.cn/v1",
            transport=httpx.MockTransport(handler),
        ),
    )
    assert transport.models() == ("kimi-k3",)
    completion = transport.complete([{"role": "user", "content": "hello"}])
    assert completion.content == "ok"
    body = captured[1].read()
    assert b"temperature" not in body
    assert b"top_p" not in body
    assert b"kimi-k3" in body
    assert b"reasoning_effort" in body


@pytest.mark.parametrize(
    "content",
    [
        "",
        '{"kind":"tool","tool":"unfinished',
        '{"kind":"final","outputs":{"result":"truncated"}}',
    ],
)
def test_truncated_completion_is_not_an_executable_action(content: str) -> None:
    transport = _image_transport(
        "https://example.com/v1",
        lambda request: httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": content,
                            "reasoning_content": "private",
                        },
                        "finish_reason": "length",
                    }
                ],
            },
        ),
    )
    with pytest.raises(RuntimeProviderError) as caught:
        transport.complete([{"role": "user", "content": "A multi-step task"}])
    assert caught.value.code == "runtime_output_truncated"
    assert "private" not in str(caught.value)
    assert caught.value.diagnostic["finish_reason"] == "length"


def test_empty_completion_records_only_safe_response_shape() -> None:
    transport = _image_transport(
        "https://example.com/v1",
        lambda request: httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "reasoning_content": "private thinking",
                            "refusal": "private refusal",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"completion_tokens": 8192, "prompt_tokens": 3000},
                "secret": "never record raw bodies",
            },
        ),
    )
    with pytest.raises(RuntimeProviderError) as caught:
        transport.complete([{"role": "user", "content": "Synthetic request"}])
    assert caught.value.diagnostic == {
        "finish_reason": "stop",
        "content_type": "missing",
        "content_empty": True,
        "has_tool_calls": False,
        "has_refusal": True,
        "completion_tokens": 8192,
        "prompt_tokens": 3000,
    }
    assert "private" not in json.dumps(caught.value.diagnostic)


def test_malformed_completion_still_returns_a_safe_provider_failure() -> None:
    transport = _image_transport(
        "https://example.com/v1",
        lambda request: httpx.Response(200, text="private non-JSON Provider body"),
    )
    with pytest.raises(RuntimeProviderError) as caught:
        transport.complete([{"role": "user", "content": "Synthetic request"}])
    assert caught.value.code == "runtime_invalid_response"
    assert caught.value.diagnostic["content_type"] == "missing"
    assert "private" not in str(caught.value)


def test_review_uses_separate_read_timeout_on_the_same_transport() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "synthetic-model"}]})
        requests.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok":true}'}}]},
        )

    transport = _image_transport(
        "https://api.moonshot.cn/v1",
        handler,
        timeout_seconds=11,
        review_timeout_seconds=27,
    )
    client = RuntimeModelClient(transport.settings, transport=transport)
    messages = [{"role": "user", "content": "Synthetic structured assessment"}]
    client.complete_action(messages)
    client.complete_review(messages)
    client.complete_action(messages)
    assert [request.extensions["timeout"]["read"] for request in requests] == [
        11,
        27,
        11,
    ]
    assert all(request.extensions["timeout"]["connect"] == 11 for request in requests)
    bodies = [json.loads(request.content) for request in requests]
    assert all(body.pop("stream") is True for body in bodies)
    assert bodies[0] == bodies[1] == bodies[2]
    assert json.loads(requests[1].content)["response_format"] == {"type": "json_object"}


def test_review_timeout_is_safe_and_does_not_retry() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "synthetic-model"}]})
        calls.append(request)
        raise httpx.ReadTimeout("private credential and request body", request=request)

    transport = _image_transport("https://api.moonshot.cn/v1", handler)
    client = RuntimeModelClient(transport.settings, transport=transport)
    with pytest.raises(RuntimeProviderError) as caught:
        client.complete_review([{"role": "user", "content": "Synthetic"}])
    assert caught.value.code == "runtime_timeout"
    assert caught.value.diagnostic == {
        "timeout_phase": "read",
        "timeout_seconds": 180.0,
        "event_count": 0,
        "content_bytes": 0,
    }
    assert "private" not in str(caught.value)
    assert len(calls) == 1


def test_http_transport_sends_json_object_response_format() -> None:
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
                        "message": {"role": "assistant", "content": "{}"},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    transport = HttpRuntimeTransport(
        RuntimeSettings(model_base_url="https://api.moonshot.cn/v1"),
        http_client=httpx.Client(
            base_url="https://api.moonshot.cn/v1",
            transport=httpx.MockTransport(handler),
        ),
    )
    transport.complete(
        [{"role": "user", "content": "hello"}],
        response_format={"type": "json_object"},
    )
    assert captured
    body = json.loads(captured[-1].read())
    assert body["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize(
    "base_url,provider_type,expected",
    [
        ("https://api.moonshot.cn/v1", "moonshot", {"type": "json_object"}),
        ("https://api.openai.com/v1", "openai", {"type": "json_object"}),
        ("https://custom.example/v1", "openai_compatible", None),
    ],
)
def test_action_completion_uses_known_json_protocol_without_forcing_unknown_endpoints(
    base_url, provider_type, expected
) -> None:
    bodies = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "synthetic-model"}]})
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"action":"final","outputs":{"result":{}}}'
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    settings = RuntimeSettings(
        model_base_url=base_url, model_id="synthetic-model", provider_type=provider_type
    )
    transport = HttpRuntimeTransport(
        settings,
        http_client=httpx.Client(
            base_url=base_url, transport=httpx.MockTransport(handler)
        ),
    )
    client = RuntimeModelClient(settings, transport=transport)
    assert client.complete_action(
        [{"role": "system", "content": "Return a JSON Agent action"}]
    ).content.startswith('{"action"')
    assert bodies[0].get("response_format") == expected


@pytest.mark.parametrize(
    "operation", ["complete", "review", "stream", "stream_fallback"]
)
def test_adapter_internal_type_error_never_resends_a_model_request(
    operation: str,
) -> None:
    calls: list[dict | None] = []

    def complete(messages, *, response_format=None):
        del messages
        calls.append(response_format)
        raise TypeError("synthetic adapter failure after a request was sent")

    transport = SimpleNamespace(models=lambda: ("synthetic-model",), complete=complete)
    if operation == "stream":
        transport.stream = complete
    client = RuntimeModelClient(
        RuntimeSettings(model_id="synthetic-model", provider_type="moonshot"),
        transport=transport,
    )
    messages = [{"role": "user", "content": "Return a synthetic JSON object"}]
    with pytest.raises(TypeError, match="failure after a request was sent"):
        if operation == "complete":
            client.complete_action(messages)
        elif operation == "review":
            client.complete_review(messages)
        else:
            list(client.stream(messages, response_format={"type": "json_object"}))
    assert calls == [{"type": "json_object"}]


@pytest.mark.parametrize(
    "operation", ["complete", "review", "stream", "stream_fallback"]
)
def test_legacy_adapter_without_response_format_still_sends_exactly_one_request(
    operation: str,
) -> None:
    calls: list[list[dict]] = []

    def complete(messages):
        calls.append(list(messages))
        return RuntimeCompletion(content='{"ok":true}', finish_reason="stop")

    def stream(messages):
        calls.append(list(messages))
        yield '{"ok":true}'

    transport = SimpleNamespace(models=lambda: ("synthetic-model",), complete=complete)
    if operation == "stream":
        transport.stream = stream
    client = RuntimeModelClient(
        RuntimeSettings(model_id="synthetic-model", provider_type="moonshot"),
        transport=transport,
    )
    messages = [{"role": "user", "content": "Return a synthetic JSON object"}]
    if operation == "complete":
        assert client.complete_action(messages).content == '{"ok":true}'
    elif operation == "review":
        assert client.complete_review(messages).content == '{"ok":true}'
    else:
        assert list(
            client.stream(messages, response_format={"type": "json_object"})
        ) == ['{"ok":true}']
    assert calls == [messages]


def test_process_key_is_ignored_when_host_key_is_disallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-ignored")
    client = RuntimeModelClient(RuntimeSettings(allow_process_environment_key=False))
    assert client.configured is False


def test_http_transport_maps_unauthorized_without_leaking_bodies() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    transport = HttpRuntimeTransport(
        RuntimeSettings(),
        http_client=httpx.Client(
            base_url="https://api.moonshot.cn/v1",
            transport=httpx.MockTransport(handler),
        ),
    )
    try:
        transport.models()
    except RuntimeProviderError as exc:
        assert exc.code == "runtime_unauthorized"
        assert "bad key" not in str(exc)
    else:
        raise AssertionError("expected RuntimeProviderError")


def test_compatible_images_keep_base_path_and_use_provider_default_size() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"data": [{"b64_json": ENCODED_PNG}]})

    transport = _image_transport("https://custom.example/api/v2", handler)
    images = transport.generate_images("A dot")
    assert captured[0].url.path == "/api/v2/images/generations"
    assert json.loads(captured[0].content) == {
        "model": "synthetic-model",
        "prompt": "A dot",
        "n": 1,
    }
    assert images[0].contents == PNG
    assert images[0].media_type == "image/png"


@pytest.mark.parametrize(
    ("base_url", "expected_path"),
    [
        (
            "https://dashscope.aliyuncs.com/api/v1",
            "/api/v1/services/aigc/multimodal-generation/generation",
        ),
        (
            "https://workspace.cn-beijing.maas.aliyuncs.com/api/v1",
            "/api/v1/services/aigc/multimodal-generation/generation",
        ),
        (
            "https://custom.example/native/services/aigc/multimodal-generation/generation",
            "/native/services/aigc/multimodal-generation/generation",
        ),
    ],
)
def test_native_image_protocol_uses_message_shape_and_parses_choices(
    base_url: str, expected_path: str
) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "output": {
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {"image": f"data:image/png;base64,{ENCODED_PNG}"}
                                ]
                            }
                        }
                    ]
                }
            },
        )

    transport = _image_transport(base_url, handler)
    assert transport.generate_images("A dot")[0].contents == PNG
    assert captured[0].url.path == expected_path
    assert json.loads(captured[0].content) == {
        "model": "synthetic-model",
        "input": {"messages": [{"role": "user", "content": [{"text": "A dot"}]}]},
        "parameters": {"n": 1},
    }
    transport.generate_images("A dot", size="1024x1536")
    assert json.loads(captured[1].content)["parameters"]["size"] == "1024*1536"


@pytest.mark.parametrize("protocol", ["images", "image_chat"])
def test_unknown_service_negotiates_only_missing_routes_and_reuses_success(
    protocol: str,
) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path.endswith("/images/generations"):
            return httpx.Response(404, json={"error": {"code": "route_not_found"}})
        if protocol == "image_chat" and request.url.path.endswith("/images"):
            return httpx.Response(405)
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"images": [{"image_url": {"url": DATA_PNG}}]}}
                    ]
                },
            )
        return httpx.Response(200, json={"data": [{"b64_json": ENCODED_PNG}]})

    transport = _image_transport("https://unknown.example/api/v7", handler)
    assert transport.generate_images("A dot")[0].contents == PNG
    assert [request.url.path for request in captured] == [
        "/api/v7/images/generations",
        "/api/v7/images",
        *(["/api/v7/chat/completions"] if protocol == "image_chat" else []),
    ]
    last_path = captured[-1].url.path
    if protocol == "image_chat":
        assert json.loads(captured[-1].content) == {
            "model": "synthetic-model",
            "messages": [{"role": "user", "content": "A dot"}],
            "modalities": ["image", "text"],
            "stream": False,
        }
    captured.clear()
    transport.generate_images("Another dot")
    assert [request.url.path for request in captured] == [last_path]


@pytest.mark.parametrize(
    ("status", "payload", "code"),
    [
        (401, {"code": "InvalidApiKey"}, "runtime_unauthorized"),
        (400, {"code": "InvalidParameter"}, "runtime_parameters_unsupported"),
        (403, {"code": "AccessDenied"}, "runtime_permission_denied"),
        (400, {"code": "Arrearage"}, "runtime_insufficient_balance"),
        (
            429,
            {"error": {"code": "insufficient_quota"}},
            "runtime_insufficient_balance",
        ),
        (404, {"code": "ModelNotFound"}, "runtime_model_unavailable"),
        (
            404,
            {"error": {"message": "The model SECRET does not exist"}},
            "runtime_model_unavailable",
        ),
        (
            404,
            {"error": {"message": "No endpoints found for SECRET"}},
            "runtime_model_unavailable",
        ),
        (200, {"data": []}, "runtime_invalid_response"),
        (429, {"error": {"code": "rate_limit_exceeded"}}, "runtime_rate_limited"),
        (400, {"error": {"code": "other_error"}}, "runtime_request_invalid"),
        (500, {"error": {"code": "other_error"}}, "runtime_provider_error"),
    ],
)
def test_image_failures_are_redacted_and_never_try_another_generation_route(
    status: int, payload: dict, code: str
) -> None:
    captured: list[httpx.Request] = []
    payload = dict(payload, message="PRIVATE-KEY-AND-RAW-DETAIL")

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status, json=payload, headers={"x-private": "PRIVATE-HEADER"}
        )

    transport = _image_transport("https://unknown.example/v1", handler)
    with pytest.raises(RuntimeProviderError) as raised:
        transport.generate_images("A dot")
    assert raised.value.code == code
    assert len(captured) == 1
    assert "PRIVATE" not in str(raised.value)
    assert "SECRET" not in str(raised.value)


def test_successful_html_is_a_wrong_address_without_protocol_retry() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            text="<html>PRIVATE-CONSOLE</html>",
            headers={"content-type": "text/html"},
        )

    transport = _image_transport("https://custom.example/v1", handler)
    with pytest.raises(RuntimeProviderError) as raised:
        transport.generate_images("A dot")
    assert raised.value.code == "runtime_endpoint_invalid"
    assert "PRIVATE" not in str(raised.value)
    assert len(calls) == 1


def test_missing_image_routes_stop_after_three_protocols() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(404)

    with pytest.raises(RuntimeProviderError) as raised:
        _image_transport("https://unknown.example/v1", handler).generate_images("Dot")
    assert raised.value.code == "runtime_endpoint_not_found"
    assert len(calls) == 3


@pytest.mark.parametrize(
    "url",
    [
        "https://bailian.console.aliyun.com/cn-beijing/settings/api-key",
        "https://platform.openai.com/api-keys",
        "https://openrouter.ai/settings/keys",
    ],
)
def test_known_console_addresses_are_rejected_before_credentials_are_sent(
    url: str,
) -> None:
    with pytest.raises(ProviderCredentialError) as raised:
        provider_base_url("openai_compatible", url)
    assert raised.value.code == "provider_console_url"
    assert url not in str(raised.value)


def test_generic_text_requests_use_standard_tokens_without_reasoning_extension() -> (
    None
):
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    transport = _image_transport("https://unknown.example/v1", handler)
    assert transport.complete([{"role": "user", "content": "Hello"}]).content == "OK"
    body = json.loads(captured[0].content)
    assert body["max_tokens"] == 8_192
    assert "max_completion_tokens" not in body
    assert "reasoning_effort" not in body


def test_generated_image_cdn_client_never_receives_provider_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cdn_requests: list[httpx.Request] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer SYNTHETIC-SECRET"
        return httpx.Response(
            200, json={"data": [{"url": "https://cdn.example/generated.png"}]}
        )

    def cdn_handler(request: httpx.Request) -> httpx.Response:
        cdn_requests.append(request)
        return httpx.Response(200, content=PNG)

    transport = HttpRuntimeTransport(
        RuntimeSettings(model_base_url="https://unknown.example/v1"),
        http_client=httpx.Client(
            base_url="https://unknown.example/v1",
            headers={"authorization": "Bearer SYNTHETIC-SECRET"},
            transport=httpx.MockTransport(api_handler),
        ),
    )
    cdn_client = httpx.Client(transport=httpx.MockTransport(cdn_handler))
    monkeypatch.setattr(
        "veyra_agent_platform.local.runtime.client.httpx.Client",
        lambda **kwargs: cdn_client,
    )
    assert transport.generate_images("A dot")[0].contents == PNG
    assert len(cdn_requests) == 1
    assert "authorization" not in cdn_requests[0].headers


def test_private_image_urls_and_oversized_bytes_are_rejected() -> None:
    private = _image_transport(
        "https://unknown.example/v1",
        lambda _: httpx.Response(
            200, json={"data": [{"url": "https://127.0.0.1/private.png"}]}
        ),
    )
    with pytest.raises(RuntimeProviderError) as raised:
        private.generate_images("A dot")
    assert raised.value.code == "image_generation_invalid"

    oversized = _image_transport(
        "https://unknown.example/v1",
        lambda _: httpx.Response(
            200,
            json={
                "data": [
                    {"b64_json": b64encode(PNG + b"0" * 20_000_000).decode("ascii")}
                ]
            },
        ),
    )
    with pytest.raises(RuntimeProviderError) as raised:
        oversized.generate_images("A dot")
    assert raised.value.code == "image_generation_invalid"
