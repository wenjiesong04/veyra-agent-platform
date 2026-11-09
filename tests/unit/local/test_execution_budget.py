from types import SimpleNamespace

import pytest

from veyra_agent_platform.local.runtime.execution_budget import ModelTurnBudget


def test_initial_allowance_and_explicit_extension_preserve_consumed_turns() -> None:
    budget = ModelTurnBudget.restore(2, {})
    budget.consume()
    budget.consume()
    restored = ModelTurnBudget.restore(2, {"budget": budget.state()})
    restored.extend(4)
    assert restored.used == 2 and restored.limit == 6 and restored.remaining == 4
    assert restored.original_limit == 2


@pytest.mark.parametrize("additional", [True, 0, -1, 65, "4"])
def test_extension_never_implicitly_removes_host_policy(additional) -> None:
    budget = ModelTurnBudget.restore(2, {})
    with pytest.raises(ValueError):
        budget.extend(additional)
    assert budget.limit == 2


def test_total_policy_is_configurable_and_exposed_at_exhaustion() -> None:
    settings = SimpleNamespace(max_total_model_turns=3, max_additional_model_turns=2)
    budget = ModelTurnBudget.restore(2, {}, settings)
    budget.extend(1)
    budget.consume()
    context = budget.waiting_context(3, "pre_render")
    assert context["max_additional_turns"] == 0
    assert context["minimum_additional_turns"] == 1
    with pytest.raises(ValueError):
        budget.extend(1)


def test_legacy_approval_checkpoint_counts_its_already_requested_action() -> None:
    budget = ModelTurnBudget.restore(8, {"turn": 3, "pending_tool": {"tool": "x"}})
    assert budget.used == 4
    restored = ModelTurnBudget.restore(
        8, {"turn": 4, "budget": budget.state(), "pending_tool": {"tool": "x"}}
    )
    assert restored.used == 4
