from __future__ import annotations

import gzip
import json
import zlib

import httpx
import pytest

from tests.unit.local.test_review_stream import Stream, delta
from veyra_agent_platform.local.runtime.client import (
    HttpRuntimeTransport,
    RuntimeModelClient,
    RuntimeProviderError,
    RuntimeSettings,
)


def model(handler):
    settings = RuntimeSettings(model_id="synthetic", provider_type="openai_compatible")
    http = httpx.Client(
        base_url="https://example.test/v1",
        headers={"Authorization": "Bearer PRIVATE_FIXTURE_TOKEN"},
        transport=httpx.MockTransport(handler),
    )
    original = dict(http.headers)
    return (
        RuntimeModelClient(
            settings, transport=HttpRuntimeTransport(settings, http_client=http)
        ),
        http,
        original,
    )


@pytest.mark.parametrize("method", ["complete_action", "complete_review"])
def test_stream_requests_identity_without_changing_auth_client_or_discovery(method):
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "synthetic"}]})
        assert request.headers["accept-encoding"] == "identity"
        assert request.headers["authorization"] == "Bearer PRIVATE_FIXTURE_TOKEN"
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=Stream([delta("safe"), delta(finish="stop")]),
        )

    client, http, original = model(handler)
    assert (
        getattr(client, method)([{"role": "user", "content": "request"}]).content
        == "safe"
    )
    assert len(requests) == 2 and requests[0].method == "GET"
    assert requests[0].headers["accept-encoding"] == original["accept-encoding"]
    assert dict(http.headers) == original


@pytest.mark.parametrize("method", ["complete_action", "complete_review"])
def test_malformed_encoding_has_safe_response_diagnostic_and_no_retry(method):
    posts = []
    stream = Stream([b"PRIVATE_RAW_REASONING_NOT_A_GZIP_STREAM"])

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "synthetic"}]})
        posts.append(request)
        return httpx.Response(
            200,
            headers={
                "content-type": "text/event-stream; charset=utf-8",
                "content-encoding": "gzip",
                "x-private": "PRIVATE_HEADER",
            },
            stream=stream,
        )

    client, _, _ = model(handler)
    progress = []
    with pytest.raises(RuntimeProviderError) as caught:
        getattr(client, method)(
            [{"role": "user", "content": "request"}], on_progress=progress.append
        )
    assert caught.value.code == "runtime_invalid_response"
    assert caught.value.diagnostic == {
        "category": "response_decoding",
        "http_status": 200,
        "response_content_type": "text/event-stream",
        "response_content_encoding": "gzip",
        "event_count": 0,
        "content_bytes": 0,
    }
    assert len(posts) == 1 and stream.closed
    assert not any(event["status"] == "completed" for event in progress)
    assert "PRIVATE" not in str(caught.value) + json.dumps(
        caught.value.diagnostic
    ) + json.dumps(progress)


@pytest.mark.parametrize("method", ["complete_action", "complete_review"])
@pytest.mark.parametrize("encoding", ["gzip", "deflate"])
@pytest.mark.parametrize("json_gateway", [False, True])
def test_compliant_compressed_responses_remain_supported(
    method, encoding, json_gateway
):
    if json_gateway:
        raw = json.dumps(
            {"choices": [{"message": {"content": "safe"}, "finish_reason": "stop"}]}
        ).encode()
    else:
        raw = delta("safe") + delta(finish="stop")
    compressed = gzip.compress(raw) if encoding == "gzip" else zlib.compress(raw)
    stream = Stream([compressed[:5], compressed[5:]])
    posts = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "synthetic"}]})
        posts.append(request)
        return httpx.Response(
            200,
            headers={
                "content-type": "application/json"
                if json_gateway
                else "text/event-stream",
                "content-encoding": encoding,
            },
            stream=stream,
        )

    client, _, _ = model(handler)
    assert (
        getattr(client, method)([{"role": "user", "content": "request"}]).content
        == "safe"
    )
    assert len(posts) == 1 and stream.closed


@pytest.mark.parametrize("encoding", ["gzip", "deflate"])
@pytest.mark.parametrize(
    "status,code",
    [
        (401, "runtime_unauthorized"),
        (403, "runtime_permission_denied"),
        (429, "runtime_rate_limited"),
        (503, "runtime_provider_error"),
    ],
)
def test_compressed_provider_errors_are_classified_once_without_double_decoding(
    encoding, status, code
):
    raw = json.dumps(
        {"error": {"code": "unclassified", "message": "PRIVATE_ERROR_BODY"}}
    ).encode()
    compressed = gzip.compress(raw) if encoding == "gzip" else zlib.compress(raw)
    stream = Stream([compressed])
    posts = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "synthetic"}]})
        posts.append(request)
        return httpx.Response(
            status,
            headers={
                "content-type": "application/json",
                "content-encoding": encoding,
                "content-length": str(len(compressed)),
            },
            stream=stream,
        )

    client, _, _ = model(handler)
    with pytest.raises(RuntimeProviderError) as caught:
        client.complete_action([{"role": "user", "content": "request"}])
    assert caught.value.code == code
    assert caught.value.diagnostic["http_status"] == status
    assert caught.value.diagnostic["response_content_encoding"] == encoding
    assert "PRIVATE" not in str(caught.value) + json.dumps(caught.value.diagnostic)
    assert len(posts) == 1 and stream.closed


@pytest.mark.parametrize("method", ["complete_action", "complete_review"])
def test_non_json_access_denial_does_not_invent_a_key_permission_cause(method):
    posts = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "synthetic"}]})
        posts.append(request)
        return httpx.Response(
            403,
            headers={"content-type": "text/html; charset=utf-8"},
            stream=Stream([b"PRIVATE_ERROR_BODY"]),
        )

    client, _, _ = model(handler)
    with pytest.raises(RuntimeProviderError) as caught:
        getattr(client, method)([{"role": "user", "content": "request"}])
    assert caught.value.code == "runtime_permission_denied"
    assert str(caught.value) == (
        "The model service refused access (HTTP 403); "
        "the response does not establish the specific cause"
    )
    assert caught.value.diagnostic == {
        "http_status": 403,
        "response_content_type": "other",
        "response_content_encoding": "identity",
    }
    assert len(posts) == 1
    assert "PRIVATE" not in str(caught.value) + json.dumps(caught.value.diagnostic)
