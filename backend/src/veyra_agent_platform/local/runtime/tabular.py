"""Bounded, exact CSV group comparison without business-specific conclusions."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, DecimalException, Inexact, localcontext
from fractions import Fraction
from typing import Any, cast

TABULAR_MAX_FILE_BYTES = 1_000_000
TABULAR_MAX_ROWS = 2_000
TABULAR_MAX_COLUMNS = 50
TABULAR_MAX_CELL_BYTES = 4_096
TABULAR_MAX_RESULT_GROUPS = 200
TABULAR_MAX_ROW_REFERENCES = 200
TABULAR_MAX_RESULT_BYTES = 500_000
TABULAR_DEFAULT_RESULT_BYTES = 7_500
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


class TabularError(ValueError):
    """Safe diagnostics never include input cell contents or host paths."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class _Group:
    amount: Fraction = Fraction(0)
    rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _Table:
    metadata: dict[str, Any]
    groups: dict[str, _Group]
    blanks: _Group
    total: Fraction


def compare_csv(
    left: bytes,
    right: bytes,
    *,
    left_path: str,
    right_path: str,
    left_key: object,
    right_key: object,
    left_amount: object,
    right_amount: object,
    include_all_groups: object = False,
) -> dict[str, Any]:
    """Compare every parsed record; detail truncation never truncates summaries."""
    if type(include_all_groups) is not bool:
        raise TabularError(
            "tabular_input_invalid", "Include all groups must be boolean"
        )
    first = _table(left, "Left", left_path, left_key, left_amount)
    second = _table(right, "Right", right_path, right_key, right_amount)
    counts = {
        "matched_groups": 0,
        "equal_groups": 0,
        "different_groups": 0,
        "left_only_groups": 0,
        "right_only_groups": 0,
        "left_matched_records": 0,
        "right_matched_records": 0,
        "left_only_records": 0,
        "right_only_records": 0,
        "left_blank_key_records": len(first.blanks.rows),
        "right_blank_key_records": len(second.blanks.rows),
    }
    sums = {
        name: Fraction(0)
        for name in ("left_matched", "right_matched", "left_only", "right_only")
    }
    details: list[dict[str, Any]] = []
    for key in sorted(first.groups.keys() | second.groups.keys()):
        left_group, right_group = first.groups.get(key), second.groups.get(key)
        if left_group is not None and right_group is not None:
            status = "equal" if left_group.amount == right_group.amount else "different"
            counts["matched_groups"] += 1
            counts[f"{status}_groups"] += 1
            for side, group in (("left", left_group), ("right", right_group)):
                counts[f"{side}_matched_records"] += len(group.rows)
                sums[f"{side}_matched"] += group.amount
        else:
            status = "left_only" if left_group is not None else "right_only"
            selected_group = left_group if left_group is not None else right_group
            assert selected_group is not None
            counts[f"{status}_groups"] += 1
            counts[f"{status}_records"] += len(selected_group.rows)
            sums[status] += selected_group.amount
        details.append(
            {
                "key": key,
                "status": status,
                "left_count": len(left_group.rows) if left_group else 0,
                "right_count": len(right_group.rows) if right_group else 0,
                "left_total": _exact(left_group.amount) if left_group else None,
                "right_total": _exact(right_group.amount) if right_group else None,
                "difference": _exact(right_group.amount - left_group.amount)
                if left_group and right_group
                else None,
                "left_rows": left_group.rows[:TABULAR_MAX_ROW_REFERENCES]
                if left_group
                else [],
                "right_rows": right_group.rows[:TABULAR_MAX_ROW_REFERENCES]
                if right_group
                else [],
                "left_rows_truncated": bool(
                    left_group and len(left_group.rows) > TABULAR_MAX_ROW_REFERENCES
                ),
                "right_rows_truncated": bool(
                    right_group and len(right_group.rows) > TABULAR_MAX_ROW_REFERENCES
                ),
            }
        )
    counts["left_unmatched_records"] = (
        counts["left_only_records"] + counts["left_blank_key_records"]
    )
    counts["right_unmatched_records"] = (
        counts["right_only_records"] + counts["right_blank_key_records"]
    )
    totals = {
        "left_all": first.total,
        "right_all": second.total,
        **sums,
        "left_blank_key": first.blanks.amount,
        "right_blank_key": second.blanks.amount,
        "left_unmatched": sums["left_only"] + first.blanks.amount,
        "right_unmatched": sums["right_only"] + second.blanks.amount,
        "matched_difference": sums["right_matched"] - sums["left_matched"],
        "right_matched_minus_left_all": sums["right_matched"] - first.total,
        "all_difference": second.total - first.total,
    }
    counts["multi_record_groups"] = sum(
        group["left_count"] > 1 or group["right_count"] > 1 for group in details
    )
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "left": first.metadata,
        "right": second.metadata,
        "counts": counts,
        "totals": {name: _exact(value) for name, value in totals.items()},
        "mismatch_groups": [],
        "mismatch_groups_truncated": False,
        "multi_record_groups": [],
        "multi_record_groups_truncated": False,
        "blank_keys": {"left": [], "right": []},
        "blank_keys_truncated": {"left": False, "right": False},
        "groups": [],
        "groups_requested": include_all_groups,
        "groups_truncated": False,
        "summary_complete": True,
        "truncated": False,
        "key_rule": "Exact text keys; blank keys remain unmatched.",
        "difference_rule": (
            "right minus left for matched keys; "
            "absent sides have null amounts and differences."
        ),
    }
    byte_limit = (
        TABULAR_MAX_RESULT_BYTES if include_all_groups else TABULAR_DEFAULT_RESULT_BYTES
    )
    if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > byte_limit:
        raise TabularError(
            "tabular_output_too_large",
            "CSV metadata exceeds the output limit; use shorter paths and column names",
        )
    # Show non-equal groups first without guessing their business meaning.
    details.sort(key=lambda group: (group["status"] == "equal", group["key"]))
    mismatches = [group for group in details if group["status"] != "equal"]
    multiple = [
        group
        for group in details
        if group["left_count"] > 1 or group["right_count"] > 1
    ]
    for collection_name, collection in (
        ("mismatch_groups", mismatches),
        ("multi_record_groups", multiple),
    ):
        for entry in collection[:TABULAR_MAX_RESULT_GROUPS]:
            if not _append_group(result, result[collection_name], entry, byte_limit):
                break
        result[f"{collection_name}_truncated"] = len(result[collection_name]) < len(
            collection
        ) or any(
            group["left_rows_truncated"] or group["right_rows_truncated"]
            for group in result[collection_name]
        )
        result["truncated"] |= result[f"{collection_name}_truncated"]
    for side, group in (("left", first.blanks), ("right", second.blanks)):
        for row in group.rows[:TABULAR_MAX_ROW_REFERENCES]:
            if not _append_detail(result, result["blank_keys"][side], row, byte_limit):
                break
        result["blank_keys_truncated"][side] = len(result["blank_keys"][side]) < len(
            group.rows
        )
        result["truncated"] |= result["blank_keys_truncated"][side]
    if include_all_groups:
        for entry in details[:TABULAR_MAX_RESULT_GROUPS]:
            if not _append_group(result, result["groups"], entry, byte_limit):
                break
        result["groups_truncated"] = len(result["groups"]) < len(details) or any(
            group["left_rows_truncated"] or group["right_rows_truncated"]
            for group in result["groups"]
        )
        result["truncated"] |= result["groups_truncated"]
    return result


def _append_group(
    result: dict[str, Any],
    target: list[dict[str, Any]],
    value: dict[str, Any],
    limit: int,
) -> bool:
    entry = {
        **value,
        "left_rows": list(value["left_rows"]),
        "right_rows": list(value["right_rows"]),
    }
    while not _append_detail(result, target, entry, limit):
        side = (
            "left" if len(entry["left_rows"]) >= len(entry["right_rows"]) else "right"
        )
        if not entry[f"{side}_rows"]:
            return False
        entry[f"{side}_rows"].pop()
        entry[f"{side}_rows_truncated"] = True
    return True


def _append_detail(
    result: dict[str, Any],
    target: list[dict[str, Any]],
    value: dict[str, Any],
    limit: int,
) -> bool:
    target.append(value)
    if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > limit:
        target.pop()
        result["truncated"] = True
        return False
    return True


def _table(content: bytes, side: str, path: str, key: object, amount: object) -> _Table:
    if not isinstance(content, bytes) or len(content) > TABULAR_MAX_FILE_BYTES:
        raise TabularError(
            "tabular_file_too_large", f"{side} CSV exceeds the 1 MB file limit"
        )
    for name in (key, amount):
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name.encode("utf-8")) > 256
        ):
            raise TabularError(
                "tabular_input_invalid",
                "Select exact nonblank key and amount column names",
            )
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TabularError(
            "tabular_csv_invalid", f"{side} CSV must use UTF-8 encoding"
        ) from exc
    _quotes(text, side)
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        headers = next(reader)
    except (StopIteration, csv.Error) as exc:
        raise TabularError(
            "tabular_csv_invalid", f"{side} CSV needs a valid header row"
        ) from exc
    if not 1 <= len(headers) <= TABULAR_MAX_COLUMNS or any(
        not header.strip() for header in headers
    ):
        raise TabularError(
            "tabular_csv_invalid", f"{side} CSV needs 1 to 50 nonblank column headers"
        )
    if len(set(headers)) != len(headers):
        raise TabularError(
            "tabular_csv_invalid", f"{side} CSV has duplicate column headers"
        )
    if any(len(header.encode("utf-8")) > 256 for header in headers):
        raise TabularError(
            "tabular_csv_invalid", f"{side} CSV header names exceed the 256-byte limit"
        )
    if key not in headers or amount not in headers:
        raise TabularError(
            "tabular_input_invalid",
            f"{side} CSV does not contain the selected key and amount columns",
        )
    key_index, amount_index = (
        headers.index(cast(str, key)),
        headers.index(cast(str, amount)),
    )
    groups: dict[str, _Group] = {}
    blanks = _Group()
    total = Fraction(0)
    record_count = 0
    header_end = reader.line_num
    previous_end = header_end
    try:
        for row in reader:
            start, end = previous_end + 1, reader.line_num
            previous_end = end
            if not row:
                continue
            record_count += 1
            if record_count > TABULAR_MAX_ROWS:
                raise TabularError(
                    "tabular_rows_exceeded", f"{side} CSV exceeds the 2000-record limit"
                )
            if len(row) != len(headers):
                raise TabularError(
                    "tabular_csv_invalid",
                    f"{side} CSV has a wrong column count at physical line {start}",
                )
            if any(len(cell.encode("utf-8")) > TABULAR_MAX_CELL_BYTES for cell in row):
                raise TabularError(
                    "tabular_cell_too_large",
                    f"{side} CSV exceeds the 4096-byte cell limit "
                    f"at physical line {start}",
                )
            value = _amount(row[amount_index], side, start)
            total += value
            identity = row[key_index]
            group = (
                groups.setdefault(identity, _Group()) if identity.strip() else blanks
            )
            group.amount += value
            group.rows.append(
                {"line_start": start, "line_end": end, "amount": _exact(value)}
            )
    except csv.Error as exc:
        raise TabularError("tabular_csv_invalid", f"{side} CSV is malformed") from exc
    metadata = {
        "path": path,
        "sha256": hashlib.sha256(content).hexdigest(),
        "byte_length": len(content),
        "column_count": len(headers),
        "key_column": key,
        "amount_column": amount,
        "header_line_start": 1,
        "header_line_end": header_end,
        "record_count": record_count,
        "group_count": len(groups),
        "blank_key_record_count": len(blanks.rows),
        "total": _exact(total),
        "keyed_total": _exact(total - blanks.amount),
        "blank_key_total": _exact(blanks.amount),
    }
    return _Table(metadata, groups, blanks, total)


def _quotes(text: str, side: str) -> None:
    """Reject malformed quotes that csv.reader otherwise accepts permissively."""
    if "\x00" in text:
        raise TabularError(
            "tabular_csv_invalid", f"{side} CSV contains a null character"
        )
    quoted, beginning, closed = False, True, False
    index = 0
    while index < len(text):
        character = text[index]
        if quoted:
            if character == '"':
                if index + 1 < len(text) and text[index + 1] == '"':
                    index += 1
                else:
                    quoted, closed = False, True
        elif closed:
            if character not in ",\r\n":
                raise TabularError(
                    "tabular_csv_invalid", f"{side} CSV has malformed quoting"
                )
            closed, beginning = False, True
        elif character == '"':
            if not beginning:
                raise TabularError(
                    "tabular_csv_invalid", f"{side} CSV has malformed quoting"
                )
            quoted, beginning = True, False
        elif character in ",\r\n":
            beginning = True
        else:
            beginning = False
        index += 1
    if quoted:
        raise TabularError(
            "tabular_csv_invalid", f"{side} CSV has an unterminated quoted field"
        )


def _amount(text: str, side: str, line: int) -> Fraction:
    literal = text.strip()
    if not _DECIMAL.fullmatch(literal):
        raise TabularError(
            "tabular_amount_invalid",
            f"{side} CSV needs a finite decimal amount at physical line {line}",
        )
    try:
        decimal = Decimal(literal)
    except DecimalException as exc:
        raise TabularError(
            "tabular_amount_invalid",
            f"{side} CSV has an invalid decimal at physical line {line}",
        ) from exc
    coefficient = decimal.as_tuple()
    if (
        not decimal.is_finite()
        or len(coefficient.digits) > 32
        or not isinstance(coefficient.exponent, int)
        or abs(coefficient.exponent) > 32
    ):
        raise TabularError(
            "tabular_amount_invalid",
            f"{side} CSV exceeds decimal precision or exponent limits "
            f"at physical line {line}",
        )
    return Fraction(decimal)


def _exact(value: Fraction) -> str:
    # All operands are finite decimal literals, so all sums terminate exactly.
    with localcontext() as context:
        context.prec = 256
        context.Emin, context.Emax = -512, 512
        context.traps[Inexact] = True
        exact = format(Decimal(value.numerator) / Decimal(value.denominator), "f")
    return exact.rstrip("0").rstrip(".") if "." in exact else exact
