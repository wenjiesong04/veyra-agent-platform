"""Bounded arithmetic over decimal literals, without executing expression code."""

from __future__ import annotations

import ast
import math
import re
from decimal import Decimal, DecimalException, Inexact, localcontext
from fractions import Fraction

_MAX_EXPRESSION_LENGTH = 400
_MAX_AST_NODES = 64
_MAX_OPERATIONS = 32
_MAX_LITERAL_DIGITS = 32
_MAX_LITERAL_EXPONENT = 32
_MAX_FRACTION_DIGITS = 64
_MAX_MAGNITUDE = Fraction(10**32)
_MIN_NONZERO_MAGNITUDE = Fraction(1, 10**32)
_EXPRESSION_CHARACTERS = re.compile(r"[0-9eE+\-*/().\s]+\Z", flags=re.ASCII)
_DECIMAL_LITERAL = re.compile(
    r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z", flags=re.ASCII
)


class ArithmeticError(ValueError):
    """A safe user-facing expression or numeric-boundary failure."""


def calculate(expression: object) -> dict[str, str | int | float | bool]:
    """Return an exact decimal/rational string and a finite JSON numeric value."""

    if not isinstance(expression, str) or not expression.strip():
        raise ArithmeticError("A numeric expression is required")
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise ArithmeticError("Expression exceeds the 400-character limit")
    expression = expression.strip()
    if not _EXPRESSION_CHARACTERS.fullmatch(expression):
        raise ArithmeticError("Use only numbers, parentheses and + - * / operators")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise ArithmeticError("Expression syntax is invalid") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > _MAX_AST_NODES:
        raise ArithmeticError("Expression exceeds the 64-node complexity limit")
    allowed = (
        ast.Expression,
        ast.Constant,
        ast.BinOp,
        ast.UnaryOp,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.UAdd,
        ast.USub,
    )
    if any(not isinstance(node, allowed) for node in nodes):
        raise ArithmeticError("Use only numbers, parentheses and + - * / operators")
    operations = sum(isinstance(node, ast.BinOp | ast.UnaryOp) for node in nodes)
    if operations > _MAX_OPERATIONS:
        raise ArithmeticError("Expression exceeds the operation limit")
    value = _evaluate(tree.body, expression)
    exact, repeating = _exact_string(value)
    numeric: int | float = value.numerator if value.denominator == 1 else float(value)
    if not math.isfinite(numeric):
        raise ArithmeticError("Result cannot be represented as a finite JSON number")
    # The exact string remains authoritative when JSON floating-point rounding
    # changes even a terminating decimal with many significant digits.
    approximate = repeating or Fraction(Decimal(str(numeric))) != value
    return {
        "expression": expression,
        "value": numeric,
        "exact": exact,
        "approximate": approximate,
    }


def _evaluate(node: ast.AST, expression: str) -> Fraction:
    if isinstance(node, ast.Constant):
        literal = ast.get_source_segment(expression, node) or ""
        if type(node.value) not in {int, float} or not _DECIMAL_LITERAL.fullmatch(
            literal
        ):
            raise ArithmeticError("Only decimal numeric literals are supported")
        try:
            decimal = Decimal(literal)
        except DecimalException as exc:
            raise ArithmeticError("Numeric literal is invalid") from exc
        coefficient = decimal.as_tuple()
        if (
            not decimal.is_finite()
            or len(coefficient.digits) > _MAX_LITERAL_DIGITS
            or not isinstance(coefficient.exponent, int)
            or abs(coefficient.exponent) > _MAX_LITERAL_EXPONENT
        ):
            raise ArithmeticError(
                "Numeric literal exceeds precision or exponent limits"
            )
        return _bounded(Fraction(decimal))
    if isinstance(node, ast.UnaryOp):
        value = _evaluate(node.operand, expression)
        return _bounded(-value if isinstance(node.op, ast.USub) else value)
    if isinstance(node, ast.BinOp):
        left = _evaluate(node.left, expression)
        right = _evaluate(node.right, expression)
        if isinstance(node.op, ast.Add):
            result = left + right
        elif isinstance(node.op, ast.Sub):
            result = left - right
        elif isinstance(node.op, ast.Mult):
            result = left * right
        elif isinstance(node.op, ast.Div):
            if not right:
                raise ArithmeticError("Division by zero is not allowed")
            result = left / right
        else:
            raise ArithmeticError("Operator is not supported")
        return _bounded(result)
    raise ArithmeticError("Expression contains an unsupported value")


def _bounded(value: Fraction) -> Fraction:
    if (
        len(str(abs(value.numerator))) > _MAX_FRACTION_DIGITS
        or len(str(value.denominator)) > _MAX_FRACTION_DIGITS
        or abs(value) > _MAX_MAGNITUDE
        or (value and abs(value) < _MIN_NONZERO_MAGNITUDE)
    ):
        raise ArithmeticError("Intermediate or final result exceeds numeric limits")
    return value


def _exact_string(value: Fraction) -> tuple[str, bool]:
    denominator = value.denominator
    for factor in (2, 5):
        while denominator % factor == 0:
            denominator //= factor
    if denominator != 1:
        return f"{value.numerator}/{value.denominator}", True
    # A bounded denominator has at most 213 binary factors. Together with the
    # magnitude bound, 256 decimal digits suffice for every terminating result.
    with localcontext() as context:
        context.prec = 256
        context.Emin = -512
        context.Emax = 512
        context.traps[Inexact] = True
        try:
            decimal = Decimal(value.numerator) / Decimal(value.denominator)
        except DecimalException as exc:
            raise ArithmeticError("Result exceeds exact decimal precision") from exc
        exact = format(decimal, "f")
    if "." in exact:
        exact = exact.rstrip("0").rstrip(".")
    return exact, False
