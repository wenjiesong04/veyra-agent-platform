from __future__ import annotations

from veyra_agent_platform.local.builder.test_run import (
    classify_failure,
    explain_failure,
)


def test_waiting_is_not_classified_as_failure() -> None:
    assert classify_failure(status="waiting", failure_code="") == "none"
    assert "批准" in explain_failure(
        status="waiting", failure_code="", classification="none", locale="zh"
    )


def test_stop_maps_to_environment_not_operation_failure() -> None:
    assert (
        classify_failure(status="cancelled", failure_code="run_cancelled")
        == "environment"
    )
    assert classify_failure(status="interrupted", failure_code="") == "environment"


def test_runtime_rate_limit_is_environment_not_builder_profile() -> None:
    assert (
        classify_failure(status="failed", failure_code="runtime_rate_limited")
        == "environment"
    )
    text = explain_failure(
        status="failed",
        failure_code="runtime_rate_limited",
        classification="environment",
        locale="zh",
    )
    assert "Builder" in text
    assert "限流" in text


def test_permission_is_deterministic_repairable() -> None:
    assert (
        classify_failure(status="failed", failure_code="tool_permission_denied")
        == "repairable"
    )


def test_runtime_not_configured_is_user_action() -> None:
    assert (
        classify_failure(status="failed", failure_code="runtime_not_configured")
        == "user_action"
    )
    assert "运行模型" in explain_failure(
        status="failed",
        failure_code="runtime_not_configured",
        classification="user_action",
        locale="zh",
    )


def test_knowledge_stale_is_user_action() -> None:
    assert (
        classify_failure(status="failed", failure_code="knowledge_index_stale")
        == "user_action"
    )


def test_success_is_not_classified() -> None:
    assert classify_failure(status="unverified", failure_code="") == "none"
    assert classify_failure(status="verified", failure_code="") == "none"
