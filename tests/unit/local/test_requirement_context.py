from __future__ import annotations

import pytest

from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.local.builder.requirement_context import (
    user_requirement_context,
)


def test_later_correction_can_restore_a_previously_changed_requirement() -> None:
    rows = [
        {"role": "user", "kind": "user", "content": "Use budget 500."},
        {"role": "assistant", "kind": "assistant", "content": "I assume budget 900."},
        {"role": "user", "kind": "user", "content": "Use budget 700."},
    ]
    context = user_requirement_context(rows, "Use budget 500.")
    assert context.count("Use budget 500.") == 2
    assert context.index("Use budget 500.") < context.index("Use budget 700.")
    assert context.rindex("Use budget 500.") > context.index("Use budget 700.")
    assert "I assume" not in context


def test_oversized_original_requirements_are_never_silently_truncated() -> None:
    rows = [
        {"role": "user", "kind": "user", "content": "a" * 60_000},
        {"role": "user", "kind": "user", "content": "b" * 60_000},
    ]
    with pytest.raises(ContractValidationError, match="requirement context exceeds"):
        user_requirement_context(rows, "Retry the same requirements.")
