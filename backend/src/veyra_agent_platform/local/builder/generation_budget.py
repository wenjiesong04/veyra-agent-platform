"""One durable admission budget for all Model requests in a Builder operation."""

import json

from veyra_agent_platform.contracts.common import ContractValidationError


class GenerationBudgetExceeded(ContractValidationError):
    code = "factory_generation_budget_exhausted"
    repair_exhausted = True

    def __init__(self, phase: str, used: int, limit: int | None) -> None:
        super().__init__(
            "Generation budget ended; the original requirements are retained"
        )
        self.safe_repair_diagnostic = "planner_repair_budget_exhausted: " + json.dumps(
            {
                "phase": phase,
                "repairs": used,
                "limit": limit,
                "issue": "generation_budget",
                "locations": [],
            },
            sort_keys=True,
        )


class GenerationRefinementNotAllowed(ContractValidationError):
    code = "factory_generation_refinement_not_allowed"
    repair_exhausted = True
    safe_repair_diagnostic = "saved_plan_requires_refinement"

    def __init__(self) -> None:
        super().__init__(
            "The saved plan requires a repair; this operation permits review only"
        )
