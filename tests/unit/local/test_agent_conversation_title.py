from veyra_agent_platform.local.runtime.conversations import (
    _is_placeholder_title,
    _public_title,
)


def test_public_title_never_returns_a_raw_uuid() -> None:
    leaked = "01a0ca54-c517-787b-bd8d-d4034403f38c"
    assert _is_placeholder_title(leaked)
    assert _public_title(leaked) == "New conversation"
    assert _public_title(None) == "New conversation"
    assert _public_title(leaked, "Summarize this packaging photo") == (
        "Summarize this packaging photo"
    )
    assert _public_title("Packaging review") == "Packaging review"
