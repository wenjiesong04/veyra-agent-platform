"""Request caps for an isolated paid acceptance process, not product Run budgets."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal

import httpx

RequestKind = Literal["text", "image"]
_OUTCOMES = {"sending", "streaming", "succeeded", "closed", "http_error", "error"}


class AcceptanceBudgetError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RequestBudget:
    def __init__(
        self,
        text_limit: int = 32,
        image_limit: int = 8,
        *,
        state_path: Path | None = None,
    ) -> None:
        if any(
            type(value) is not int or value < 0 for value in (text_limit, image_limit)
        ):
            raise ValueError("Request limits must be nonnegative integers")
        self._limits = {"text": text_limit, "image": image_limit}
        self._sent = {"text": 0, "image": 0}
        self._halted = False
        self._requests: list[dict[str, Any]] = []
        self._lock = threading.RLock()
        self._state_path = state_path
        if state_path is not None and state_path.exists():
            self._restore()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "limits": dict(self._limits),
                "sent": dict(self._sent),
                "halted": self._halted,
                "requests": [dict(record) for record in self._requests],
            }

    def halt(self) -> None:
        with self._lock:
            self._halted = True
            self._persist()

    def _begin(self, kind: RequestKind) -> dict[str, Any]:
        if self._halted:
            raise AcceptanceBudgetError("acceptance_requests_halted")
        if self._sent[kind] >= self._limits[kind]:
            self.halt()
            raise AcceptanceBudgetError("acceptance_request_limit_reached")
        record = {
            "kind": kind,
            "ordinal": self._sent[kind] + 1,
            "outcome": "sending",
            "status": None,
            "elapsed_ms": 0.0,
        }
        self._sent[kind] += 1
        self._requests.append(record)
        try:
            self._persist()
        except AcceptanceBudgetError:
            self._sent[kind] -= 1
            self._requests.pop()
            raise
        return record

    def _finish(
        self,
        record: dict[str, Any],
        outcome: str,
        status: int | None,
        started: float,
    ) -> None:
        with self._lock:
            record.update(
                outcome=outcome,
                status=status,
                elapsed_ms=round((time.monotonic() - started) * 1000, 3),
            )
            if outcome in {"http_error", "error"}:
                self._halted = True
            self._persist()

    def _persist(self) -> None:
        if self._state_path is None:
            return
        temporary: str | None = None
        try:
            descriptor, temporary = tempfile.mkstemp(
                prefix=".acceptance-budget-", dir=self._state_path.parent
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(self.snapshot(), stream, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._state_path)
        except OSError:
            self._halted = True
            raise AcceptanceBudgetError(
                "acceptance_budget_persistence_failed"
            ) from None
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)

    def _restore(self) -> None:
        assert self._state_path is not None
        try:
            saved = json.loads(self._state_path.read_text(encoding="utf-8"))
            assert set(saved) == {"limits", "sent", "halted", "requests"}
            assert saved["limits"] == self._limits
            assert type(saved["halted"]) is bool
            assert isinstance(saved["requests"], list)
            counts = {"text": 0, "image": 0}
            for record in saved["requests"]:
                assert set(record) == {
                    "kind",
                    "ordinal",
                    "outcome",
                    "status",
                    "elapsed_ms",
                }
                kind = record["kind"]
                assert kind in counts
                counts[kind] += 1
                assert type(record["ordinal"]) is int
                assert record["ordinal"] == counts[kind] <= self._limits[kind]
                assert record["outcome"] in _OUTCOMES
                status = record["status"]
                assert status is None or (type(status) is int and 100 <= status <= 599)
                assert type(record["elapsed_ms"]) in {int, float}
                assert 0 <= record["elapsed_ms"] < float("inf")
            assert saved["sent"] == counts
        except (AssertionError, OSError, ValueError, TypeError, KeyError):
            raise AcceptanceBudgetError("acceptance_budget_state_invalid") from None
        self._sent = counts
        self._requests = saved["requests"]
        self._halted = saved["halted"] or any(
            record["outcome"] in {"sending", "streaming", "http_error", "error"}
            for record in self._requests
        )
        self._persist()


class BudgetedClient(httpx.Client):
    def __init__(
        self, *, budget: RequestBudget, kind: RequestKind, **kwargs: Any
    ) -> None:
        if kind not in {"text", "image"}:
            raise ValueError("Request kind must be text or image")
        self._budget = budget
        self._kind = kind
        super().__init__(**kwargs)

    def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        if request.method != "POST":
            try:
                response = super().send(request, **kwargs)
            except BaseException:
                self._budget.halt()
                raise
            if response.status_code >= 400:
                self._budget.halt()
            return response
        # Serialize admission through the response headers (the whole nonstream send).
        with self._budget._lock:
            record = self._budget._begin(self._kind)
            started = time.monotonic()
            try:
                response = super().send(request, **kwargs)
            except BaseException:
                self._budget._finish(record, "error", None, started)
                raise
            if response.status_code >= 400:
                self._budget._finish(
                    record, "http_error", response.status_code, started
                )
            elif kwargs.get("stream", False) and not response.is_stream_consumed:
                self._budget._finish(record, "streaming", response.status_code, started)
                assert isinstance(response.stream, httpx.SyncByteStream)
                response.stream = _BudgetedStream(
                    response.stream, self._budget, record, response.status_code, started
                )
            else:
                self._budget._finish(record, "succeeded", response.status_code, started)
            return response


class _BudgetedStream(httpx.SyncByteStream):
    def __init__(
        self,
        stream: httpx.SyncByteStream,
        budget: RequestBudget,
        record: dict[str, Any],
        status: int,
        started: float,
    ) -> None:
        self._stream, self._budget, self._record = stream, budget, record
        self._status, self._started, self._finished = status, started, False

    def __iter__(self) -> Iterator[bytes]:
        try:
            yield from self._stream
        except GeneratorExit:
            raise
        except BaseException:
            self._finish("error")
            raise
        else:
            self._finish("succeeded")

    def close(self) -> None:
        try:
            self._stream.close()
        except BaseException:
            self._finish("error")
            raise
        if not self._finished:
            self._finish("closed")

    def _finish(self, outcome: str) -> None:
        self._finished = True
        self._budget._finish(self._record, outcome, self._status, self._started)
