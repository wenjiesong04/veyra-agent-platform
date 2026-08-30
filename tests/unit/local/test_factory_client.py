from __future__ import annotations

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
    else:
        raise AssertionError("expected FactoryProviderError")
