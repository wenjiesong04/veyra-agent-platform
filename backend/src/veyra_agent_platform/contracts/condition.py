"""The bounded executable Condition expression and value-path contract."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from .common import ContractValidationError

ConditionOperator = Literal[
    "==", "!=", ">", ">=", "<", "<=", "contains", "not contains"
]
CONDITION_OPERATORS: tuple[ConditionOperator, ...] = (
    "==",
    "!=",
    ">",
    ">=",
    "<",
    "<=",
    "contains",
    "not contains",
)
CONDITION_GRAMMAR = (
    "a field or dotted path compared with ==, !=, >, >=, <, <=, contains, "
    "or not contains and a string, finite number, or boolean literal"
)
CONDITION_PLANNING_GUIDANCE = (
    "For a condition boundary, expression should be a typed predicate object "
    "with path, operator and literal, e.g. "
    '{"path":"review.ready","operator":"==","literal":true}. '
    "The path must identify an actual declared input or prior stage output; "
    "stage_id.output_port can have further object fields or list indices. "
    "HumanApproval approved/rejected outcomes are control ports, not data "
    "outputs; route those ports directly rather than adding a data condition. "
    "Veyra compiles the object deterministically to "
    + CONDITION_GRAMMAR
    + ". Ordering needs a number literal. A legacy string in this grammar is "
    "also accepted. Use exactly two branch labels, first for true and second "
    "for false. Keep explanations in reason/source, never in expression. "
    "Functions, compound predicates, variable-to-variable comparisons and "
    "natural-language classification are unsupported. If an AI decision is "
    "needed, declare the responsible actor's typed decision output first and "
    "compare that output; do not invent a classifier or replace the requested "
    "decision with true or a non-empty check. Retain unsupported decisions "
    "as required duties with explicit uncertainty. Non-condition boundaries "
    "use an empty expression."
)


class ConditionValidationError(ContractValidationError):
    """A value-free diagnostic that can safely survive bounded repair failure."""

    def __init__(
        self,
        code: str,
        location: str,
        *,
        operator: str | None = None,
        literal_type: str | None = None,
    ) -> None:
        self.details: dict[str, Any] = {
            "code": code,
            "location": location,
            "grammar": CONDITION_GRAMMAR,
        }
        if operator is not None:
            self.details["operator"] = (
                operator if operator in CONDITION_OPERATORS else "unsupported"
            )
        if literal_type is not None:
            self.details["literal_type"] = literal_type
        super().__init__(
            "Invalid condition: " + json.dumps(self.details, sort_keys=True)
        )


def condition_expression_schema(*, max_length: int = 240) -> dict[str, Any]:
    """Provider predicate shape; legacy strings share the same semantic parser."""
    return {
        "description": CONDITION_PLANNING_GUIDANCE,
        "anyOf": [
            {"type": "string", "maxLength": max_length},
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "path": {"type": "string", "maxLength": max_length},
                    "operator": {"type": "string", "enum": list(CONDITION_OPERATORS)},
                    "literal": {
                        "anyOf": [
                            {"type": "string", "maxLength": max_length},
                            {"type": "number"},
                            {"type": "boolean"},
                        ]
                    },
                },
                "required": ["path", "operator", "literal"],
            },
        ],
    }


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
_EXPRESSION_PREFIX = re.compile(
    rf"^{_PATH}"
    r"(?:\s*(?P<symbol>==|!=|>=|<=|>|<)\s*|\s+(?P<word>not\s+contains|contains)\s+)"
    r"(?P<literal>.*)$",
    re.DOTALL,
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

    def to_predicate(self) -> dict[str, Any]:
        return {"path": self.field, "operator": self.operator, "literal": self.literal}


def parse_condition_predicate(
    predicate: Any, *, field_name: str = "condition.expression"
) -> ConditionExpression:
    """Compile a closed typed predicate into the same AST as legacy expressions."""
    if not isinstance(predicate, Mapping) or set(predicate) != {
        "path",
        "operator",
        "literal",
    }:
        raise ConditionValidationError("predicate_shape_invalid", field_name)
    path = predicate["path"]
    if not isinstance(path, str) or not VALUE_PATH_RE.fullmatch(path):
        raise ConditionValidationError("predicate_path_invalid", field_name + ".path")
    operator = predicate["operator"]
    literal = predicate["literal"]
    if not isinstance(operator, str) or operator not in CONDITION_OPERATORS:
        raise ConditionValidationError(
            "predicate_operator_invalid",
            field_name + ".operator",
            operator="unsupported",
        )
    if not isinstance(literal, str | bool | int | float) or (
        isinstance(literal, float) and not math.isfinite(literal)
    ):
        raise ConditionValidationError(
            "predicate_literal_invalid",
            field_name + ".literal",
            operator=operator,
            literal_type=_literal_type(literal),
        )
    _validate_literal_operator(operator, literal, field_name)
    return ConditionExpression(
        field=path,
        operator=operator,  # type: ignore[arg-type]
        literal=literal,
        literal_token=_literal_token(literal),
    )


def parse_condition_expression(
    expression: Any, *, field_name: str = "condition.expression"
) -> ConditionExpression:
    """Parse the bounded comparison grammar; never evaluate code."""

    if not isinstance(expression, str):
        raise ConditionValidationError("expression_type_invalid", field_name)
    match = _EXPRESSION.fullmatch(expression.strip())
    if match is None:
        prefix = _EXPRESSION_PREFIX.fullmatch(expression.strip())
        operator = (
            prefix.group("symbol") or " ".join(prefix.group("word").split())
            if prefix is not None
            else "unsupported"
        )
        token = prefix.group("literal") if prefix is not None else ""
        literal_type = (
            "string"
            if token.startswith(('"', "'"))
            else "boolean"
            if token in {"true", "false"}
            else "number"
            if re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", token)
            else "unsupported"
        )
        raise ConditionValidationError(
            "expression_syntax_invalid",
            field_name,
            operator=operator,
            literal_type=literal_type,
        )
    path = match.group("path")
    operator = match.group("symbol") or " ".join(match.group("word").split())
    raw = match.group("literal")
    literal = _literal(raw, field_name)
    _validate_literal_operator(operator, literal, field_name)
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
            raise ConditionValidationError(
                "string_literal_invalid", field_name
            ) from exc
        return str(value)
    if raw.startswith("'"):
        return raw[1:-1]
    if raw == "true":
        return True
    if raw == "false":
        return False
    if "." in raw:
        value = float(raw)
        if not math.isfinite(value):
            raise ConditionValidationError(
                "predicate_literal_invalid", field_name, literal_type="number"
            )
        return value
    return int(raw)


def _validate_literal_operator(operator: str, literal: Any, field_name: str) -> None:
    if operator in {">", ">=", "<", "<="} and not _is_number(literal):
        raise ConditionValidationError(
            "ordering_requires_number",
            field_name,
            operator=operator,
            literal_type=_literal_type(literal),
        )


def _literal_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int | float):
        return "number"
    if value is None:
        return "null"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, list):
        return "array"
    return "unsupported"


def _literal_token(value: str | bool | int | float) -> str:
    if isinstance(value, float):
        # JSON may use exponent notation; the existing Source DSL does not.
        # Preserve the same finite number without widening that grammar.
        token = format(Decimal(str(value)), "f")
        return token if "." in token else token + ".0"
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


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
