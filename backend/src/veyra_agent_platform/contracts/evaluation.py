"""Private, version-bound result checks; not an Agent execution policy."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .canonical import canonical_json
from .common import (
    ContractValidationError,
    freeze_json,
    require_keys,
    require_list,
    require_mapping,
    require_string,
    require_uuid7,
    thaw_json,
)

METHODS = frozenset(
    {"equals", "number_equals", "set_equals", "artifact_integrity", "human_review"}
)
BASELINE_KINDS = frozenset({"user", "fixture", "reference", "model"})


def exact_decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        raise ValueError("A finite decimal value is required")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("A finite decimal value is required") from exc
    if not parsed.is_finite():
        raise ValueError("A finite decimal value is required")
    return parsed


@dataclass(frozen=True)
class EvaluationCheck:
    id: str
    label: str
    required: bool
    path: tuple[str, ...]
    method: str
    expected: Any = None
    baseline: Any = None

    @classmethod
    def from_dict(cls, value: Any) -> EvaluationCheck:
        item = require_mapping(value, "evaluation check")
        require_keys(
            item,
            allowed={
                "id",
                "label",
                "required",
                "path",
                "method",
                "expected",
                "baseline",
            },
            required={"id", "label", "required", "path", "method"},
        )
        identifier = require_string(item["id"], "check.id")
        label = require_string(item["label"], "check.label")
        if (
            len(identifier) > 128
            or len(label) > 1000
            or not identifier.strip()
            or not label.strip()
        ):
            raise ContractValidationError("check identity or label is invalid")
        if type(item["required"]) is not bool:
            raise ContractValidationError("check.required must be boolean")
        path = tuple(require_list(item["path"], "check.path"))
        if (
            not path
            or len(path) > 64
            or any(not isinstance(part, str) for part in path)
            or path[0].startswith("$")
        ):
            raise ContractValidationError("check.path must select a public output")
        method = require_string(item["method"], "check.method")
        if method not in METHODS:
            raise ContractValidationError("unsupported evaluation method")
        expected = None
        baseline = None
        if method in {"equals", "number_equals", "set_equals"}:
            if "expected" not in item or "baseline" not in item:
                raise ContractValidationError(
                    "comparison requires expected and baseline"
                )
            expected = freeze_json(item["expected"])
            source = require_mapping(item["baseline"], "check.baseline")
            require_keys(
                source,
                allowed={"kind", "reference", "revision"},
                required={"kind", "reference", "revision"},
            )
            if require_string(source["kind"], "baseline.kind") not in BASELINE_KINDS:
                raise ContractValidationError("unsupported baseline provenance")
            for name in ("reference", "revision"):
                text = require_string(source[name], f"baseline.{name}")
                if len(text) > 2000 or not text.strip():
                    raise ContractValidationError("baseline metadata is too long")
            baseline = freeze_json(source)
            if method == "number_equals":
                if not isinstance(item["expected"], str):
                    raise ContractValidationError("decimal expected value must be text")
                try:
                    exact_decimal(item["expected"])
                except ValueError as exc:
                    raise ContractValidationError(str(exc)) from exc
            if method == "set_equals" and not isinstance(item["expected"], list):
                raise ContractValidationError("set expected value must be an array")
        elif "expected" in item or "baseline" in item:
            raise ContractValidationError("this method does not accept a baseline")
        return cls(
            identifier, label, item["required"], path, method, expected, baseline
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "label": self.label,
            "required": self.required,
            "path": list(self.path),
            "method": self.method,
        }
        if self.baseline is not None:
            result.update(
                expected=thaw_json(self.expected), baseline=thaw_json(self.baseline)
            )
        return result


@dataclass(frozen=True)
class EvaluationSpec:
    version_id: str
    checks: tuple[EvaluationCheck, ...]

    @classmethod
    def from_dict(cls, value: Any) -> EvaluationSpec:
        item = require_mapping(value, "evaluation spec")
        require_keys(
            item,
            allowed={"version", "version_id", "checks"},
            required={"version", "version_id", "checks"},
        )
        if item["version"] != "1":
            raise ContractValidationError("unsupported evaluation spec version")
        version_id = require_uuid7(item["version_id"], "evaluation.version_id")
        values = require_list(item["checks"], "evaluation.checks")
        if not 1 <= len(values) <= 128:
            raise ContractValidationError("evaluation requires 1..128 checks")
        if len(canonical_json(item)) > 131_072:
            raise ContractValidationError(
                "evaluation spec exceeds the local payload limit"
            )
        checks = tuple(EvaluationCheck.from_dict(entry) for entry in values)
        if len({check.id for check in checks}) != len(checks):
            raise ContractValidationError("evaluation check IDs must be unique")
        return cls(version_id, checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": "1",
            "version_id": self.version_id,
            "checks": [check.to_dict() for check in self.checks],
        }


@dataclass(frozen=True)
class EvaluationReview:
    expected_report_id: str
    version_id: str
    spec_hash: str
    result_hash: str
    decisions: tuple[dict[str, str], ...]

    @classmethod
    def from_dict(cls, value: Any) -> EvaluationReview:
        item = require_mapping(value, "evaluation review")
        names = {
            "expected_report_id",
            "version_id",
            "spec_hash",
            "result_hash",
            "decisions",
        }
        require_keys(item, allowed=names, required=names)
        for name in ("expected_report_id", "version_id"):
            require_uuid7(item[name], f"review.{name}")
        for name in ("spec_hash", "result_hash"):
            if not isinstance(item[name], str) or not re.fullmatch(
                r"[0-9a-f]{64}", item[name]
            ):
                raise ContractValidationError("review snapshot hash is invalid")
        decisions = []
        for raw in require_list(item["decisions"], "review.decisions"):
            decision = require_mapping(raw, "review decision")
            require_keys(
                decision,
                allowed={"check_id", "outcome", "reason"},
                required={"check_id", "outcome", "reason"},
            )
            check_id = require_string(decision["check_id"], "review.check_id")
            reason = require_string(decision["reason"], "review.reason").strip()
            outcome = require_string(decision["outcome"], "review.outcome")
            if (
                not check_id.strip()
                or len(check_id) > 128
                or not reason
                or len(reason) > 4000
                or outcome not in {"pass", "fail", "unknown"}
            ):
                raise ContractValidationError("review decision is invalid")
            decisions.append(
                {"check_id": check_id, "outcome": outcome, "reason": reason}
            )
        if not 1 <= len(decisions) <= 128 or len(
            {entry["check_id"] for entry in decisions}
        ) != len(decisions):
            raise ContractValidationError("review requires unique check decisions")
        if len(canonical_json(item)) > 262_144:
            raise ContractValidationError("review exceeds the local payload limit")
        return cls(
            item["expected_report_id"],
            item["version_id"],
            item["spec_hash"],
            item["result_hash"],
            tuple(decisions),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_report_id": self.expected_report_id,
            "version_id": self.version_id,
            "spec_hash": self.spec_hash,
            "result_hash": self.result_hash,
            "decisions": [dict(entry) for entry in self.decisions],
        }
