from __future__ import annotations

from copy import deepcopy

import pytest

from tests.integration.local.test_factory_routes import VALID_SEMANTIC_PLAN
from tests.unit.local.test_semantic_plan_compiler import _empty_context, _step
from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.dataflow import (
    parse_data_edges,
    types_compatible,
)
from veyra_agent_platform.contracts.document import DocumentContent, DocumentTable
from veyra_agent_platform.contracts.semantic_plan import AgentSemanticPlanV1
from veyra_agent_platform.contracts.typed_io import (
    looks_like_collection_ref,
    parse_typed_field,
    value_matches_field,
)
from veyra_agent_platform.local.builder.quality import validate_agent_quality
from veyra_agent_platform.local.builder.semantic_compiler import compile_semantic_plan
from veyra_agent_platform.local.builder.simulation import simulate_agent
from veyra_agent_platform.local.runtime.dataflow import DataflowStore


def _plan(**changes: object) -> AgentSemanticPlanV1:
    payload = deepcopy(VALID_SEMANTIC_PLAN)
    payload.update(changes)
    return AgentSemanticPlanV1.from_dict(payload)


def test_types_compatible_promotes_pdf_and_rejects_image_to_string() -> None:
    image = parse_typed_field("image", "photo")
    text = parse_typed_field("string", "note")
    pdf = parse_typed_field("pdf", "pack")
    document = parse_typed_field("document", "doc")
    assert types_compatible(pdf, document)
    assert not types_compatible(image, text)


def test_collection_ref_matches_collection_field() -> None:
    field = parse_typed_field("collection", "folder")
    value = {
        "kind": "collection",
        "collection_id": "col_1",
        "items": [
            {
                "kind": "artifact",
                "artifact_id": "art_1",
                "media_type": "application/pdf",
                "filename": "a.pdf",
            }
        ],
    }
    assert looks_like_collection_ref(value)
    assert value_matches_field(field, value)
    with pytest.raises(ContractValidationError):
        parse_data_edges(
            [
                {
                    "source": {"kind": "run_input", "port": "folder"},
                    "target": {"kind": "run_input", "port": "folder"},
                }
            ]
        )


def test_document_content_keeps_xlsx_tables() -> None:
    content = DocumentContent(
        source_artifact_id="art_sheet",
        filename="book.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        text_blocks=(),
        tables=(
            DocumentTable(
                sheet="Sheet1",
                headers=("item", "qty"),
                rows=(("box", "2"),),
            ),
        ),
    )
    dumped = content.to_dict()
    assert dumped["tables"][0]["sheet"] == "Sheet1"
    assert "box" in content.plaintext()
    assert "art_sheet" in dumped["source_artifact_id"]


def test_duplicate_target_port_is_rejected() -> None:
    with pytest.raises(ContractValidationError, match="DUPLICATE_TARGET_PORT"):
        parse_data_edges(
            [
                {
                    "source": {"kind": "run_input", "port": "text"},
                    "target": {
                        "kind": "node",
                        "node_id": "analyze",
                        "port": "text",
                    },
                },
                {
                    "source": {"kind": "run_input", "port": "text"},
                    "target": {
                        "kind": "node",
                        "node_id": "analyze",
                        "port": "text",
                    },
                },
            ]
        )


def test_sequential_typed_model_flow_emits_data_edges() -> None:
    plan = _plan(
        goal="Analyze an image then write a summary.",
        suggested_name="Vision summary",
        description="Understand the photo and summarize it.",
        inputs=[
            {"name": "item_image", "type": "image"},
            {"name": "notes", "type": "string", "required": False},
        ],
        outputs=[{"name": "summary", "type": "object"}],
        steps=["analyze", "summarize"],
        step_intents=[
            {
                **_step(
                    "analyze_item",
                    "Analyze item",
                    "Describe the photographed item.",
                    "model",
                ),
                "inputs": [{"name": "item_image", "type": "image"}],
                "outputs": [{"name": "analysis", "type": "object"}],
            },
            {
                **_step(
                    "write_summary",
                    "Write summary",
                    "Turn the analysis into a summary object.",
                    "model",
                    depends_on=["analyze_item"],
                ),
                "inputs": [{"name": "analysis", "type": "object"}],
                "outputs": [{"name": "summary", "type": "object"}],
            },
        ],
    )
    compiled = compile_semantic_plan(plan, _empty_context())
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    graph = compiled.blueprint.to_dict()
    assert graph["data_edges"]
    targets = {
        (edge["target"]["kind"], edge["target"].get("node_id"), edge["target"]["port"])
        for edge in graph["data_edges"]
    }
    assert ("node", "analyze_item", "item-image") in targets or (
        "node",
        "analyze_item",
        "item_image",
    ) in {
        (edge["target"]["kind"], edge["target"].get("node_id"), edge["target"]["port"])
        for edge in graph["data_edges"]
    }
    quality = validate_agent_quality(compiled.blueprint)
    simulation = simulate_agent(compiled.blueprint)
    assert quality.verdict == "PASS", quality.diagnostics
    assert simulation.passed, simulation.diagnostics


def test_image_to_string_port_fails_closed() -> None:
    plan = _plan(
        inputs=[{"name": "photo", "type": "image"}],
        outputs=[{"name": "caption", "type": "string"}],
        steps=["caption"],
        step_intents=[
            {
                **_step("caption", "Caption", "Caption the photo as text.", "model"),
                "inputs": [{"name": "photo", "type": "string"}],
                "outputs": [{"name": "caption", "type": "string"}],
            }
        ],
    )
    compiled = compile_semantic_plan(plan, _empty_context())
    assert compiled.status == "compile_error"
    assert compiled.error is not None
    assert "DATAFLOW_TYPE_MISMATCH" in compiled.error or "MISSING_REQUIRED_INPUT" in (
        compiled.error
    )


def test_pdf_document_agent_compiles_and_simulates() -> None:
    plan = _plan(
        goal="Analyze a PDF.",
        suggested_name="PDF analyst",
        description="Read a PDF and return structured findings.",
        inputs=[{"name": "source", "type": "pdf"}],
        outputs=[{"name": "findings", "type": "object"}],
        steps=["analyze"],
        step_intents=[
            {
                **_step("analyze_pdf", "Analyze PDF", "Extract findings.", "model"),
                "inputs": [{"name": "source", "type": "pdf"}],
                "outputs": [{"name": "findings", "type": "object"}],
            }
        ],
    )
    compiled = compile_semantic_plan(plan, _empty_context())
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    assert simulate_agent(compiled.blueprint).passed


def test_spreadsheet_agent_compiles() -> None:
    plan = _plan(
        goal="Summarize a spreadsheet.",
        suggested_name="Sheet analyst",
        description="Read tabular data.",
        inputs=[{"name": "workbook", "type": "document"}],
        outputs=[{"name": "summary", "type": "object"}],
        steps=["analyze"],
        step_intents=[
            {
                **_step("analyze_sheet", "Analyze sheet", "Summarize tables.", "model"),
                "inputs": [{"name": "workbook", "type": "document"}],
                "outputs": [{"name": "summary", "type": "object"}],
            }
        ],
    )
    compiled = compile_semantic_plan(plan, _empty_context())
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    assert validate_agent_quality(compiled.blueprint).verdict == "PASS"


def test_approval_revision_and_image_generation_compile() -> None:
    plan = _plan(
        goal="Design packaging with approval and a preview image.",
        suggested_name="Packaging designer",
        description="Analyze an item, propose concepts, approve, then render.",
        inputs=[
            {"name": "item_image", "type": "image"},
            {"name": "item_description", "type": "string", "required": False},
            {"name": "occasion", "type": "string"},
            {"name": "recipient", "type": "string"},
            {"name": "budget", "type": "string", "required": False},
            {"name": "style_preferences", "type": "string", "required": False},
        ],
        outputs=[
            {"name": "final_design", "type": "object"},
            {"name": "preview", "type": "image"},
        ],
        steps=["analyze", "concepts", "approve", "finalize", "render"],
        step_intents=[
            {
                **_step(
                    "analyze_item",
                    "Analyze item",
                    "Understand the item image and context.",
                    "model",
                ),
                "inputs": [
                    {"name": "item_image", "type": "image"},
                    {"name": "item_description", "type": "string", "required": False},
                    {"name": "occasion", "type": "string"},
                    {"name": "recipient", "type": "string"},
                ],
                "outputs": [{"name": "analysis", "type": "object"}],
            },
            {
                **_step(
                    "generate_concepts",
                    "Generate concepts",
                    "Propose packaging concepts from the analysis.",
                    "model",
                    depends_on=["analyze_item"],
                ),
                "inputs": [{"name": "analysis", "type": "object"}],
                "outputs": [{"name": "concepts", "type": "array"}],
            },
            {
                **_step(
                    "review_concepts",
                    "Review concepts",
                    "Approve a packaging concept.",
                    "approval",
                    depends_on=["generate_concepts"],
                ),
            },
            {
                **_step(
                    "final_design",
                    "Final design",
                    "Produce the approved packaging design.",
                    "model",
                    depends_on=["review_concepts"],
                ),
                "branch_condition": "review_concepts",
                "branch_key": "approved",
                "inputs": [{"name": "concepts", "type": "array"}],
                "outputs": [{"name": "final_design", "type": "object"}],
            },
            {
                **_step(
                    "render_preview",
                    "Render preview",
                    "Generate the packaging preview image.",
                    "model",
                    depends_on=["final_design"],
                ),
                "branch_condition": "review_concepts",
                "branch_key": "approved",
                "inputs": [{"name": "final_design", "type": "object"}],
                "outputs": [{"name": "preview", "type": "image"}],
            },
            {
                **_step(
                    "revise_concepts",
                    "Revise concepts",
                    "Revise packaging concepts after rejection.",
                    "model",
                    depends_on=["review_concepts"],
                ),
                "branch_condition": "review_concepts",
                "branch_key": "rejected",
                "inputs": [{"name": "concepts", "type": "array"}],
                "outputs": [{"name": "concepts", "type": "array"}],
            },
            {
                **_step(
                    "review_round_two",
                    "Review round two",
                    "Approve the revised concepts.",
                    "approval",
                    depends_on=["revise_concepts"],
                ),
                "branch_condition": "review_concepts",
                "branch_key": "rejected",
            },
            {
                **_step(
                    "final_after_review",
                    "Final after second review",
                    "Produce the design after a second review.",
                    "model",
                    depends_on=["review_round_two"],
                ),
                "branch_condition": "review_concepts",
                "branch_key": "rejected",
                "inputs": [{"name": "concepts", "type": "array"}],
                "outputs": [{"name": "final_design", "type": "object"}],
            },
        ],
    )
    compiled = compile_semantic_plan(plan, _empty_context())
    assert compiled.status == "compiled", compiled.error
    assert compiled.blueprint is not None
    graph = compiled.blueprint.to_dict()
    kinds = [node["component_type"] for node in graph["nodes"]]
    assert kinds.count("HumanApproval") == 2
    assert any(node.get("model_ref") == "model.image" for node in graph["nodes"])
    quality = validate_agent_quality(compiled.blueprint)
    simulation = simulate_agent(compiled.blueprint)
    assert quality.verdict == "PASS", quality.diagnostics
    assert simulation.passed, simulation.diagnostics


def test_simple_summarizer_compiles() -> None:
    plan = _plan(
        goal="Summarize the source text.",
        suggested_name="Summarizer",
        description="Return a short summary.",
        inputs=[{"name": "text", "type": "string"}],
        outputs=[{"name": "summary", "type": "string"}],
        steps=["summarize"],
        step_intents=[
            {
                **_step("summarize", "Summarize", "Summarize the text.", "model"),
                "inputs": [{"name": "text", "type": "string"}],
                "outputs": [{"name": "summary", "type": "string"}],
            }
        ],
    )
    compiled = compile_semantic_plan(plan, _empty_context())
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    assert validate_agent_quality(compiled.blueprint).verdict == "PASS"
    assert simulate_agent(compiled.blueprint).passed
    # Existing Agents omit data_edges; they remain readable.
    from pathlib import Path

    fixture = Path(__file__).resolve().parents[3] / (
        "contracts/fixtures/valid/approval-gate.vagent.yaml"
    )
    import json

    payload = json.loads(fixture.read_text(encoding="utf-8"))
    source = AgentSource.from_dict(payload)
    assert source.data_edges == ()


def test_runtime_store_binds_exact_ports_and_hides_unconnected_values() -> None:
    plan = _plan(
        goal="Analyze an image then write a summary.",
        suggested_name="Vision summary",
        description="Understand the photo and summarize it.",
        inputs=[
            {"name": "item_image", "type": "image"},
            {"name": "notes", "type": "string", "required": False},
        ],
        outputs=[{"name": "summary", "type": "object"}],
        steps=["analyze", "summarize"],
        step_intents=[
            {
                **_step(
                    "analyze_item",
                    "Analyze item",
                    "Describe the photographed item.",
                    "model",
                ),
                "inputs": [{"name": "item_image", "type": "image"}],
                "outputs": [{"name": "analysis", "type": "object"}],
            },
            {
                **_step(
                    "write_summary",
                    "Write summary",
                    "Turn the analysis into a summary object.",
                    "model",
                    depends_on=["analyze_item"],
                ),
                "inputs": [{"name": "analysis", "type": "object"}],
                "outputs": [{"name": "summary", "type": "object"}],
            },
        ],
    )
    compiled = compile_semantic_plan(plan, _empty_context())
    assert compiled.blueprint is not None
    image = {
        "kind": "artifact",
        "artifact_id": "art_item",
        "media_type": "image/png",
        "filename": "item.png",
    }
    values = {"item-image": image, "notes": "keep this local"}
    store = DataflowStore.from_source(compiled.blueprint, values)
    analyze = next(
        node for node in compiled.blueprint.nodes if node.id == "analyze_item"
    )
    summary_node = next(
        node for node in compiled.blueprint.nodes if node.id == "write_summary"
    )
    first = store.context_for(analyze)
    assert first.resolved_inputs["item-image"] == image
    assert "notes" not in first.resolved_inputs
    store.record(analyze.id, {"analysis": {"material": "paper"}})
    second = store.context_for(summary_node)
    assert second.resolved_inputs["analysis"] == {"material": "paper"}
    assert "item-image" not in second.resolved_inputs
    assert "notes" not in second.resolved_inputs
    store.record(summary_node.id, {"summary": {"text": "done"}})
    outputs = store.run_outputs(compiled.blueprint.outputs)
    assert outputs["summary"] == {"text": "done"}
