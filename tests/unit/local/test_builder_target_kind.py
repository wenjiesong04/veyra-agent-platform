from __future__ import annotations

from veyra_agent_platform.local.builder.target_kind import classify_builder_target


def test_translation_assistant_is_an_agent_preference() -> None:
    result = classify_builder_target("创建一个翻译助手，把中文翻译成自然英语。")
    assert result.create_kind == "agent"
    assert result.user_requested_surface == "agent"


def test_research_assistant_is_an_agent_preference() -> None:
    result = classify_builder_target("创建一个研究助手，可以搜索网页并整理成报告。")
    assert result.create_kind == "agent"


def test_packaging_designer_wording_is_only_a_preference() -> None:
    result = classify_builder_target(
        "创建一个礼品包装设计助手。"
        "用户上传物品图片并告诉它场合、收礼人和风格。"
        "它可以分析图片、参考设计知识，并生成包装方案和包装效果图。"
    )
    assert result.create_kind == "agent"


def test_named_process_is_a_workflow_preference_not_a_lock() -> None:
    result = classify_builder_target(
        "创建一个商品包装设计流程。"
        "先让商品分析 Agent 分析上传的商品图片，"
        "再让市场研究 Agent 调研竞品，"
        "然后让包装设计 Agent 提出设计，"
        "我确认后再生成最终包装效果图。"
    )
    assert result.create_kind == "workflow"
    assert result.user_requested_surface == "workflow"


def test_daily_sales_wording_does_not_lock_shape() -> None:
    result = classify_builder_target(
        "每天先抓取销售数据，低于目标就通知负责人，"
        "高于目标就生成日报，日报必须由经理确认后再发送。"
    )
    assert result.create_kind == "agent"


def test_ambiguous_system_stays_a_preference() -> None:
    result = classify_builder_target("帮我做一个市场研究系统")
    assert result.create_kind == "agent"
