"""Canonical BuilderOperation event kinds. Server-owned, not UI timers."""

from __future__ import annotations

from typing import Final

OPERATION_STARTED = "builder.operation.started"
INTENT_STARTED = "builder.intent.started"
INTENT_RESOLVED = "builder.intent.resolved"
SPECIFICATION_STARTED = "builder.specification.started"
SPECIFICATION_COMPLETED = "builder.specification.completed"
SEMANTIC_PLAN_STARTED = "builder.semantic_plan.started"
SEMANTIC_PLAN_COMPLETED = "builder.semantic_plan.completed"
CAPABILITIES_STARTED = "builder.capabilities.started"
CAPABILITIES_RESOLVED = "builder.capabilities.resolved"
COMPILE_STARTED = "builder.compile.started"
COMPILE_COMPLETED = "builder.compile.completed"
VALIDATION_STARTED = "builder.validation.started"
VALIDATION_COMPLETED = "builder.validation.completed"
COMPONENT_DESIGN_STARTED = "builder.component_design.started"
COMPONENT_DESIGN_COMPLETED = "builder.component_design.completed"
COMPONENT_CREATED = "builder.component.created"
PROPOSAL_READY = "builder.proposal.ready"
PROPOSAL_CONFIRMED = "builder.proposal.confirmed"
PROPOSAL_REJECTED = "builder.proposal.rejected"
APPLY_STARTED = "builder.apply.started"
APPLY_COMPLETED = "builder.apply.completed"
TEST_STARTED = "builder.test_run.started"
TEST_WAITING_APPROVAL = "builder.test_run.waiting_approval"
TEST_COMPLETED = "builder.test_run.completed"
TEST_FAILED = "builder.test_run.failed"
TEST_STOPPED = "builder.test_run.stopped"
OPERATION_COMPLETED = "builder.operation.completed"
OPERATION_FAILED = "builder.operation.failed"

EVENT_KINDS: Final[frozenset[str]] = frozenset(
    {
        OPERATION_STARTED,
        INTENT_STARTED,
        INTENT_RESOLVED,
        SPECIFICATION_STARTED,
        SPECIFICATION_COMPLETED,
        SEMANTIC_PLAN_STARTED,
        SEMANTIC_PLAN_COMPLETED,
        CAPABILITIES_STARTED,
        CAPABILITIES_RESOLVED,
        COMPILE_STARTED,
        COMPILE_COMPLETED,
        VALIDATION_STARTED,
        VALIDATION_COMPLETED,
        COMPONENT_DESIGN_STARTED,
        COMPONENT_DESIGN_COMPLETED,
        COMPONENT_CREATED,
        PROPOSAL_READY,
        PROPOSAL_CONFIRMED,
        PROPOSAL_REJECTED,
        APPLY_STARTED,
        APPLY_COMPLETED,
        TEST_STARTED,
        TEST_WAITING_APPROVAL,
        TEST_COMPLETED,
        TEST_FAILED,
        TEST_STOPPED,
        OPERATION_COMPLETED,
        OPERATION_FAILED,
    }
)

TERMINAL_EVENT_KINDS: Final[frozenset[str]] = frozenset(
    {OPERATION_COMPLETED, OPERATION_FAILED, PROPOSAL_REJECTED}
)

_LABELS: Final[dict[str, tuple[str, str]]] = {
    OPERATION_STARTED: ("开始构建", "Started"),
    INTENT_STARTED: ("理解需求", "Understanding request"),
    INTENT_RESOLVED: ("理解需求", "Understanding request"),
    SPECIFICATION_STARTED: ("整理规格", "Specifying Agent"),
    SPECIFICATION_COMPLETED: ("整理规格", "Specifying Agent"),
    SEMANTIC_PLAN_STARTED: ("生成方案", "Planning Agent"),
    SEMANTIC_PLAN_COMPLETED: ("生成方案", "Planning Agent"),
    CAPABILITIES_STARTED: ("解析资源", "Resolving capabilities"),
    CAPABILITIES_RESOLVED: ("解析资源", "Resolving capabilities"),
    COMPILE_STARTED: ("编译 Agent", "Compiling Agent"),
    COMPILE_COMPLETED: ("编译 Agent", "Compiling Agent"),
    VALIDATION_STARTED: ("验证结构", "Validating"),
    VALIDATION_COMPLETED: ("验证结构", "Validating"),
    COMPONENT_DESIGN_STARTED: ("设计可复用组件", "Designing reusable component"),
    COMPONENT_DESIGN_COMPLETED: ("组件方案已就绪", "Component plan ready"),
    COMPONENT_CREATED: ("组件已发布", "Component published"),
    PROPOSAL_READY: ("等待确认", "Preparing review"),
    PROPOSAL_CONFIRMED: ("用户确认", "Confirmed"),
    PROPOSAL_REJECTED: ("已拒绝", "Rejected"),
    APPLY_STARTED: ("创建 Draft", "Creating Draft"),
    APPLY_COMPLETED: ("创建 Draft", "Creating Draft"),
    TEST_STARTED: ("测试 Agent", "Testing Agent"),
    TEST_WAITING_APPROVAL: ("等待批准", "Waiting for approval"),
    TEST_COMPLETED: ("测试成功", "Test succeeded"),
    TEST_FAILED: ("测试失败", "Test failed"),
    TEST_STOPPED: ("测试已停止", "Test stopped"),
    OPERATION_COMPLETED: ("完成", "Completed"),
    OPERATION_FAILED: ("失败", "Failed"),
}


def event_label(kind: str, *, locale: str = "en") -> str:
    pair = _LABELS.get(kind, ("工作阶段", "Work stage"))
    return pair[0] if locale == "zh" else pair[1]


def is_terminal_event(kind: str) -> bool:
    return kind in TERMINAL_EVENT_KINDS
