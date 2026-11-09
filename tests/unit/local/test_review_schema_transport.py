import json
from dataclasses import replace

import httpx
import pytest

from veyra_agent_platform.contracts.finalization import FinalizationContract
from veyra_agent_platform.local.factory.capability_profile import (
    derive_provider_capability_profile,
)
from veyra_agent_platform.local.runtime.client import (
    HttpRuntimeTransport,
    RuntimeModelClient,
    RuntimeProviderError,
)
from veyra_agent_platform.local.runtime.config import RuntimeSettings
from veyra_agent_platform.local.runtime.finalization import candidate_review_schema


def _settings(base_url="https://api.moonshot.cn/v1"):
    return RuntimeSettings(
        provider_type="openai_compatible",
        model_base_url=base_url,
        model_id="synthetic-model",
        allow_process_environment_key=False,
    )


def _verified(settings):
    return replace(
        derive_provider_capability_profile(settings),
        status="known",
        source="probe",
        probed=True,
        checked_at="2026-10-19T00:00:00Z",
        strict_json_schema=True,
        strict_json_schema_support="supported",
        json_object_support="supported",
    )


def _schema():
    return candidate_review_schema(
        FinalizationContract(criteria=tuple(f"Check {i}" for i in range(13))), []
    )


def test_verified_review_sends_all_required_slots_without_changing_action_protocol():
    settings = _settings()
    bodies = []
    looked_up = []
    profile = _verified(settings)

    def lookup(identity):
        looked_up.append(identity)
        return profile

    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": settings.model_id}]})
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}
                ]
            },
        )

    http = httpx.Client(
        base_url=settings.model_base_url, transport=httpx.MockTransport(handler)
    )
    transport = HttpRuntimeTransport(settings, http_client=http)
    client = RuntimeModelClient(
        settings, transport=transport, provider_capability_lookup=lookup
    )
    messages = [{"role": "user", "content": "Synthetic assessment"}]
    with http:
        client.complete_action(messages)
        completion = client.complete_review(messages, schema=_schema())
        client.complete_action(messages)
    assert looked_up == [profile.identity_key]
    assert (
        bodies[0]["response_format"]
        == bodies[2]["response_format"]
        == {"type": "json_object"}
    )
    assert bodies[1]["stream"] is True
    wire = bodies[1]["response_format"]
    assert wire["type"] == completion.review_protocol == "json_schema"
    assert wire["json_schema"]["strict"] is True
    slots = wire["json_schema"]["schema"]["properties"]["findings"]
    assert slots["required"] == [str(i) for i in range(13)]
    assert slots["additionalProperties"] is False
    assert set(slots["properties"]) == set(slots["required"])


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "unknown"},
        {"status": "stale"},
        {"source": "static_known"},
        {"probed": False},
        {"checked_at": None},
        {"strict_json_schema_support": "unknown"},
        {"strict_json_schema": False},
        {"model": "another-model"},
        {"base_url_fingerprint": "another-endpoint"},
        {"endpoint_kind": "responses"},
        {"probe_version": "another-probe"},
        {"provider_id": "another-provider"},
        {"schema_flavor": "none"},
    ],
)
def test_unverified_or_mismatched_profile_cannot_enable_strict_review(changes):
    settings = _settings()
    wrong = replace(_verified(settings), **changes)
    client = RuntimeModelClient(settings, provider_capability_lookup=lambda _: wrong)
    assert client._review_response_format(_schema()) == {"type": "json_object"}


def test_missing_profile_keeps_unknown_compatible_transport_without_new_parameters():
    client = RuntimeModelClient(
        _settings("https://example.test/v1"), provider_capability_lookup=lambda _: None
    )
    assert client._review_response_format(_schema()) is None


def test_verified_schema_rejection_does_not_dispatch_a_second_request():
    settings = _settings()
    requests = []

    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": settings.model_id}]})
        requests.append(request)
        return httpx.Response(
            400, json={"error": {"message": "Unsupported response format"}}
        )

    http = httpx.Client(
        base_url=settings.model_base_url, transport=httpx.MockTransport(handler)
    )
    client = RuntimeModelClient(
        settings,
        transport=HttpRuntimeTransport(settings, http_client=http),
        provider_capability_lookup=lambda _: _verified(settings),
    )
    with http, pytest.raises(RuntimeProviderError):
        client.complete_review(
            [{"role": "user", "content": "Synthetic review"}], schema=_schema()
        )
    assert len(requests) == 1


def test_native_messages_does_not_reuse_a_chat_schema_profile():
    settings = _settings("https://api.moonshot.cn").model_copy(
        update={"provider_type": "anthropic"}
    )
    requests = []
    looked_up = []

    def lookup(identity):
        looked_up.append(identity)
        return _verified(settings)

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": settings.model_id}]})
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": '{"ok":true}'}],
                "stop_reason": "end_turn",
            },
        )

    http = httpx.Client(
        base_url=settings.model_base_url, transport=httpx.MockTransport(handler)
    )
    client = RuntimeModelClient(
        settings,
        transport=HttpRuntimeTransport(settings, http_client=http),
        provider_capability_lookup=lookup,
    )
    with http:
        completion = client.complete_review(
            [{"role": "user", "content": "Synthetic review"}], schema=_schema()
        )
    assert looked_up == []
    assert len(requests) == 1 and requests[0].url.path == "/v1/messages"
    assert "response_format" not in json.loads(requests[0].content)
    assert completion.content == '{"ok":true}'
    assert completion.review_protocol == "text"
