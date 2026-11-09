"""A complete review is required; transport progress is never a verdict."""

import json

import httpx
import pytest

from veyra_agent_platform.local.runtime import completion_stream
from veyra_agent_platform.local.runtime.client import (
    HttpRuntimeTransport,
    RuntimeModelClient,
    RuntimeProviderError,
    RuntimeSettings,
)


def event(value):
    return ("data: " + json.dumps(value) + "\n\n").encode()


def delta(content=None, finish=None, **extra):
    return event(
        {"choices": [{"delta": {"content": content, **extra}, "finish_reason": finish}]}
    )


class Stream(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks, self.closed = chunks, False

    def __iter__(self):
        for chunk in self.chunks:
            if isinstance(chunk, BaseException):
                raise chunk
            if callable(chunk):
                chunk = chunk()
            yield chunk

    def close(self):
        self.closed = True


def client(
    chunks,
    *,
    provider="openai_compatible",
    status=200,
    media="text/event-stream",
    **settings,
):
    stream = Stream(chunks)
    requests = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "synthetic"}]})
        requests.append(request)
        return httpx.Response(status, headers={"content-type": media}, stream=stream)

    config = RuntimeSettings(model_id="synthetic", provider_type=provider, **settings)
    transport = HttpRuntimeTransport(
        config,
        http_client=httpx.Client(
            base_url="https://example.test/v1", transport=httpx.MockTransport(handler)
        ),
    )
    return RuntimeModelClient(config, transport=transport), requests, stream


def test_review_stream_keeps_only_complete_public_content_and_safe_progress():
    model, requests, stream = client(
        [
            b": keepalive\n\n",
            delta(reasoning_content="PRIVATE HIDDEN REASONING"),
            event({"choices": [], "usage": {"completion_tokens": 10}}),
            delta('{"ok":'),
            delta("true}"),
            delta(finish="stop"),
            b"data: [DONE]\n\n",
        ]
    )
    progress = []
    result = model.complete_review(
        [{"role": "user", "content": "Assess"}], on_progress=progress.append
    )
    assert result.content == '{"ok":true}' and result.finish_reason == "stop"
    assert len(requests) == 1 and json.loads(requests[0].content)["stream"] is True
    assert stream.closed and progress[0]["status"] == "connected"
    assert progress[-1]["status"] == "completed"
    assert "PRIVATE" not in json.dumps(progress) + result.content
    assert all(
        set(item) == {"status", "elapsed_ms", "event_count", "content_bytes"}
        for item in progress
    )


@pytest.mark.parametrize(
    "ending,code",
    [
        ([delta(finish="length")], "runtime_output_truncated"),
        ([], "runtime_invalid_response"),
        ([b"data: [DONE]\n\n"], "runtime_invalid_response"),
        ([delta(finish={"private": "value"})], "runtime_invalid_response"),
        ([b"data: not-json-private\n\n"], "runtime_invalid_response"),
    ],
)
def test_complete_json_alone_or_truncation_never_finishes_a_review(ending, code):
    model, requests, stream = client([delta('{"ok":true}'), *ending])
    with pytest.raises(RuntimeProviderError) as caught:
        model.complete_review([{"role": "user", "content": "Assess"}])
    assert caught.value.code == code and len(requests) == 1 and stream.closed
    assert "private" not in str(caught.value) + str(caught.value.diagnostic)


def test_standard_multiline_sse_event_is_parsed():
    payload = json.dumps(
        {"choices": [{"delta": {"content": '{"ok":true}'}, "finish_reason": "stop"}]},
        indent=2,
    )
    multiline = "".join("data: " + line + "\n" for line in payload.splitlines()) + "\n"
    model, requests, _ = client([multiline.encode()])
    assert model.complete_review([]).content == '{"ok":true}'
    assert len(requests) == 1


@pytest.mark.parametrize(
    "status,code,body",
    [
        (
            402,
            "runtime_insufficient_balance",
            {"error": {"code": "insufficient_quota", "message": "private"}},
        ),
        (429, "runtime_rate_limited", {"error": {"message": "private"}}),
        (401, "runtime_unauthorized", {"error": {"message": "private"}}),
    ],
)
def test_stream_http_errors_are_read_and_classified_without_resending(
    status, code, body
):
    model, requests, stream = client(
        [json.dumps(body).encode()], status=status, media="application/json"
    )
    with pytest.raises(RuntimeProviderError) as caught:
        model.complete_review([])
    assert caught.value.code == code
    assert len(requests) == 1 and stream.closed and "private" not in str(caught.value)


def test_sse_provider_error_is_not_a_partial_success():
    model, requests, stream = client(
        [
            delta('{"ok":true}'),
            event({"error": {"code": "insufficient_quota", "message": "private"}}),
        ]
    )
    with pytest.raises(RuntimeProviderError) as caught:
        model.complete_review([])
    assert caught.value.code == "runtime_insufficient_balance"
    assert len(requests) == 1 and stream.closed


def test_gateway_json_response_is_consumed_without_a_second_post():
    body = {
        "choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}]
    }
    model, requests, stream = client(
        [json.dumps(body).encode()], media="application/json"
    )
    assert model.complete_review([]).content == '{"ok":true}'
    assert len(requests) == 1 and stream.closed


def test_anthropic_thinking_and_ping_are_not_retained():
    model, requests, stream = client(
        [
            event({"type": "ping"}),
            event(
                {
                    "type": "content_block_delta",
                    "delta": {"type": "thinking_delta", "thinking": "PRIVATE"},
                }
            ),
            event(
                {
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": '{"ok":true}'},
                }
            ),
            event({"type": "message_delta", "delta": {"stop_reason": "end_turn"}}),
            event({"type": "message_stop"}),
        ],
        provider="anthropic",
    )
    progress = []
    assert (
        model.complete_review([], on_progress=progress.append).content == '{"ok":true}'
    )
    assert (
        "PRIVATE" not in json.dumps(progress) and stream.closed and len(requests) == 1
    )


@pytest.mark.parametrize("reason", ["max_tokens", "tool_use", None])
def test_anthropic_requires_a_normal_complete_message(reason):
    model, requests, _ = client(
        [
            event(
                {
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": '{"ok":true}'},
                }
            ),
            event({"type": "message_delta", "delta": {"stop_reason": reason}}),
            event({"type": "message_stop"}),
        ],
        provider="anthropic",
    )
    with pytest.raises(RuntimeProviderError):
        model.complete_review([])
    assert len(requests) == 1


def test_timeout_after_progress_is_safe_and_does_not_retry():
    model, requests, stream = client(
        [delta(reasoning_content="private"), httpx.ReadTimeout("private credential")]
    )
    with pytest.raises(RuntimeProviderError) as caught:
        model.complete_review([])
    assert caught.value.code == "runtime_timeout"
    assert caught.value.diagnostic["timeout_phase"] == "read"
    assert caught.value.diagnostic["event_count"] == 1
    assert "private" not in str(caught.value) and len(requests) == 1 and stream.closed


def test_heartbeat_cannot_extend_the_total_review_deadline(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(completion_stream, "monotonic", lambda: now[0])

    def late_heartbeat():
        now[0] = 3.0
        return b": heartbeat\n\n"

    model, requests, stream = client([late_heartbeat], review_max_duration_seconds=2)
    with pytest.raises(RuntimeProviderError) as caught:
        model.complete_review([])
    assert caught.value.diagnostic["timeout_phase"] == "deadline"
    assert len(requests) == 1 and stream.closed


def test_cancellation_after_progress_closes_stream_without_a_verdict():
    cancelled = [False]
    model, requests, stream = client(
        [delta(reasoning_content="private"), delta('{"ok":true}', "stop")]
    )

    def progress(item):
        if item["event_count"]:
            cancelled[0] = True

    with pytest.raises(RuntimeProviderError) as caught:
        model.complete_review(
            [], on_progress=progress, is_cancelled=lambda: cancelled[0]
        )
    assert (
        caught.value.code == "runtime_cancelled"
        and len(requests) == 1
        and stream.closed
    )


def test_cancellation_before_dispatch_sends_no_post():
    model, requests, _ = client([])
    with pytest.raises(RuntimeProviderError, match="cancelled"):
        model.complete_review([], is_cancelled=lambda: True)
    assert requests == []


def test_unterminated_line_cannot_hide_deadline_checks(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(completion_stream, "monotonic", lambda: now[0])

    def partial():
        now[0] = 3.0
        return b'data: {"choices":'

    def must_not_read():
        raise AssertionError("Read another chunk after the deadline")

    model, requests, stream = client(
        [partial, must_not_read], review_max_duration_seconds=2
    )
    with pytest.raises(RuntimeProviderError) as caught:
        model.complete_review([])
    assert caught.value.diagnostic["timeout_phase"] == "deadline"
    assert len(requests) == 1 and stream.closed


def test_unterminated_line_size_is_bounded_before_another_network_read():
    model, requests, stream = client(
        [b"data: " + b"x" * (completion_stream.MAX_EVENT_BYTES + 1)]
    )
    with pytest.raises(RuntimeProviderError, match="line was too large"):
        model.complete_review([])
    assert len(requests) == 1 and stream.closed


def test_large_json_response_cannot_accept_a_valid_truncated_prefix():
    envelope = json.dumps(
        {"choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}]}
    ).encode()
    limit = 256 * 32
    model, requests, stream = client(
        [envelope + b" " * (limit - len(envelope)), b"private trailing garbage"],
        media="application/json",
        max_completion_tokens=256,
    )
    with pytest.raises(RuntimeProviderError, match="output envelope"):
        model.complete_review([])
    assert len(requests) == 1 and stream.closed


@pytest.mark.parametrize(
    "reason", ["cancelled", "error", "function_call", "length", ["stop"]]
)
def test_json_gateway_cannot_hide_an_abnormal_finish(reason):
    envelope = {
        "choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": reason}]
    }
    model, requests, _ = client(
        [json.dumps(envelope).encode()], media="application/json"
    )
    with pytest.raises(RuntimeProviderError):
        model.complete_review([])
    assert len(requests) == 1


@pytest.mark.parametrize("newline", ["\r", "\r\n"])
def test_sse_accepts_cr_delimiters_across_network_chunks(newline):
    wire = delta('{"ok":true}', "stop").decode().replace("\n", newline).encode()
    model, requests, _ = client([wire[:-1], wire[-1:]])
    assert model.complete_review([]).content == '{"ok":true}'
    assert len(requests) == 1
