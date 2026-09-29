from veyra_agent_platform.local.builder.conversation_service import (
    _provisional_title,
    _title_is_provisional,
)


def test_provisional_title_extracts_first_clause_without_a_model() -> None:
    assert _provisional_title("创建一个中英文翻译 Agent。") == "中英文翻译 Agent"
    assert (
        _provisional_title("创建会议纪要整理 Agent，输入会议记录，输出摘要。")
        == "会议纪要整理 Agent"
    )
    assert _provisional_title("帮我生成礼物包装 Agent") == "礼物包装 Agent"
    assert "Chat" not in _provisional_title("帮我生成一个可以调用 GitHub 的 Agent。")


def test_provisional_title_rejects_raw_uuids() -> None:
    leaked = "01a0ca54-c517-787b-bd8d-d4034403f38c"
    assert _provisional_title(leaked) == "新对话"
    assert _title_is_provisional(leaked, "帮我生成翻译 Agent")


def test_provisional_title_does_not_claim_manual_titles() -> None:
    first = "创建一个中英文翻译 Agent。"
    assert _title_is_provisional("中英文翻译 Agent", first)
    assert _title_is_provisional("Chat", first)
    assert not _title_is_provisional("手工标题", first)
    assert not _title_is_provisional("中英文翻译助手", first)
