"""Resource Factory plans: classify a missing capability, never invent runtime code."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .common import (
    ContractValidationError,
    require_list,
    require_mapping,
    require_string,
)

FactoryStatus = Literal[
    "generatable",
    "requires_user_configuration",
    "requires_external_integration",
    "unsupported",
]
FactoryStrategyName = Literal[
    "skill_instruction",
    "http_tool_wrapper",
    "filesystem_tool_wrapper",
    "none",
]
FactoryRisk = Literal["low", "medium", "high"]

_STATUSES = set(FactoryStatus.__args__)  # type: ignore[attr-defined]
_STRATEGIES = set(FactoryStrategyName.__args__)  # type: ignore[attr-defined]
_RISKS = set(FactoryRisk.__args__)  # type: ignore[attr-defined]


@dataclass(frozen=True)
class ResourceFactoryStrategy:
    """Whether a missing capability can be generated as a safe Catalog resource."""

    can_generate: bool
    resource_kind: str | None
    generation_strategy: FactoryStrategyName
    reason: str
    risk_level: FactoryRisk
    status: FactoryStatus
    requirements: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_generate": self.can_generate,
            "resource_kind": self.resource_kind,
            "generation_strategy": self.generation_strategy,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "status": self.status,
            "requirements": list(self.requirements),
        }

    @classmethod
    def from_dict(cls, data: Any) -> ResourceFactoryStrategy:
        item = require_mapping(data, "resource factory strategy")
        status = require_string(item.get("status"), "status")
        strategy = require_string(
            item.get("generation_strategy"), "generation_strategy"
        )
        risk = require_string(item.get("risk_level"), "risk_level")
        if status not in _STATUSES:
            raise ContractValidationError("resource factory strategy.status is invalid")
        if strategy not in _STRATEGIES:
            raise ContractValidationError(
                "resource factory strategy.generation_strategy is invalid"
            )
        if risk not in _RISKS:
            raise ContractValidationError(
                "resource factory strategy.risk_level is invalid"
            )
        can_generate = item.get("can_generate", False)
        if not isinstance(can_generate, bool):
            raise ContractValidationError(
                "resource factory strategy.can_generate must be boolean"
            )
        kind = item.get("resource_kind")
        if kind is not None:
            kind = require_string(kind, "resource_kind")
        return cls(
            can_generate=can_generate,
            resource_kind=kind,
            generation_strategy=strategy,  # type: ignore[arg-type]
            reason=require_string(item.get("reason"), "reason"),
            risk_level=risk,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            requirements=_string_tuple(item.get("requirements") or [], "requirements"),
        )


@dataclass(frozen=True)
class ResourceFactoryPlan:
    """Persisted factory decision for one missing capability on a Proposal."""

    capability: str
    status: FactoryStatus
    strategy: FactoryStrategyName
    can_generate: bool
    reason: str
    risk_level: FactoryRisk
    resource_kind: str | None = None
    requirements: tuple[str, ...] = ()
    draft: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    published: dict[str, Any] | None = None
    snapshot_hash: str | None = None
    proposal_id: str | None = None
    operation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "capability": self.capability,
            "status": self.status,
            "strategy": self.strategy,
            "generation_strategy": self.strategy,
            "can_generate": self.can_generate,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "resource_kind": self.resource_kind,
            "requirements": list(self.requirements),
            "draft": self.draft,
            "validation": self.validation,
            "published": self.published,
            "snapshot_hash": self.snapshot_hash,
            "proposal_id": self.proposal_id,
            "operation_id": self.operation_id,
        }
        return payload

    @classmethod
    def from_dict(cls, data: Any) -> ResourceFactoryPlan:
        item = require_mapping(data, "resource factory plan")
        strategy_raw = item.get("strategy") or item.get("generation_strategy")
        strategy = ResourceFactoryStrategy.from_dict(
            {
                "can_generate": item.get("can_generate", False),
                "resource_kind": item.get("resource_kind"),
                "generation_strategy": strategy_raw,
                "reason": item.get("reason"),
                "risk_level": item.get("risk_level"),
                "status": item.get("status"),
                "requirements": item.get("requirements") or [],
            }
        )
        draft = item.get("draft")
        validation = item.get("validation")
        published = item.get("published")
        if draft is not None:
            draft = dict(require_mapping(draft, "draft"))
        if validation is not None:
            validation = dict(require_mapping(validation, "validation"))
        if published is not None:
            published = dict(require_mapping(published, "published"))
        snapshot = item.get("snapshot_hash")
        proposal_id = item.get("proposal_id")
        operation_id = item.get("operation_id")
        return cls(
            capability=require_string(item.get("capability"), "capability"),
            status=strategy.status,
            strategy=strategy.generation_strategy,
            can_generate=strategy.can_generate,
            reason=strategy.reason,
            risk_level=strategy.risk_level,
            resource_kind=strategy.resource_kind,
            requirements=strategy.requirements,
            draft=draft,
            validation=validation,
            published=published,
            snapshot_hash=require_string(snapshot, "snapshot_hash")
            if snapshot
            else None,
            proposal_id=require_string(proposal_id, "proposal_id")
            if proposal_id
            else None,
            operation_id=require_string(operation_id, "operation_id")
            if operation_id
            else None,
        )


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    items = require_list(value, field)
    return tuple(
        require_string(item, f"{field}[{index}]") for index, item in enumerate(items)
    )
