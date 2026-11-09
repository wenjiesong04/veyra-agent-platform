from __future__ import annotations

from typing import Any

import pytest

from veyra_agent_platform.local.runtime.service import _check


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"design": "A festive package"}, True),
        (
            {
                "kind": "artifact",
                "artifact_id": "test-image",
                "media_type": "image/png",
                "filename": "render.png",
            },
            True,
        ),
        ([{"name": "Option A"}], True),
        ("Ready", True),
        (0, True),
        (False, True),
        (None, False),
        ("", False),
        ([], False),
    ],
)
def test_required_fields_accepts_json_values_without_hashing(
    value: Any, expected: bool
):
    assert _check("required_fields:result", {"result": value}) is expected


def test_required_fields_rejects_missing_field():
    assert _check("required_fields:result", {"another": "present"}) is False


def test_packaging_output_checks_accept_object_and_image_reference():
    outputs = {
        "result": {"design": "A festive package"},
        "render": {
            "kind": "artifact",
            "artifact_id": "test-image",
            "media_type": "image/png",
            "filename": "render.png",
        },
    }
    assert all(
        _check(check, outputs)
        for check in ["output.not_empty", "required_fields:result", "schema_valid"]
    )
