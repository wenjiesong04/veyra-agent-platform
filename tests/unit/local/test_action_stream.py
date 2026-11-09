"""Action transport progress must never become a partially executable action."""

import json

import httpx
import pytest

from tests.unit.local.test_agent_loop_runtime import _HarnessHost, _tool_loop_source
from tests.unit.local.test_review_stream import Stream, client, delta
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime import completion_stream
from veyra_agent_platform.local.runtime.client import (
    HttpRuntimeTransport,
    RuntimeModelClient,
    RuntimeProviderError,
    RuntimeSettings,
)
from veyra_agent_platform.local.runtime.service import RuntimeError


def test_action_aggregates_slow_active_response_without_changing_idle_timeout(
    monkeypatch,
):
    now = [0.0]
    monkeypatch.setattr(completion_stream, "monotonic", lambda: now[0])

    def chunk(at, content):
        def receive():
            now[0] = at
            return content

        return receive

    model, requests, stream = client(
        [
            chunk(1, delta(reasoning_content="PRIVATE REASONING")),
            chunk(60, b": heartbeat\n\n"),
            chunk(95, delta('{"action":"final",')),
            delta('"outputs":{"result":"done"}}', "stop"),
        ],
        provider="moonshot",
        review_timeout_seconds=2,
        review_max_duration_seconds=2,
        action_max_duration_seconds=150,
    )
    progress = []
    result = model.complete_action([], on_progress=progress.append)
    assert json.loads(result.content)["outputs"] == {"result": "done"}
    assert result.review_protocol is None and result.finish_reason == "stop"
    assert len(requests) == 1 and stream.closed
    assert requests[0].extensions["timeout"]["read"] == 90
    body = json.loads(requests[0].content)
    assert body["stream"] is True and body["response_format"] == {"type": "json_object"}
    assert progress[-1]["status"] == "completed"
    assert progress[-1]["elapsed_ms"] == 95_000
    assert "PRIVATE" not in result.content + json.dumps(progress)
    assert all(
        set(item) == {"status", "elapsed_ms", "event_count", "content_bytes"}
        for item in progress
    )


@pytest.mark.parametrize(
    "ending,code",
    [
        ([], "runtime_invalid_response"),
        ([delta(finish="length")], "runtime_output_truncated"),
        ([delta(tool_calls=[{"id": "private"}])], "runtime_invalid_response"),
        ([delta(refusal="private")], "runtime_invalid_response"),
        ([b"data: not-json-private\n\n"], "runtime_invalid_response"),
        ([httpx.ReadTimeout("private credential")], "runtime_timeout"),
    ],
)
def test_action_never_dispatches_a_complete_json_prefix_before_normal_end(
    tmp_path, ending, code
):
    resource = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    host = _HarnessHost(tmp_path, resource)
    action = {
        "action": "tool",
        "tool": resource["reference"],
        "arguments": {"path": "notes.txt"},
    }
    model, requests, stream = client([delta(json.dumps(action)), *ending])
    with pytest.raises(RuntimeError) as caught:
        host._execute_loop("project", "run", _tool_loop_source(resource), {}, model)
    assert caught.value.code == code
    assert len(requests) == 1 and stream.closed and not host.effects
    assert not any(kind == "tool.started" for _, kind, _ in host.events)
    progress = [payload for _, kind, payload in host.events if kind == "model.progress"]
    assert progress and all(item["published"] is False for item in progress)
    assert "private" not in json.dumps(progress)
    assert "arguments" not in json.dumps(progress)


def test_action_json_gateway_consumes_the_same_response_once():
    envelope = {
        "choices": [
            {
                "message": {
                    "content": '{"action":"final","outputs":{"result":"done"}}'
                },
                "finish_reason": "stop",
            }
        ]
    }
    model, requests, stream = client(
        [json.dumps(envelope).encode()], media="application/json"
    )
    assert json.loads(model.complete_action([]).content)["outputs"]["result"] == "done"
    assert stream.closed and len(requests) == 1


def test_action_heartbeat_cannot_extend_its_own_deadline(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(completion_stream, "monotonic", lambda: now[0])

    def partial():
        now[0] = 3
        return b'data: {"choices":'

    model, requests, stream = client(
        [partial], action_max_duration_seconds=2, review_max_duration_seconds=100
    )
    with pytest.raises(RuntimeProviderError) as caught:
        model.complete_action([])
    assert caught.value.diagnostic["timeout_phase"] == "deadline"
    assert caught.value.diagnostic["timeout_seconds"] == 2
    assert len(requests) == 1 and stream.closed


@pytest.mark.parametrize("cancel_before", [True, False])
def test_action_cancellation_does_not_return_a_partial_or_late_result(cancel_before):
    cancelled = [cancel_before]
    model, requests, stream = client(
        [delta('{"action":"final","outputs":{"result":"done"}}', "stop")]
    )

    def progress(item):
        if item["status"] == "receiving_result":
            cancelled[0] = True

    with pytest.raises(RuntimeProviderError) as caught:
        model.complete_action(
            [], on_progress=progress, is_cancelled=lambda: cancelled[0]
        )
    assert caught.value.code == "runtime_cancelled"
    assert len(requests) == (0 if cancel_before else 1)
    assert cancel_before or stream.closed


@pytest.mark.parametrize("json_gateway", [False, True])
def test_normally_finished_empty_action_retains_safe_recovery_diagnostic(json_gateway):
    chunks = (
        [
            json.dumps(
                {"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]}
            ).encode()
        ]
        if json_gateway
        else [delta(finish="stop")]
    )
    model, requests, stream = client(
        chunks, media="application/json" if json_gateway else "text/event-stream"
    )
    with pytest.raises(RuntimeProviderError) as caught:
        model.complete_action([])
    diagnostic = caught.value.diagnostic
    assert caught.value.code == "runtime_invalid_response"
    assert diagnostic["finish_reason"] == "stop" and diagnostic["content_empty"] is True
    assert not diagnostic.get("has_tool_calls") and not diagnostic.get("has_refusal")
    assert len(requests) == 1 and stream.closed


def test_existing_single_empty_completion_recovery_still_uses_one_new_turn(tmp_path):
    requests, streams = [], []
    replies = iter(
        [
            [delta(finish="stop")],
            [delta('{"action":"final","outputs":{"translation":"done"}}', "stop")],
        ]
    )

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "synthetic"}]})
        requests.append(request)
        stream = Stream(next(replies))
        streams.append(stream)
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=stream
        )

    settings = RuntimeSettings(model_id="synthetic")
    transport = HttpRuntimeTransport(
        settings,
        http_client=httpx.Client(
            base_url="https://example.test/v1", transport=httpx.MockTransport(handler)
        ),
    )
    model = RuntimeModelClient(settings, transport=transport)
    resource = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    host = _HarnessHost(tmp_path, resource)
    outcome = host._execute_loop(
        "project", "run", _tool_loop_source(resource), {}, model
    )
    assert outcome.result == {"translation": "done"} and not host.effects
    assert len(requests) == 2 and all(stream.closed for stream in streams)
    assert (
        sum(
            kind == "node.started" and payload.get("phase") == "model"
            for _, kind, payload in host.events
        )
        == 2
    )
    assert sum(kind == "model.output_rejected" for _, kind, _ in host.events) == 1
