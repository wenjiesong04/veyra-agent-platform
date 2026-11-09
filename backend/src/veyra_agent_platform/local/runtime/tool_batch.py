"""One model action containing independent, trusted local observation calls."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from veyra_agent_platform.contracts.agent import AgentSource

from .tools import ToolAuthorization

MAX_BATCH_CALLS = 16


class _BatchHost(Protocol):
    tools: Any

    def _is_running(self, run_id: str) -> bool: ...

    def _loop_authorize(
        self,
        project_id: str,
        source: AgentSource,
        reference: str,
        arguments: Mapping[str, Any],
    ) -> ToolAuthorization: ...

    def _loop_run_tool(
        self,
        project_id: str,
        run_id: str,
        source: AgentSource,
        pending: Mapping[str, Any],
        emit: Any,
        tool_calls: list[Any],
        *,
        approved: bool,
        input_files: Mapping[str, Any] | None = None,
    ) -> Any: ...


def execute_tool_batch(
    host: _BatchHost,
    project_id: str,
    run_id: str,
    source: AgentSource,
    calls: Sequence[Mapping[str, Any]],
    emit: Callable[[str | None, str, dict[str, Any]], None],
    tool_calls: list[Any],
    *,
    input_files: Mapping[str, Any],
    turn: int,
) -> dict[str, Any]:
    from .agent_loop import (
        _MAX_OBSERVATION_CHARS,
        _resolve_tool_reference,
        _state_tool_input_error,
    )
    from .service import RuntimeError, _ExecutionPause, _RunAbandoned
    from .tool_input_contract import tool_input_issue

    diagnostics: list[dict[str, Any]] = []
    prepared: list[tuple[int, str, dict[str, Any], ToolAuthorization]] = []
    size = len(calls) if isinstance(calls, list | tuple) else 0

    def reject(index: int, reference: str | None, diagnostic: dict[str, Any]) -> None:
        diagnostic = {
            "stage": "tool_input",
            **diagnostic,
            "summary": diagnostic.get("summary")
            or diagnostic.get("message", "Tool batch input rejected"),
        }
        emit(
            "tool",
            "tool.input_rejected",
            {
                "code": diagnostic["code"],
                "tool_reference": reference,
                "effect_started": False,
                "batch_index": index,
                "batch_size": size,
                "turn": turn,
                "diagnostic": diagnostic,
            },
        )
        diagnostics.append(
            {"index": index, "reference": reference, "diagnostic": diagnostic}
        )

    if not 1 <= size <= MAX_BATCH_CALLS:
        reject(
            -1,
            None,
            {
                "code": "tool_batch_invalid",
                "message": f"A tool batch needs 1 to {MAX_BATCH_CALLS} calls.",
            },
        )
    else:
        # Complete the no-effect preflight before dispatching even the first call.
        for index, call in enumerate(calls):
            if not host._is_running(run_id):
                raise _RunAbandoned()
            if (
                not isinstance(call, Mapping)
                or set(call) - {"tool", "arguments"}
                or not isinstance(call.get("tool"), str)
            ):
                reject(
                    index,
                    None,
                    {
                        "code": "tool_batch_invalid",
                        "message": "Each call needs a tool reference and arguments.",
                    },
                )
                continue
            reference = _resolve_tool_reference(source, call["tool"])
            if reference is None:
                reject(
                    index,
                    None,
                    {
                        "code": "tool_reference_invalid",
                        "message": "Use an exact reference from the permitted catalog.",
                    },
                )
                continue
            raw_arguments = call.get("arguments")
            arguments = dict(raw_arguments) if isinstance(raw_arguments, dict) else {}
            authorization = host._loop_authorize(
                project_id, source, reference, arguments
            )
            if authorization.decision != "allowed":
                reject(
                    index,
                    reference,
                    {"code": authorization.code, "message": authorization.reason},
                )
                raise RuntimeError(authorization.code, authorization.reason)
            if authorization.approval_required:
                reject(
                    index,
                    reference,
                    {
                        "code": "tool_batch_approval_required",
                        "message": "Use a single tool action for approval.",
                    },
                )
                continue
            if not host.tools.can_batch_observation(authorization):
                reject(
                    index,
                    reference,
                    {
                        "code": "tool_batch_unsafe",
                        "message": "Only trusted local observations can be batched.",
                    },
                )
                continue
            issue = tool_input_issue(authorization.resource, raw_arguments)
            if issue is not None:
                reject(
                    index,
                    reference,
                    {"code": "tool_input_schema_invalid", **issue.to_dict()},
                )
                continue
            state_error = _state_tool_input_error(
                source, authorization.resource, arguments
            )
            if state_error:
                reject(
                    index,
                    reference,
                    {"code": "tool_input_schema_invalid", "message": state_error},
                )
                continue
            prepared.append((index, reference, arguments, authorization))

    if diagnostics:
        return _bounded_observation(
            {
                "outcome": "rejected",
                "effect_started": False,
                "diagnostics": diagnostics,
                "notice": "No call in this batch was executed. Correct its inputs "
                "or use a single tool action for an effect or approval.",
            },
            "diagnostics",
            "diagnostic",
            limit=_MAX_OBSERVATION_CHARS,
        )

    results: list[dict[str, Any]] = []
    for index, reference, arguments, authorization in prepared:
        if not host._is_running(run_id):
            raise _RunAbandoned()

        def batch_emit(
            node_id: str | None,
            kind: str,
            payload: dict[str, Any],
            *,
            batch_index: int = index,
        ) -> None:
            emit(
                node_id,
                kind,
                {**payload, "batch_index": batch_index, "batch_size": size},
            )

        batch_emit(
            "tool",
            "tool.requested",
            {
                "tool_reference": reference,
                "authorization": authorization.decision,
                "decision_code": authorization.code,
                "turn": turn,
            },
        )
        previous_records = len(tool_calls)
        output = host._loop_run_tool(
            project_id,
            run_id,
            source,
            {"tool": reference, "arguments": arguments, "batch": True},
            batch_emit,
            tool_calls,
            approved=False,
            input_files=input_files,
        )
        if isinstance(output, _ExecutionPause):
            raise RuntimeError(
                "tool_batch_approval_required",
                "A tool batch cannot resume or authorize an approval request.",
            )
        raw_receipt = (
            getattr(tool_calls[-1], "receipt", None)
            if len(tool_calls) > previous_records
            else None
        )
        if not isinstance(raw_receipt, Mapping) or not raw_receipt:
            raise RuntimeError(
                "tool_batch_receipt_missing",
                "The Tool did not return an execution receipt",
            )
        receipt = raw_receipt
        failed = receipt.get("outcome") == "failed"
        results.append(
            {
                "index": index,
                "reference": reference,
                "status": "failed" if failed else "succeeded",
                **(
                    {"code": receipt["code"]}
                    if failed and isinstance(receipt.get("code"), str)
                    else {}
                ),
                "output": output,
            }
        )
    return _bounded_observation(
        {"outcome": "observed", "results": results},
        "results",
        "output",
        limit=_MAX_OBSERVATION_CHARS,
    )


def _bounded_observation(
    observation: dict[str, Any], collection: str, body: str, *, limit: int
) -> dict[str, Any]:
    def encoded(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    if len(encoded(observation)) <= limit:
        return observation
    entries = [dict(entry) for entry in observation[collection]]
    bounded = {**observation, collection: entries}
    skeleton = {**bounded, collection: [{**entry, body: None} for entry in entries]}
    share = max(0, (limit - len(encoded(skeleton))) // len(entries) - 240)
    for entry in entries:
        original = encoded(entry[body])
        if len(original) > share:
            entry[body] = {
                "truncated": True,
                "original_char_count": len(original),
                "excerpt": original[:share],
                "notice": "Prefix only; do not infer absence or complete coverage.",
            }
    # Escaped quotes can expand an excerpt; reduce bodies, never omit call metadata.
    while len(encoded(bounded)) > limit:
        candidates = [
            entry[body]
            for entry in entries
            if isinstance(entry[body], dict)
            and entry[body].get("truncated") is True
            and entry[body].get("excerpt")
        ]
        if not candidates:
            from .service import RuntimeError

            raise RuntimeError(
                "tool_batch_output_too_large", "Batch observation metadata is too large"
            )
        largest = max(candidates, key=lambda item: len(item["excerpt"]))
        largest["excerpt"] = largest["excerpt"][: len(largest["excerpt"]) // 2]
    return bounded
