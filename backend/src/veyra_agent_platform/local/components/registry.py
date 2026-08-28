"""The closed built-in component registry exposed to Studio."""

from __future__ import annotations

from typing import Any


def component_registry() -> list[dict[str, Any]]:
    definitions: tuple[tuple[str, list[str], list[str], str], ...] = (
        ("Start", [], ["next"], "supported"),
        ("Agent", ["model_ref", "system_prompt"], ["next"], "runtime_not_configured"),
        ("Tool", ["uses"], ["next"], "runtime_not_supported"),
        ("Condition", ["expression"], ["true", "false"], "supported"),
        ("Transform", ["mapping"], ["next"], "supported"),
        (
            "HumanApproval",
            ["prompt"],
            ["approved", "rejected"],
            "runtime_not_supported",
        ),
        ("Verifier", ["checks"], ["passed", "failed"], "supported"),
        ("Output", ["output_name"], [], "supported"),
    )
    return [
        {
            "type": kind,
            "fields": fields,
            "output_ports": ports,
            "runtime_status": runtime,
        }
        for kind, fields, ports, runtime in definitions
    ]
