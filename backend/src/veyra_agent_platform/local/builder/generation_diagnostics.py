"""Public, actionable causes for server-owned generation failures."""

import json
import re
from collections.abc import Iterable

from .product_validation import TASK_UNCERTAINTY_PREFIX

_SECRET = re.compile(r"(?i)(bearer\s+\S+|sk-[A-Za-z0-9._-]+|moonshot-[A-Za-z0-9._-]+)")

_CAUSES: dict[str, tuple[str, str]] = {
    "persistent_state_not_represented": (
        "方案要求跨运行保存项目，但没有定义可执行的状态数据和身份契约。",
        "The plan needs saved project state but has no executable state contract.",
    ),
    "persistent_state_contract_not_compiled": (
        "已规划的项目状态未正确编译到 Agent，不能保证保存或恢复。",
        "The planned project state was not compiled into the Agent.",
    ),
    "human_interaction_not_represented": (
        "方案没有落地所需的追问或确认流程。",
        "The required questions or confirmations are missing from execution.",
    ),
    "task_requires_clarification": (
        "还有影响实现的需求或能力缺口未解决；需要保留问题并继续澄清。",
        "A requirement or capability gap needs clarification before execution.",
    ),
    "planner_repair_no_progress": (
        "自动修正没有改变失败方案，已停止重复调用；原始需求和诊断仍保留。",
        "Repair made no progress; repeated requests stopped with the request retained.",
    ),
    "planner_repair_budget_exhausted": (
        "生成预算已用完，方案仍未通过；这不是用户需求被拒绝。",
        "The generation budget ended before a valid plan was produced.",
    ),
}


def redact_generation_diagnostic(text: str) -> str:
    """Remove credential-shaped values from public generation diagnostics."""
    return _SECRET.sub("<redacted>", text)


def generation_feedback(
    diagnostics: Iterable[str], *, legacy_review_only: bool = False
) -> list[str]:
    feedback: list[str] = []
    for issue in diagnostics:
        if not isinstance(issue, str):
            continue
        if issue.startswith(TASK_UNCERTAINTY_PREFIX):
            # Product-fidelity uncertainty is not coverage-review feedback.
            continue
        if issue.startswith("coverage_gap: "):
            try:
                gap = json.loads(issue.removeprefix("coverage_gap: "))
            except (ValueError, TypeError):
                continue
            if (
                not isinstance(gap, dict)
                or set(gap) != {"requirement", "reason"}
                or not all(
                    isinstance(value, str) and value.strip() for value in gap.values()
                )
            ):
                continue
            text = f"{gap['reason']}\n{gap['requirement']}"
        elif (
            legacy_review_only
            and ": " in issue
            and not issue.startswith(("planner_", "coverage_review_invalid"))
        ):
            # A successful review-only receipt establishes the origin of these
            # historical unprefixed gaps; do not rewrite the immutable record.
            requirement, reason = issue.split(": ", 1)
            if not requirement.strip() or not reason.strip():
                continue
            text = f"{reason}\n{requirement}"
        else:
            continue
        feedback.append(redact_generation_diagnostic(text)[:1_000])
        if len(feedback) == 24:
            break
    return feedback


def generation_failure_facts(
    diagnostics: Iterable[str],
    blocked_reason: str,
    locale: str,
    *,
    legacy_review_only: bool = False,
) -> dict[str, str]:
    issues = tuple(issue for issue in diagnostics if isinstance(issue, str))
    feedback = generation_feedback(issues, legacy_review_only=legacy_review_only)
    if feedback:
        return {
            "validation_code": "coverage_review_incomplete",
            "validation_summary": (
                "方案审查发现未落实的需求："
                if locale == "zh"
                else "Review found a gap: "
            )
            + feedback[0],
            "blocked_reason": blocked_reason,
            "stage": "coverage_review",
        }
    # A concrete implementation defect outranks the budget that stopped repair.
    stopping_causes = {"planner_repair_no_progress", "planner_repair_budget_exhausted"}
    code = next(
        (
            key
            for key in _CAUSES
            if key not in stopping_causes
            and any(item.startswith(key) for item in issues)
        ),
        "",
    )
    if not code:
        code = next(
            (key for key in _CAUSES if any(item.startswith(key) for item in issues)), ""
        )
    if not code:
        return {}
    summary = _CAUSES[code][0 if locale == "zh" else 1]
    if code == "task_requires_clarification" and code in issues:
        detail = next(
            (
                issue.removeprefix(TASK_UNCERTAINTY_PREFIX).strip()
                for issue in issues
                if issue.startswith(TASK_UNCERTAINTY_PREFIX)
                and issue.removeprefix(TASK_UNCERTAINTY_PREFIX).strip()
            ),
            "",
        )
        if detail:
            summary = (
                "方案待解决项：" if locale == "zh" else "Unresolved plan item: "
            ) + redact_generation_diagnostic(detail)[:1_000]
    return {
        "validation_code": code,
        "validation_summary": summary,
        "blocked_reason": blocked_reason,
    }
