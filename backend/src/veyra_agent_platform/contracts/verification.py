"""The shared executable check language used by Workflow and Agent delivery."""

from __future__ import annotations

import re

from .condition import parse_condition_expression


def parse_verifier_check(check: str) -> tuple[str, str]:
    if check in {"output.not_empty", "schema_valid"}:
        return check, ""
    kind, separator, argument = check.partition(":")
    if (
        separator
        and kind in {"required_fields", "artifact_exists"}
        and re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)?", argument)
    ):
        return kind, argument
    if separator and kind == "constraint_match":
        parse_condition_expression(argument)
        return kind, argument
    raise ValueError(f"unsupported verifier check: {check}")
