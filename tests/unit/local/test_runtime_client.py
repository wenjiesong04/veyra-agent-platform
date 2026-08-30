from __future__ import annotations

import httpx
import pytest

from veyra_agent_platform.local.runtime.client import (
    HttpRuntimeTransport,
    RuntimeModelClient,
    RuntimeProviderError,
    RuntimeSettings,
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
