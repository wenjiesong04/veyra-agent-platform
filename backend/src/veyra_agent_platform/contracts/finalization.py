"""Opt-in delivery checks for an autonomous Agent, without a second graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .common import (
    ContractValidationError,
    require_keys,
    require_list,
    require_mapping,
    require_string,
)
from .verification import parse_verifier_check


@dataclass(frozen=True)
class FinalizationContract:
    checks: tuple[str, ...] = ()
    criteria: tuple[str, ...] = ()
    review_images: bool = False
    advisory_criteria: tuple[str, ...] = ()
    pre_render_review: bool = False
    review_strategy: Literal["direct", "evidence_first"] = "direct"
    evidence_inputs: tuple[str, ...] = ()

    @property
    def review_criteria(self) -> tuple[str, ...]:
        return (*self.criteria, *self.advisory_criteria)

    @classmethod
    def from_dict(cls, value: Any) -> FinalizationContract:
        item = require_mapping(value, "finalization")
        require_keys(
            item,
            allowed={
                "version",
                "checks",
                "criteria",
                "review_images",
                "advisory_criteria",
                "pre_render_review",
                "review_strategy",
                "evidence_inputs",
            },
            required={"version", "checks", "criteria", "review_images"},
        )
        if item["version"] != "1":
            raise ContractValidationError("unsupported finalization version")
        strategy = item.get("review_strategy", "direct")
        if strategy not in ("direct", "evidence_first"):
            raise ContractValidationError("unsupported finalization.review_strategy")
        evidence_inputs = tuple(
            require_string(entry, "finalization.evidence_inputs")
            for entry in require_list(
                item.get("evidence_inputs", []), "finalization.evidence_inputs"
            )
        )
        if len(set(evidence_inputs)) != len(evidence_inputs):
            raise ContractValidationError("finalization.evidence_inputs has duplicates")
        if (strategy == "evidence_first") != bool(evidence_inputs):
            raise ContractValidationError(
                "evidence_first requires explicitly selected evidence_inputs"
            )
        if not isinstance(item["review_images"], bool):
            raise ContractValidationError("finalization.review_images must be boolean")
        pre_render = item.get("pre_render_review", False)
        if not isinstance(pre_render, bool) or (
            pre_render and not item["review_images"]
        ):
            raise ContractValidationError("pre_render_review requires image review")
        parsed: dict[str, tuple[str, ...]] = {}
        for name in ("checks", "criteria", "advisory_criteria"):
            values = tuple(
                require_string(entry, f"finalization.{name}")
                for entry in require_list(item.get(name, []), f"finalization.{name}")
            )
            if len(set(values)) != len(values):
                raise ContractValidationError(f"finalization.{name} has duplicates")
            parsed[name] = values
        if set(parsed["criteria"]) & set(parsed["advisory_criteria"]):
            raise ContractValidationError(
                "a criterion cannot be both required and advisory"
            )
        if not any(parsed.values()):
            raise ContractValidationError("finalization requires checks or criteria")
        if strategy == "evidence_first" and not parsed["criteria"]:
            raise ContractValidationError("evidence_first requires review criteria")
        if item["review_images"] and not (
            parsed["criteria"] or parsed["advisory_criteria"]
        ):
            raise ContractValidationError("image review requires explicit criteria")
        try:
            for check in parsed["checks"]:
                parse_verifier_check(check)
        except ValueError as exc:
            raise ContractValidationError(str(exc)) from exc
        return cls(
            **parsed,
            review_images=item["review_images"],
            pre_render_review=pre_render,
            review_strategy=strategy,
            evidence_inputs=evidence_inputs,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "version": "1",
            "checks": list(self.checks),
            "criteria": list(self.criteria),
            "review_images": self.review_images,
        }
        if self.advisory_criteria:
            result["advisory_criteria"] = list(self.advisory_criteria)
        if self.pre_render_review:
            result["pre_render_review"] = True
        if self.review_strategy != "direct":
            result["review_strategy"] = self.review_strategy
            result["evidence_inputs"] = list(self.evidence_inputs)
        return result
