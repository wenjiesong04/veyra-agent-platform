from __future__ import annotations

import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "scripts/acceptance/request_budget.py"
)
SPEC = importlib.util.spec_from_file_location("acceptance_request_budget", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
budget_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(budget_module)
RequestBudget = budget_module.RequestBudget
BudgetedClient = budget_module.BudgetedClient
AcceptanceBudgetError = budget_module.AcceptanceBudgetError


@pytest.mark.parametrize(("kind", "limit"), [("text", 32), ("image", 8)])
def test_default_hard_limit_counts_only_sent_posts_and_halts_both_kinds(kind, limit):
    requests = []
    budget = RequestBudget()
    transport = httpx.MockTransport(
        lambda request: (requests.append(request), httpx.Response(200))[1]
    )
    with (
        BudgetedClient(budget=budget, kind=kind, transport=transport) as client,
        BudgetedClient(
            budget=budget,
            kind="image" if kind == "text" else "text",
            transport=transport,
        ) as other,
    ):
        for _ in range(limit):
            client.post("https://provider.invalid/arbitrary-route")
        assert budget.snapshot()["sent"][kind] == limit
        with pytest.raises(AcceptanceBudgetError, match="limit_reached"):
            client.post("https://provider.invalid/arbitrary-route")
        with pytest.raises(AcceptanceBudgetError, match="halted"):
            other.post("https://provider.invalid/arbitrary-route")
    assert len(requests) == limit
    assert len(budget.snapshot()["requests"]) == limit


def test_concurrent_requests_cannot_exceed_limit():
    requests = []
    budget = RequestBudget(text_limit=7)
    transport = httpx.MockTransport(
        lambda request: (requests.append(request), httpx.Response(200))[1]
    )
    with BudgetedClient(budget=budget, kind="text", transport=transport) as client:

        def send(_):
            try:
                client.post("https://provider.invalid/anything")
                return True
            except AcceptanceBudgetError:
                return False

        with ThreadPoolExecutor(max_workers=12) as pool:
            assert sum(pool.map(send, range(40))) == 7
    assert len(requests) == 7
    assert budget.snapshot()["sent"] == {"text": 7, "image": 0}
    assert [row["ordinal"] for row in budget.snapshot()["requests"]] == list(
        range(1, 8)
    )


def test_concurrent_failure_stops_requests_still_waiting_to_send():
    seen = []
    budget = RequestBudget()
    transport = httpx.MockTransport(
        lambda request: (seen.append(request), httpx.Response(500))[1]
    )
    with BudgetedClient(budget=budget, kind="text", transport=transport) as client:

        def send(_):
            try:
                return client.post("https://provider.invalid/").status_code
            except AcceptanceBudgetError:
                return None

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(send, range(16)))
    assert results.count(500) == 1 and results.count(None) == 15
    assert len(seen) == 1 and budget.snapshot()["halted"]


def test_persistence_failure_blocks_before_send_without_incrementing(
    tmp_path, monkeypatch
):
    seen = []
    budget = RequestBudget(state_path=tmp_path / "budget.json")

    def unavailable(*args):
        raise PermissionError("private destination")

    monkeypatch.setattr(budget_module.os, "replace", unavailable)
    with (
        BudgetedClient(
            budget=budget,
            kind="text",
            transport=httpx.MockTransport(
                lambda request: (seen.append(request), httpx.Response(200))[1]
            ),
        ) as client,
        pytest.raises(AcceptanceBudgetError, match="persistence_failed"),
    ):
        client.post("https://provider.invalid/")
    assert seen == []
    assert budget.snapshot()["sent"] == {"text": 0, "image": 0}
    assert budget.snapshot()["requests"] == [] and budget.snapshot()["halted"]


@pytest.mark.parametrize("failure", [400, 429, 500, "timeout", "unexpected"])
def test_first_request_failure_prevents_all_further_posts(failure, tmp_path):
    requests = []
    state = tmp_path / "budget.json"
    budget = RequestBudget(state_path=state)

    def handle(request):
        requests.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("private detail", request=request)
        if failure == "unexpected":
            raise ValueError("private detail")
        return httpx.Response(failure, text="private response")

    transport = httpx.MockTransport(handle)
    with BudgetedClient(budget=budget, kind="image", transport=transport) as client:
        if isinstance(failure, str):
            with pytest.raises((httpx.ReadTimeout, ValueError)):
                client.post(
                    "https://provider.invalid/secret-route",
                    headers={"Authorization": "Bearer private-key"},
                    json={"private": "body"},
                )
        else:
            assert (
                client.post("https://provider.invalid/anything").status_code == failure
            )
        with pytest.raises(AcceptanceBudgetError):
            client.post("https://provider.invalid/anything")
    assert len(requests) == 1
    snapshot = budget.snapshot()
    assert snapshot["halted"] and snapshot["sent"] == {"text": 0, "image": 1}
    assert json.loads(state.read_text()) == snapshot
    assert (
        "private" not in state.read_text()
        and "provider.invalid" not in state.read_text()
    )
    restored = RequestBudget(state_path=state)
    with (
        BudgetedClient(budget=restored, kind="text", transport=transport) as client,
        pytest.raises(AcceptanceBudgetError, match="halted"),
    ):
        client.post("https://provider.invalid/anything")
    assert len(requests) == 1


def test_get_is_free_and_stays_readable_after_halt_without_allowing_posts():
    seen = []
    budget = RequestBudget(text_limit=0)
    transport = httpx.MockTransport(
        lambda request: (seen.append(request.method), httpx.Response(200))[1]
    )
    with BudgetedClient(budget=budget, kind="text", transport=transport) as client:
        client.get("https://provider.invalid/models")
        with pytest.raises(AcceptanceBudgetError):
            client.post("https://provider.invalid/chat")
        client.get("https://cdn.invalid/generated.png")
        with pytest.raises(AcceptanceBudgetError):
            client.post("https://provider.invalid/chat")
    assert seen == ["GET", "GET"]
    assert budget.snapshot()["sent"] == {"text": 0, "image": 0}


def test_stream_is_counted_before_transport_and_preserves_client_configuration():
    budget = RequestBudget()
    seen = []

    def handle(request):
        assert budget.snapshot()["sent"]["image"] == 1
        seen.append(request)
        return httpx.Response(200, stream=httpx.ByteStream(b"data: accepted\n\n"))

    with (
        BudgetedClient(
            budget=budget,
            kind="image",
            base_url="https://provider.invalid/v1/",
            headers={"Authorization": "Bearer original"},
            timeout=17,
            transport=httpx.MockTransport(handle),
        ) as client,
        client.stream("POST", "chat/completions") as response,
    ):
        assert response.read() == b"data: accepted\n\n"
    assert str(seen[0].url) == "https://provider.invalid/v1/chat/completions"
    assert seen[0].headers["Authorization"] == "Bearer original"
    assert seen[0].extensions["timeout"]["read"] == 17
    assert budget.snapshot()["sent"] == {"text": 0, "image": 1}
    assert budget.snapshot()["requests"][0]["outcome"] == "succeeded"


def test_stream_body_exception_halts_before_another_request():
    class BrokenStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"partial"
            raise httpx.ReadTimeout("private stream failure")

    seen = []
    budget = RequestBudget()
    transport = httpx.MockTransport(
        lambda request: (
            seen.append(request),
            httpx.Response(200, stream=BrokenStream()),
        )[1]
    )
    with BudgetedClient(budget=budget, kind="text", transport=transport) as client:
        with (
            pytest.raises(httpx.ReadTimeout),
            client.stream("POST", "https://provider.invalid/completions") as response,
        ):
            response.read()
        with pytest.raises(AcceptanceBudgetError):
            client.post("https://provider.invalid/completions")
    assert len(seen) == 1
    assert budget.snapshot()["requests"][0]["outcome"] == "error"


def test_stream_stopping_at_protocol_done_does_not_report_a_transport_error():
    budget = RequestBudget()
    with (
        BudgetedClient(
            budget=budget,
            kind="text",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, stream=httpx.ByteStream(b"data: answer\n\ndata: [DONE]\n\n")
                )
            ),
        ) as client,
        client.stream("POST", "https://provider.invalid/") as response,
    ):
        for line in response.iter_lines():
            if line == "data: [DONE]":
                break
    assert not budget.snapshot()["halted"]
    assert budget.snapshot()["requests"][0]["outcome"] == "closed"


def test_unfinished_persisted_stream_is_not_resubmitted_after_restart(tmp_path):
    state = tmp_path / "budget.json"
    budget = RequestBudget(state_path=state)
    with BudgetedClient(
        budget=budget,
        kind="text",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, stream=httpx.ByteStream(b"partial"))
        ),
    ) as client:
        response = client.send(
            client.build_request("POST", "https://provider.invalid/"), stream=True
        )
        recovered = RequestBudget(state_path=state)
        assert recovered.snapshot()["halted"]
        assert recovered.snapshot()["sent"]["text"] == 1
        response.close()
