"""The bounded executable Condition expression and value-path contract."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from .common import ContractValidationError

ConditionOperator = Literal[
    "==", "!=", ">", ">=", "<", "<=", "contains", "not contains"
]

_SEGMENT = r"[a-z][a-z0-9_-]*"
_PATH = rf"{_SEGMENT}(?:\.(?:{_SEGMENT}|[0-9]+))*"
VALUE_PATH_RE = re.compile(rf"^{_PATH}$")
TEMPLATE_TOKEN_RE = re.compile(rf"\{{\{{\s*({_PATH})\s*\}}\}}")
_LITERAL = r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|true|false|-?[0-9]+(?:\.[0-9]+)?"
_EXPRESSION = re.compile(
    rf"^(?P<path>{_PATH})"
    r"(?:\s*(?P<symbol>==|!=|>=|<=|>|<)\s*|\s+(?P<word>not\s+contains|contains)\s+)"
    rf"(?P<literal>{_LITERAL})$"
)


def parse_value_path(text: str, *, field_name: str = "value path") -> tuple[str, ...]:
    """Parse ``name`` or ``node.field.0`` without evaluating anything."""

    candidate = text.strip()
    if not VALUE_PATH_RE.fullmatch(candidate):
        raise ContractValidationError(
            f"{field_name} must be a field or dotted path such as draft.summary"
        )
    return tuple(candidate.split("."))


def resolve_value_path(values: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    """Read a dotted path from run values. Missing segments raise KeyError."""

    current: Any = values
    for index, segment in enumerate(path):
        if isinstance(current, Mapping):
            if segment not in current:
                raise KeyError(".".join(path[: index + 1]))
            current = current[segment]
            continue
        if isinstance(current, list) and segment.isdigit():
            position = int(segment)
            if position >= len(current):
                raise KeyError(".".join(path[: index + 1]))
            current = current[position]
            continue
        raise KeyError(".".join(path[: index + 1]))
    return current


@dataclass(frozen=True)
class ConditionExpression:
    """One safe path-to-literal comparison."""

    field: str
    operator: ConditionOperator
    literal: str | bool | int | float
    literal_token: str

    @property
    def path(self) -> tuple[str, ...]:
        return tuple(self.field.split("."))

    @property
    def root(self) -> str:
        return self.path[0]

    def evaluate(self, values: Mapping[str, Any]) -> bool:
        actual = resolve_value_path(values, self.path)
        literal = self.literal
        if self.operator == "==":
            return _equal(actual, literal)
        if self.operator == "!=":
            return not _equal(actual, literal)
        if self.operator in {"contains", "not contains"}:
            found = _contains(actual, literal)
            return found if self.operator == "contains" else not found
        if not _is_number(actual) or not _is_number(literal):
            raise ValueError(f"{self.field} is not a number")
        if self.operator == ">":
            return bool(actual > literal)
        if self.operator == ">=":
            return bool(actual >= literal)
        if self.operator == "<":
            return bool(actual < literal)
        return bool(actual <= literal)

    def to_text(self) -> str:
        return f"{self.field} {self.operator} {self.literal_token}"


def parse_condition_expression(
    expression: Any, *, field_name: str = "condition.expression"
) -> ConditionExpression:
    """Parse the bounded comparison grammar; never evaluate code."""

    if not isinstance(expression, str):
        raise ContractValidationError(
            f"{field_name} must be a path compared with a literal"
        )
    match = _EXPRESSION.fullmatch(expression.strip())
    if match is None:
        raise ContractValidationError(
            f"{field_name} must compare a field or dotted path with ==, !=, >, "
            ">=, <, <=, contains, or not contains and a string, number, or "
            "boolean literal"
        )
    path = match.group("path")
    operator = match.group("symbol") or " ".join(match.group("word").split())
    raw = match.group("literal")
    literal = _literal(raw, field_name)
    if operator in {">", ">=", "<", "<="} and not _is_number(literal):
        raise ContractValidationError(
            f"{field_name} ordering comparisons need a number literal"
        )
    return ConditionExpression(
        field=path,
        operator=operator,  # type: ignore[arg-type]
        literal=literal,
        literal_token=raw,
    )


def _literal(raw: str, field_name: str) -> str | bool | int | float:
    if raw.startswith('"'):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ContractValidationError(
                f"{field_name} contains an invalid string literal"
            ) from exc
        return str(value)
    if raw.startswith("'"):
        return raw[1:-1]
    if raw == "true":
        return True
    if raw == "false":
        return False
    if "." in raw:
        return float(raw)
    return int(raw)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _equal(actual: Any, literal: Any) -> bool:
    if isinstance(actual, str) and isinstance(literal, str):
        return actual.strip() == literal
    if _is_number(actual) and _is_number(literal):
        return bool(actual == literal)
    return bool(actual == literal)


def _contains(actual: Any, literal: Any) -> bool:
    if isinstance(actual, str):
        return isinstance(literal, str) and literal in actual
    if isinstance(actual, list):
        return any(_equal(item, literal) for item in actual)
    if isinstance(actual, Mapping):
        return isinstance(literal, str) and literal in actual
    raise ValueError("contains needs text, a list, or an object")
