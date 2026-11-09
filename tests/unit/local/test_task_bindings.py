from copy import deepcopy

import pytest

from tests.unit.local.test_semantic_composition import REQUIREMENT, Planner, design_plan
from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.task_structure import TaskStructure
from veyra_agent_platform.local.builder.generate_product import generate_builder_product
from veyra_agent_platform.local.builder.task_bindings import resolve_declared_reference
from veyra_agent_platform.local.builder.task_planner import (
    normalize_task_structure,
    validate_task_structure,
)
from veyra_agent_platform.local.resources import ResourceCatalog


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("orders_csv", "orderscsv"),
        ("ORDERS-CSV", "orderscsv"),
        ("input.orders_csv", "orderscsv"),
        ("INPUTS.orders-csv", "orderscsv"),
        ("analyze_csv.report_text", "analyze_report"),
        ("ANALYZE-CSV.REPORT-TEXT", "analyze_report"),
    ],
)
def test_shared_declared_reference_resolution_uses_the_given_symbol_tables(
    reference: str,
    expected: str,
) -> None:
    assert (
        resolve_declared_reference(
            reference,
            task_inputs={"orders-csv": "orderscsv"},
            producer_outputs={"analyze_csv.report-text": "analyze_report"},
        )
        == expected
    )


@pytest.mark.parametrize(
    "reference",
    [
        "missing",
        "report_text",
        "input.missing",
        "future.report_text",
        "orders.csv",
        "./orders.csv",
        "reports/orders.csv",
        "/tmp/orders.csv",
        "input.orders_csv.0",
        "input[orders_csv]",
        "use the uploaded orders CSV",
    ],
)
def test_shared_resolution_does_not_guess_names_paths_or_bare_producer_outputs(
    reference: str,
) -> None:
    assert (
        resolve_declared_reference(
            reference,
            task_inputs={"orders-csv": "orderscsv"},
            producer_outputs={"analyze.report-text": "analyze_report"},
        )
        is None
    )


@pytest.mark.parametrize(
    ("inputs", "outputs"),
    [
        ({"orders_csv": "one", "orders-csv": "two"}, {}),
        ({}, {"analyze_stage.report_text": "one", "analyze-stage.report-text": "two"}),
    ],
)
def test_reference_aliases_of_distinct_declared_values_fail_closed(
    inputs: dict[str, str],
    outputs: dict[str, str],
) -> None:
    with pytest.raises(ContractValidationError, match="aliases collide"):
        resolve_declared_reference(
            "orders_csv", task_inputs=inputs, producer_outputs=outputs
        )


def test_repeated_alias_of_the_same_declared_value_is_not_ambiguous() -> None:
    assert (
        resolve_declared_reference(
            "orders_csv",
            task_inputs={"orders_csv": "orderscsv", "orders-csv": "orderscsv"},
            producer_outputs={},
        )
        == "orderscsv"
    )


@pytest.mark.parametrize(
    "reference",
    [
        "uploaded_image",
        "uploaded-image",
        "input.uploaded_image",
        "INPUTS.uploaded-image",
    ],
)
def test_declared_task_input_aliases_pass_both_early_validation_and_compilation(
    reference: str,
) -> None:
    payload = design_plan()
    payload["inputs"][0]["name"] = "uploaded_image"
    payload["stages"][0]["input_sources"]["image"] = reference
    validate_task_structure(normalize_task_structure(TaskStructure.from_dict(payload)))
    product = generate_builder_product(
        REQUIREMENT, ResourceCatalog(), planner_provider=Planner(payload)
    )
    assert product.status == "review", product.diagnostics
    assert product.orchestration is not None
    draft = next(
        node
        for node in product.orchestration.workflow["nodes"]
        if node["id"] == "draft"
    )
    assert draft["input_mapping"]["image"] == "uploadedimage"


def test_stage_and_output_aliases_refer_to_the_same_declared_producer() -> None:
    payload = design_plan()
    payload["stages"][0]["id"] = "draft_stage"
    payload["execution_boundaries"][0]["stage"] = "draft_stage"
    payload["actors"][0]["outputs"][0]["name"] = "review_options"
    payload["stages"][2]["input_sources"]["analysis"] = "DRAFT-STAGE.REVIEW-OPTIONS"
    validate_task_structure(normalize_task_structure(TaskStructure.from_dict(payload)))
    product = generate_builder_product(
        REQUIREMENT, ResourceCatalog(), planner_provider=Planner(payload)
    )
    assert product.status == "review", product.diagnostics
    assert product.orchestration is not None
    nodes = product.orchestration.workflow["nodes"]
    producer = next(node for node in nodes if node["id"] == "draft_stage")
    consumer = next(node for node in nodes if node["id"] == "render")
    assert (
        consumer["input_mapping"]["analysis"]
        == producer["output_mapping"]["review-options"]
    )


def test_invalid_source_reports_declared_inputs_and_available_producers() -> None:
    payload = design_plan()
    private_invalid_source = "use the private uploaded content here"
    payload["stages"][2]["input_sources"]["analysis"] = private_invalid_source
    with pytest.raises(ContractValidationError) as caught:
        validate_task_structure(
            normalize_task_structure(TaskStructure.from_dict(payload))
        )
    diagnostic = str(caught.value)
    assert "Stage render input analysis" in diagnostic
    assert "Declared task inputs: input.image" in diagnostic
    assert "draft.options" in diagnostic and "choose.selection" in diagnostic
    assert private_invalid_source not in diagnostic
    assert "render.result" not in diagnostic


def test_external_stage_without_declared_outputs_cannot_invent_a_port() -> None:
    payload = design_plan()
    payload["execution_boundaries"] = [
        boundary
        for boundary in payload["execution_boundaries"]
        if boundary["kind"] != "human_input"
    ]
    payload["stages"][2]["input_sources"]["analysis"] = "choose.undeclared"
    with pytest.raises(ContractValidationError, match="none declared"):
        validate_task_structure(
            normalize_task_structure(TaskStructure.from_dict(payload))
        )


@pytest.mark.parametrize(
    "reference", ["draft.unpublished", "render.result", "missing.result"]
)
def test_external_handoff_rejects_missing_or_future_ports_before_composition(
    reference: str,
) -> None:
    payload = design_plan()
    payload["stages"][2]["input_sources"]["analysis"] = reference
    structure = normalize_task_structure(TaskStructure.from_dict(payload))
    with pytest.raises(ContractValidationError, match="references"):
        validate_task_structure(structure)


def test_declared_human_reply_and_actor_outputs_pass_early_binding_checks() -> None:
    validate_task_structure(
        normalize_task_structure(TaskStructure.from_dict(design_plan()))
    )


def test_colliding_input_aliases_cannot_choose_an_arbitrary_field() -> None:
    payload = design_plan()
    payload["inputs"] += [{"name": "image_", "type": "image"}]
    # Existing normalization collapses these names; reject the ambiguity.
    structure = normalize_task_structure(TaskStructure.from_dict(payload))
    with pytest.raises(ContractValidationError, match="collide"):
        validate_task_structure(structure)


def test_same_loop_working_notes_remain_distinct_from_external_typed_ports() -> None:
    payload = deepcopy(design_plan())
    payload["user_shape_override"] = "PURE_AGENT"
    # This fixture needs a native question, not an independent verification step.
    payload["stages"][1]["actor"] = "planner"
    payload["execution_boundaries"] = [
        item
        for item in payload["execution_boundaries"]
        if item["kind"] != "verification"
    ]
    payload["stages"][2]["input_sources"]["analysis"] = "draft.working_note"
    validate_task_structure(normalize_task_structure(TaskStructure.from_dict(payload)))


def test_required_workflow_boundary_keeps_private_notes_out_of_external_ports() -> None:
    payload = deepcopy(design_plan())
    payload["user_shape_override"] = "PURE_AGENT"
    payload["stages"][2]["input_sources"]["analysis"] = "draft.working_note"
    with pytest.raises(ContractValidationError, match="undeclared output"):
        validate_task_structure(
            normalize_task_structure(TaskStructure.from_dict(payload))
        )
