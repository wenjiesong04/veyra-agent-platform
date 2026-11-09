"""Bounded Builder observation of a Runtime Run.

Builder stores only run_id plus a derived summary. Runtime remains the
canonical store for events, tool receipts, Knowledge evidence, and approvals.

Builder Model (Factory / Kimi) is never the Agent Runtime Model.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal

from veyra_agent_platform.local.runtime.service import RuntimeService

Classification = Literal[
    "none",
    "repairable",
    "user_action",
    "environment",
    "semantic",
]
RepairCode = Literal["permission_denied", "lock_mismatch", "lock_missing"]

REPAIRABLE_CODES: dict[str, RepairCode] = {
    "tool_permission_denied": "permission_denied",
    "permission_denied": "permission_denied",
    "resource_lock_mismatch": "lock_mismatch",
    "knowledge_lock_mismatch": "lock_mismatch",
    "lock_mismatch": "lock_mismatch",
    "lock_missing": "lock_missing",
}
USER_ACTION_CODES = frozenset(
    {
        "runtime_not_configured",
        "resource_unbound",
        "secret_not_configured",
        "tool_unavailable",
        "tool_not_registered",
        "tool_not_executable",
        "knowledge_index_stale",
        "knowledge_not_indexed",
        "knowledge_index_invalid",
        "project_binding_stale",
    }
)
ENVIRONMENT_CODES = frozenset(
    {
        "runtime_rate_limited",
        "runtime_timeout",
        "runtime_unavailable",
        "runtime_provider_error",
        "runtime_invalid_response",
        "run_cancelled",
    }
)
_SUCCESS = frozenset({"verified", "unverified"})
_STOPPED = frozenset({"cancelled", "interrupted"})


def observe_run(
    runtime: RuntimeService,
    project_id: str,
    agent_id: str,
    run_id: str,
    *,
    locale: Literal["zh", "en"] = "en",
    repair_proposal_id: str | None = None,
) -> dict[str, Any]:
    """Project a Runtime run_detail into a Builder-safe observation."""

    detail = runtime.run_detail(project_id, agent_id, run_id)
    if detail["project_id"] != project_id or detail["agent_id"] != agent_id:
        raise ValueError("run does not belong to this Project Agent")
    readiness = runtime.readiness(project_id, agent_id)
    model: Mapping[str, Any] = (
        readiness["model"] if isinstance(readiness.get("model"), dict) else {}
    )
    events = list(detail.get("events") or [])
    raw_error = detail.get("error")
    error = raw_error if isinstance(raw_error, dict) else None
    status = str(detail.get("status") or "")
    failure_code = str(error.get("code") or "") if error else ""
    failed_node = _last_failed_node(events)
    tool_failure = _tool_failure(events, failure_code)
    knowledge_failure = _knowledge_failure(events, failure_code)
    classification = classify_failure(
        status=status,
        failure_code=failure_code,
    )
    return {
        "run_id": run_id,
        "agent_id": agent_id,
        "version_id": str(detail.get("version_id") or ""),
        "status": status,
        "runtime_model_id": str(model.get("model_id") or ""),
        "runtime_model_source": str(readiness.get("profile_source") or "host"),
        "output_summary": _output_summary(detail.get("result")),
        "failure_code": failure_code or None,
        "failed_node": failed_node,
        "tool_failure": tool_failure,
        "knowledge_failure": knowledge_failure,
        "approval_required": status == "waiting",
        "duration_ms": _duration_ms(
            detail.get("created_at"), detail.get("finished_at")
        ),
        "evidence_count": _evidence_count(events),
        "classification": classification,
        "explanation": explain_failure(
            status=status,
            failure_code=failure_code,
            classification=classification,
            locale=locale,
        ),
        "repair_proposal_id": repair_proposal_id,
        "repair_code": REPAIRABLE_CODES.get(failure_code),
        "repair_reference": tool_failure
        if classification == "repairable" and tool_failure
        else knowledge_failure,
        "next_action": _next_action(classification, failure_code, status),
    }


def classify_failure(*, status: str, failure_code: str) -> Classification:
    if status in _SUCCESS or not failure_code:
        if status == "waiting":
            return "none"
        if status in _STOPPED:
            return "environment"
        return "none"
    if failure_code in REPAIRABLE_CODES:
        return "repairable"
    if failure_code in USER_ACTION_CODES:
        return "user_action"
    if failure_code in ENVIRONMENT_CODES or failure_code.startswith("runtime_"):
        return "environment"
    return "semantic"


def explain_failure(
    *,
    status: str,
    failure_code: str,
    classification: Classification,
    locale: Literal["zh", "en"],
) -> str:
    zh = locale == "zh"
    if status == "waiting":
        return "等待人工批准。" if zh else "Waiting for approval."
    if status in _STOPPED:
        return "测试已停止。" if zh else "The test run was stopped."
    if status in _SUCCESS:
        return "测试成功。" if zh else "The test run succeeded."
    return _EXPLANATIONS.get(failure_code, _EXPLANATIONS["unknown"])[0 if zh else 1]


def not_configured_observation(
    *,
    agent_id: str,
    locale: Literal["zh", "en"],
    runtime_model_id: str,
    runtime_model_source: str,
) -> dict[str, Any]:
    return {
        "run_id": "",
        "agent_id": agent_id,
        "version_id": "",
        "status": "failed",
        "runtime_model_id": runtime_model_id,
        "runtime_model_source": runtime_model_source,
        "output_summary": None,
        "failure_code": "runtime_not_configured",
        "failed_node": None,
        "tool_failure": None,
        "knowledge_failure": None,
        "approval_required": False,
        "duration_ms": None,
        "evidence_count": 0,
        "classification": "user_action",
        "explanation": explain_failure(
            status="failed",
            failure_code="runtime_not_configured",
            classification="user_action",
            locale=locale,
        ),
        "repair_proposal_id": None,
        "repair_code": None,
        "repair_reference": None,
        "next_action": "open_runtime_settings",
    }


def public_observation(payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    return {
        "run_id": str(payload.get("run_id") or "") or None,
        "agent_id": str(payload.get("agent_id") or ""),
        "version_id": str(payload.get("version_id") or "") or None,
        "status": str(payload.get("status") or ""),
        "runtime_model_id": str(payload.get("runtime_model_id") or ""),
        "runtime_model_source": str(payload.get("runtime_model_source") or ""),
        "output_summary": payload.get("output_summary"),
        "failure_code": payload.get("failure_code"),
        "failed_node": payload.get("failed_node"),
        "tool_failure": payload.get("tool_failure"),
        "knowledge_failure": payload.get("knowledge_failure"),
        "approval_required": bool(payload.get("approval_required")),
        "duration_ms": payload.get("duration_ms"),
        "evidence_count": int(payload.get("evidence_count") or 0),
        "classification": str(payload.get("classification") or "none"),
        "explanation": str(payload.get("explanation") or ""),
        "repair_proposal_id": payload.get("repair_proposal_id"),
        "repair_code": payload.get("repair_code"),
        "next_action": payload.get("next_action"),
    }


def _next_action(
    classification: Classification, failure_code: str, status: str
) -> str | None:
    if failure_code == "runtime_not_configured":
        return "open_runtime_settings"
    if status == "waiting":
        return "approve_or_reject"
    if classification == "repairable":
        return "create_repair_proposal"
    if classification == "environment":
        return "retry_later"
    return None


def _last_failed_node(events: Sequence[Mapping[str, Any]]) -> str | None:
    for event in reversed(events):
        if event.get("kind") in {"node.failed", "tool.failed"}:
            node = event.get("node_id")
            if isinstance(node, str) and node:
                return node
    return None


def _event_payload(event: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _tool_failure(events: Sequence[Mapping[str, Any]], failure_code: str) -> str | None:
    for event in reversed(events):
        if event.get("kind") != "tool.failed":
            continue
        payload = _event_payload(event)
        reference = payload.get("tool_reference") or payload.get("uses")
        if isinstance(reference, str) and reference:
            return reference
    if failure_code in REPAIRABLE_CODES:
        for event in reversed(events):
            payload = _event_payload(event)
            reference = payload.get("tool_reference") or payload.get("uses")
            if (
                isinstance(reference, str)
                and reference
                and reference != "knowledge.context"
            ):
                return reference
    return None


def _knowledge_failure(
    events: Sequence[Mapping[str, Any]], failure_code: str
) -> str | None:
    if "knowledge" not in failure_code:
        return None
    for event in reversed(events):
        payload = _event_payload(event)
        refs = payload.get("references")
        if isinstance(refs, list) and refs and isinstance(refs[0], str):
            return str(refs[0])
        reference = payload.get("tool_reference")
        if reference == "knowledge.context":
            return str(reference)
    return failure_code


def _evidence_count(events: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for event in events:
        payload = _event_payload(event)
        receipts = payload.get("receipts")
        if isinstance(receipts, list):
            total += len(receipts)
        elif event.get("kind") in {"tool.completed", "tool.failed"}:
            total += 1
    return total


def _output_summary(result: object) -> str | None:
    if not isinstance(result, dict) or not result:
        return None
    if len(result) == 1:
        value = next(iter(result.values()))
        if isinstance(value, str):
            return value[:500]
    encoded = json.dumps(result, ensure_ascii=False)
    return encoded[:500]


def _duration_ms(started: object, finished: object) -> int | None:
    if not isinstance(started, str) or not isinstance(finished, str):
        return None
    try:
        start = datetime.fromisoformat(started.replace("Z", "+00:00"))
        end = datetime.fromisoformat(finished.replace("Z", "+00:00"))
    except ValueError:
        return None
    delta = int((end - start).total_seconds() * 1000)
    return max(delta, 0)


_EXPLANATIONS: dict[str, tuple[str, str]] = {
    "runtime_not_configured": (
        "Agent 结构已经有效，但还没有配置运行模型。"
        "Veyra Builder 的 Kimi 不会自动成为这个 Agent 的 Runtime。",
        "The Agent structure is valid, but no Runtime model is configured. "
        "Veyra's Builder Kimi is not this Agent's Runtime model.",
    ),
    "tool_permission_denied": (
        "Agent 尝试使用一项工具或读取项目文件，但当前运行权限不允许这项操作。",
        "The Agent tried to use a tool or read project files, "
        "but the current run permissions do not allow it.",
    ),
    "permission_denied": (
        "Agent 尝试使用一项工具或读取项目文件，但当前运行权限不允许这项操作。",
        "The Agent tried to use a tool or read project files, "
        "but the current run permissions do not allow it.",
    ),
    "resource_unbound": (
        "Agent 引用的资源尚未绑定到这个 Project。需要先在资源库中绑定。",
        "A resource this Agent uses is not bound to this Project yet.",
    ),
    "resource_lock_mismatch": (
        "Agent 锁定的资源哈希与当前 Project pin 不一致。",
        "The Agent lock does not match the current Project resource pin.",
    ),
    "knowledge_lock_mismatch": (
        "Knowledge 绑定后内容已变化，需要显式重新绑定。",
        "Knowledge changed after binding and must be rebound explicitly.",
    ),
    "knowledge_index_stale": (
        "Knowledge 索引已过期。请先重建索引，再手动重新测试。",
        "The Knowledge index is stale. Rebuild it, then run the test again.",
    ),
    "knowledge_index_invalid": (
        "Knowledge 索引损坏，无法在运行时检索。",
        "The Knowledge index is invalid, so Runtime cannot retrieve it.",
    ),
    "knowledge_not_indexed": (
        "Knowledge 尚未建立索引，无法在运行时检索。",
        "Knowledge has not been indexed, so Runtime cannot retrieve it.",
    ),
    "project_binding_stale": (
        "Project 资源绑定已过期，需要显式重新绑定。",
        "The Project resource binding is stale and must be rebound explicitly.",
    ),
    "secret_not_configured": (
        "这项资源还缺少主机凭据。请在资源库中配置，不要把 Builder 密钥绑给 Agent。",
        "This resource still needs a host credential. "
        "Configure it in the Resource Library.",
    ),
    "runtime_rate_limited": (
        "Agent Runtime 模型当前被限流。这不是 Builder 能力问题，请稍后再手动重试。",
        "The Agent Runtime model is rate limited. "
        "This is not a Builder profile failure. Retry later.",
    ),
    "runtime_timeout": (
        "Agent Runtime 模型请求超时。请稍后再手动重试。",
        "The Agent Runtime model timed out. Retry later.",
    ),
    "runtime_unavailable": (
        "Agent Runtime 模型服务不可用。请稍后再手动重试。",
        "The Agent Runtime model service is unavailable. Retry later.",
    ),
    "run_cancelled": (
        "测试已停止。",
        "The test run was stopped.",
    ),
    "unknown": (
        "测试失败。打开运行详情查看 Runtime 证据。",
        "The test run failed. Open the run detail to inspect Runtime evidence.",
    ),
}
