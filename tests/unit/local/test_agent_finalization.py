from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.unit.local.test_agent_autonomy_planning import _stateful_agent
from tests.unit.local.test_agent_loop_runtime import (
    _HarnessHost,
    _ScriptedLoopModel,
    _tool_loop_source,
)
from tests.unit.local.test_gated_role_composition import _Planner
from veyra_agent_platform.contracts.agent import AgentSource, ComponentType, FlowNode
from veyra_agent_platform.contracts.canonical import behavior_hash, source_hash
from veyra_agent_platform.contracts.common import ContractValidationError, new_uuid7
from veyra_agent_platform.contracts.finalization import FinalizationContract
from veyra_agent_platform.contracts.task_structure import (
    ExecutionBoundary,
    StateRequirement,
    TaskIOField,
)
from veyra_agent_platform.contracts.typed_io import parse_typed_fields
from veyra_agent_platform.contracts.wire import RunEvent
from veyra_agent_platform.local.builder.generate_product import generate_builder_product
from veyra_agent_platform.local.builder.product_shape import decide_product_shape
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.client import (
    GeneratedImage,
    RuntimeProviderError,
)
from veyra_agent_platform.local.runtime.finalization import (
    candidate_review_prompt,
    parse_candidate_review,
    review_observations,
)
from veyra_agent_platform.local.runtime.model_capabilities import (
    RuntimeModelCapabilities,
)
from veyra_agent_platform.local.runtime.native_images import (
    image_node_id,
    render_image_requests,
)
from veyra_agent_platform.local.runtime.service import (
    RuntimeError,
    RuntimeService,
    _agent_user_content,
    _RunAbandoned,
)


def _source(*, images: bool = False, max_turns: int = 8) -> AgentSource:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    payload = _tool_loop_source(tool).to_dict()
    payload["outputs"] = {"result": "object"}
    if images:
        payload["outputs"].update(
            {
                "front": {"type": "artifact", "artifact_kind": "image"},
                "side": {"type": "artifact", "artifact_kind": "image"},
            }
        )
    for node in payload["nodes"]:
        if node["component_type"] == "Output":
            node["output_name"] = "result"
    payload["extensions"]["veyra"].update(
        max_turns=max_turns,
        finalization={
            "version": "1",
            "checks": ["required_fields:result"],
            "criteria": ["The candidate matches the supplied facts"],
            "review_images": images,
            **({"pre_render_review": True} if images else {}),
        },
    )
    return AgentSource.from_dict(payload)


def _review(status: str, *, images: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "findings": [
            {
                "criterion": 0,
                "status": status,
                "reason": "Public evidence-based feedback",
                "evidence": "The supplied candidate and observations",
            }
        ],
        "question": "What is the measured dimension?"
        if status == "needs_input"
        else "",
        "invalidate_images": images or [],
    }


def _final(value: Any) -> dict[str, Any]:
    return {"action": "final", "outputs": {"result": value}}


class _Host(_HarnessHost):
    def __init__(self, path: Path) -> None:
        super().__init__(
            path, ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
        )
        self.rendered: list[str] = []
        self.running = True
        self.media_fields: list[str] = []

    def _is_running(self, run_id):
        return self.running

    def _model_user_content(
        self, project_id, source, values, capabilities, *, fields=None, image_limit=8
    ):
        if fields:
            self.media_fields.extend(fields)
        return [
            {"type": "text", "text": json.dumps(values)},
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,fixture"},
            },
        ]

    def _run_image_model(self, project_id, run_id, node, source, values, emit):
        name = next(iter(node.outputs))
        self.rendered.append(name)
        return {
            name: {
                "kind": "artifact",
                "artifact_id": f"fixture-{len(self.rendered)}",
                "media_type": "image/png",
            }
        }


def test_rejected_candidate_revises_in_same_run_before_output(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    model = _ScriptedLoopModel(
        _final({"cost": 200}), _review("revise"), _final({"cost": 100}), _review("pass")
    )
    result = host._execute_loop("project", "run", _source(), {"budget": 100}, model)
    assert result.result == {"result": {"cost": 100}}
    assert len(model.calls) == 4
    assert [kind for _, kind, _ in host.events].count("finalization.rejected") == 1
    assert (
        sum(
            node == "output" and kind == "node.completed"
            for node, kind, _ in host.events
        )
        == 1
    )
    assert "Read-only delivery feedback" in model.calls[2][-1]["content"]
    assert "permitted tools" not in model.calls[1][0]["content"].lower()
    assert not result.verified
    assert not host.effects


def test_no_findings_preserves_input_roles_and_finishes_without_padding(
    tmp_path: Path,
) -> None:
    payload = _source().to_dict()
    payload["inputs"] = {
        "material": {"type": "string", "description": "Original evidence"},
        "analysis": {
            "type": "string",
            "description": "Upstream claims to check, not original evidence",
        },
    }
    payload["outputs"] = {
        "result": "string",
        "findings": {
            "type": "array",
            "description": "Actual defects only; may be empty when none are found",
        },
    }
    payload["extensions"]["veyra"]["finalization"].update(
        checks=[
            "output.not_empty",
            "required_fields:result",
        ],
        criteria=["Report supported conclusions and actual defects, if any"],
    )
    source = AgentSource.from_dict(payload)
    before = source.source_hash
    outputs = {
        "result": "No defects found; the conditional claim is supported.",
        "findings": [],
    }
    model = _ScriptedLoopModel({"action": "final", "outputs": outputs}, _review("pass"))
    host = _Host(tmp_path)
    outcome = host._execute_loop(
        "project",
        "run",
        source,
        {
            "material": "A depends on B.",
            "analysis": "If B is absent, A cannot proceed.",
        },
        model,
    )

    assert outcome.result == outputs and outcome.pause is None
    assert len(model.calls) == 2 and not host.effects
    evidence = json.loads(model.calls[1][1]["content"])
    assert evidence["input_contract"]["material"]["description"] == "Original evidence"
    assert evidence["input_contract"]["analysis"]["description"].startswith(
        "Upstream claims"
    )
    assert evidence["output_contract"]["findings"]["description"].startswith(
        "Actual defects only"
    )
    assert evidence["candidate"]["findings"] == []
    assert "A depends on B." in json.dumps(evidence["observations"])
    assert "If B is absent, A cannot proceed." in json.dumps(evidence["observations"])
    assert not any(kind == "finalization.rejected" for _, kind, _ in host.events)
    assert source.source_hash == before


@pytest.mark.parametrize("phase", ["pre_render", "candidate", "images"])
def test_review_policy_checks_inference_premises_without_forcing_defects(phase) -> None:
    prompt = candidate_review_prompt(_source().finalization, phase=phase)
    assert "original evidence from an upstream analysis" in prompt
    assert "word 'if' alone does not establish missing necessary premises" in prompt
    assert "Accept supported conditional inferences" in prompt
    assert "without inventing defects" in prompt


def test_missing_facts_pause_and_resume_without_new_run(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    source = _source()
    model = _ScriptedLoopModel(_final({"dimension": "unknown"}), _review("needs_input"))
    paused = host._execute_loop("project", "run", source, {}, model)
    assert paused.result is None and paused.pause is not None
    assert paused.pause.prompt == "What is the measured dimension?"
    resumed = _ScriptedLoopModel(_final({"dimension": 10}), _review("pass"))
    inputs = {**paused.pause.values, "$agent_reply": "10 cm"}
    result = host._execute_loop("project", "run", source, inputs, resumed)
    assert result.result == {"result": {"dimension": 10}}
    assert any(message.get("content") == "10 cm" for message in resumed.calls[0])


def test_budget_does_not_publish_unreviewed_candidate(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    model = _ScriptedLoopModel(_final({"value": 1}))
    outcome = host._execute_loop("project", "run", _source(max_turns=1), {}, model)
    assert outcome.pause is not None and outcome.pause.details["kind"] == "budget"
    assert outcome.pause.values["$agent_loop"]["pending_action"]["outputs"] == {
        "result": {"value": 1}
    }
    assert len(model.calls) == 1 and not host.rendered
    assert not any(node == "output" for node, _, _ in host.events)


def test_deterministic_failure_revises_without_calling_reviewer(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    source = replace(
        _source(),
        finalization=FinalizationContract(
            checks=("constraint_match:result.total <= 100",)
        ),
    )
    model = _ScriptedLoopModel(_final({"total": 200}), _final({"total": 100}))
    result = host._execute_loop("project", "run", source, {}, model)
    assert result.result == {"result": {"total": 100}}
    assert len(model.calls) == 2
    assert not any(kind == "finalization.started" for _, kind, _ in host.events)


@pytest.mark.parametrize("timeout", [False, True])
def test_advisory_review_budget_or_provider_error_does_not_block_delivery(
    tmp_path: Path, timeout: bool
) -> None:
    host = _Host(tmp_path)
    source = replace(
        _source(max_turns=2 if timeout else 1),
        finalization=FinalizationContract(
            checks=("required_fields:result",), advisory_criteria=("Visual preference",)
        ),
    )

    class Model(_ScriptedLoopModel):
        def complete_review(self, messages):
            raise RuntimeProviderError("runtime_timeout", "Synthetic advisory timeout")

    model = Model(_final({"style": "blue"}))
    result = host._execute_loop("project", "run", source, {}, model)
    assert result.result == {"result": {"style": "blue"}}
    accepted = next(
        payload for _, kind, payload in host.events if kind == "finalization.accepted"
    )
    assert accepted["advisory_unverified"] == 1
    assert accepted["evidence_kind"] == "deterministic"
    assert accepted["independent_verification"] is False


def test_repeated_candidate_and_feedback_stop_without_publishing(
    tmp_path: Path,
) -> None:
    host = _Host(tmp_path)
    model = _ScriptedLoopModel(
        _final({"bad": True}),
        _review("revise"),
        _final({"bad": True}),
        _review("revise"),
    )
    with pytest.raises(RuntimeError) as failure:
        host._execute_loop("project", "run", _source(), {}, model)
    assert failure.value.code == "agent_finalization_no_progress"
    assert len(model.calls) == 4
    assert not any(node == "output" for node, _, _ in host.events)


def test_uncertain_evidence_allows_replanning_but_is_not_a_pass(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    model = _ScriptedLoopModel(
        _final({"protection": "untested"}),
        _review("uncertain"),
        _final({"protection": "untested"}),
        _review("uncertain"),
    )
    with pytest.raises(RuntimeError) as failure:
        host._execute_loop("project", "run", _source(), {}, model)
    assert failure.value.code == "agent_finalization_uncertain"
    assert len(model.calls) == 4


def test_images_are_reviewed_and_only_invalidated_view_is_regenerated(
    tmp_path: Path,
) -> None:
    host = _Host(tmp_path)
    candidate = _final({"style": "consistent"})
    model = _ScriptedLoopModel(
        candidate,
        _review("pass"),
        _review("revise", images=["front"]),
        candidate,
        _review("pass"),
        _review("pass"),
    )
    result = host._execute_loop("project", "run", _source(images=True), {}, model)
    assert host.rendered == ["front", "side", "front"]
    assert result.result["front"]["artifact_id"] == "fixture-3"
    assert result.result["side"]["artifact_id"] == "fixture-2"
    assert {"front", "side"} <= set(host.media_fields)
    assert any(part["type"] == "image_url" for part in model.calls[2][1]["content"])


def test_semantic_defects_prevent_paid_image_rendering(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    model = _ScriptedLoopModel(
        _final({"bad": True}),
        _review("uncertain"),
        _final({"bad": True}),
        _review("uncertain"),
    )
    with pytest.raises(RuntimeError):
        host._execute_loop("project", "run", _source(images=True), {}, model)
    assert not host.rendered


def test_cancel_during_review_prevents_output(tmp_path: Path) -> None:
    host = _Host(tmp_path)

    class _CancelModel(_ScriptedLoopModel):
        def complete(self, messages):
            result = super().complete(messages)
            if len(self.calls) == 2:
                host.running = False
            return result

    model = _CancelModel(_final({"good": True}), _review("pass"))
    with pytest.raises(_RunAbandoned):
        host._execute_loop("project", "run", _source(), {}, model)
    assert not any(node == "output" for node, _, _ in host.events)


@pytest.mark.parametrize(
    "mutation", ["omitted", "contradiction", "duplicate", "foreign-image"]
)
def test_review_cannot_omit_criteria_or_grant_effects(mutation: str) -> None:
    value = _review("pass")
    if mutation == "omitted":
        value["findings"] = []
    elif mutation == "contradiction":
        value["findings"][0]["status"] = "revise"
    elif mutation == "duplicate":
        value["findings"] *= 2
    else:
        value["invalidate_images"] = ["foreign"]
    with pytest.raises(ValueError):
        parse_candidate_review(json.dumps(value), _source().finalization, [])


def test_old_sources_keep_hashes_and_new_policy_changes_behavior() -> None:
    new = _source().to_dict()
    old = deepcopy(new)
    del old["extensions"]["veyra"]["finalization"]
    parsed = AgentSource.from_dict(old)
    assert parsed.to_dict() == old
    assert source_hash(parsed.to_dict()) == source_hash(old)
    assert behavior_hash(new) != behavior_hash(old)
    invalid = deepcopy(new)
    invalid["extensions"]["veyra"]["finalization"]["version"] = "2"
    with pytest.raises(ContractValidationError):
        AgentSource.from_dict(invalid)


def test_owned_verification_compiles_native_policy_without_workflow() -> None:
    task = _stateful_agent()
    task = replace(
        task,
        execution_boundaries=(
            *task.execution_boundaries,
            ExecutionBoundary(
                kind="verification",
                stage="manage",
                reason="Check the result and revise defects before delivery",
                checks=("required_fields:result",),
            ),
        ),
    )
    assert decide_product_shape(task).shape == "PURE_AGENT"
    product = generate_builder_product(
        task.goal, ResourceCatalog(), planner_provider=_Planner(task)
    )
    assert product.status == "review", product.diagnostics
    assert product.source is not None and product.source.finalization is not None
    assert product.source.finalization.checks == ("required_fields:result",)
    assert task.execution_boundaries[-1].reason in product.source.finalization.criteria
    assert product.orchestration is None


def test_output_vision_review_requires_primary_vision_even_without_image_input() -> (
    None
):
    task = _stateful_agent()
    task = replace(
        task,
        outputs=(
            TaskIOField(name="result", type="string"),
            TaskIOField(name="view", type="image"),
        ),
        execution_boundaries=(
            ExecutionBoundary(
                kind="verification",
                stage="manage",
                reason="Inspect actual output images before delivery",
                checks=("output.not_empty",),
            ),
        ),
    )
    product = generate_builder_product(
        task.goal, ResourceCatalog(), planner_provider=_Planner(task)
    )
    assert product.source is not None and product.source.finalization.review_images
    primary = next(
        item for item in product.model_requirements if item.slot == "primary"
    )
    assert "image_input" in primary.required


def test_runtime_preflight_includes_output_vision_review() -> None:
    requirements = RuntimeService._runtime_model_requirements(
        SimpleNamespace(_source_requires_model=lambda *args: True),
        "project",
        _source(images=True),
    )
    assert "image_input" in requirements["primary_model"]


def test_visual_review_does_not_silently_drop_generated_images_after_eight_inputs() -> (
    None
):
    source = _source(images=True)
    photo = parse_typed_fields(
        {"photos": {"type": "artifact", "artifact_kind": "image", "multiple": True}},
        "inputs",
    )
    source = replace(source, inputs=photo)

    def artifact():
        return {
            "kind": "artifact",
            "artifact_id": new_uuid7(),
            "filename": "fixture.png",
            "media_type": "image/png",
        }

    values = {
        "photos": [artifact() for _ in range(8)],
        "front": artifact(),
        "side": artifact(),
        "result": {"style": "same"},
    }
    capabilities = RuntimeModelCapabilities(
        "fixture",
        "fixture",
        "supported",
        "supported",
        "unknown",
        "unknown",
        "unknown",
        "static_profile",
    )
    content = _agent_user_content(
        source,
        values,
        capabilities,
        fields={**source.inputs, **source.outputs},
        image_limit=None,
    )
    urls = [part["image_url"]["url"] for part in content if part["type"] == "image_url"]
    assert len(urls) == 10
    assert f"artifact://{values['front']['artifact_id']}" in urls
    assert f"artifact://{values['side']['artifact_id']}" in urls


def test_new_image_versions_are_progress_even_when_defect_text_repeats(
    tmp_path: Path,
) -> None:
    host = _Host(tmp_path)
    candidate = _final({"style": "same"})
    model = _ScriptedLoopModel(
        candidate,
        _review("pass"),
        _review("revise", images=["front"]),
        candidate,
        _review("revise", images=["front"]),
        candidate,
        _review("pass"),
    )
    result = host._execute_loop(
        "project", "run", _source(images=True, max_turns=12), {}, model
    )
    assert result.result is not None
    assert host.rendered == ["front", "side", "front", "front"]


def test_image_cancellation_stops_batches_and_artifact_publication() -> None:
    running = True
    calls = []
    stored = []
    source = _source(images=True)
    field = parse_typed_fields(
        {"view": {"type": "artifact", "artifact_kind": "image", "multiple": True}},
        "outputs",
    )
    node = FlowNode(
        id="render",
        component_type=ComponentType.MODEL,
        outputs=field,
        system_prompt="fixture",
    )

    def generate(prompt, count):
        nonlocal running
        calls.append(count)
        running = False
        return [GeneratedImage(b"fixture", "image/png")]

    client = SimpleNamespace(configured=True, generate_images=generate)
    host = SimpleNamespace(
        _is_running=lambda run_id: running,
        _agent_system_prompt=lambda node, source: "fixture",
        _model_for=lambda *args: client,
        _require_bound_model_capabilities=lambda *args: None,
        _store_artifact=lambda *args: stored.append(args),
    )
    with pytest.raises(_RunAbandoned):
        RuntimeService._run_image_model(host, "project", "run", node, source, {}, None)
    assert len(calls) == 1
    assert stored == []


@pytest.mark.parametrize(
    "check",
    [
        "arbitrary_check",
        "required_fields:missing",
        "constraint_match:missing.total > 10",
    ],
)
def test_invalid_delivery_rules_fail_before_model_work(check: str) -> None:
    payload = _source().to_dict()
    payload["extensions"]["veyra"]["finalization"]["checks"] = [check]
    with pytest.raises(ContractValidationError):
        AgentSource.from_dict(payload)


def test_missing_nested_check_value_returns_feedback_instead_of_terminal_error(
    tmp_path: Path,
) -> None:
    host = _Host(tmp_path)
    source = replace(
        _source(),
        finalization=FinalizationContract(
            checks=("constraint_match:result.total <= 100",)
        ),
    )
    model = _ScriptedLoopModel(_final({}), _final({"total": 100}))
    result = host._execute_loop("project", "run", source, {}, model)
    assert result.result == {"result": {"total": 100}}


def test_advisory_uncertainty_is_disclosed_without_rejecting_delivery(
    tmp_path: Path,
) -> None:
    host = _Host(tmp_path)
    source = replace(
        _source(),
        finalization=FinalizationContract(
            checks=("required_fields:result",),
            advisory_criteria=("Subjective style assessment",),
        ),
    )
    review = _review("uncertain")
    review["status"] = "pass"
    model = _ScriptedLoopModel(_final({"design": "available"}), review)
    result = host._execute_loop("project", "run", source, {}, model)
    assert result.result == {"result": {"design": "available"}}
    accepted = next(
        payload for _, kind, payload in host.events if kind == "finalization.accepted"
    )
    assert accepted["advisory_unverified"] == 1
    assert accepted["findings"][0]["status"] == "uncertain"
    assert not result.verified


def test_image_review_is_one_request_unless_pre_review_was_enabled(
    tmp_path: Path,
) -> None:
    host = _Host(tmp_path)
    source = _source(images=True)
    source = replace(
        source, finalization=replace(source.finalization, pre_render_review=False)
    )
    model = _ScriptedLoopModel(_final({"design": "ready"}), _review("pass"))
    result = host._execute_loop("project", "run", source, {}, model)
    assert result.result is not None
    assert len(model.calls) == 2
    assert host.rendered == ["front", "side"]
    assert "Inspect the attached generated images" in model.calls[1][0]["content"]


def test_agent_check_names_use_actual_agent_io_not_workflow_aliases() -> None:
    task = _stateful_agent()
    task = replace(
        task,
        outputs=(TaskIOField(name="final_design", type="object"),),
        execution_boundaries=(
            ExecutionBoundary(
                kind="verification",
                stage="manage",
                reason="Check final design",
                checks=("required_fields:final_design",),
            ),
        ),
    )
    product = generate_builder_product(
        task.goal, ResourceCatalog(), planner_provider=_Planner(task)
    )
    assert product.status == "review", product.diagnostics
    assert "final-design" in product.source.outputs
    assert product.source.finalization.checks == ("required_fields:final-design",)


def test_canonical_schema_accepts_native_state_and_delivery_contract() -> None:
    from jsonschema import Draft202012Validator

    task = _stateful_agent()
    task = replace(
        task,
        execution_boundaries=(
            *task.execution_boundaries,
            ExecutionBoundary(
                kind="verification",
                stage="manage",
                reason="Check native delivery",
                checks=("required_fields:result",),
            ),
        ),
    )
    product = generate_builder_product(
        task.goal, ResourceCatalog(), planner_provider=_Planner(task)
    )
    schema = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "contracts/schemas/agent-source.schema.json"
        ).read_text()
    )
    Draft202012Validator(schema).validate(product.source.to_dict())


def test_native_read_can_refresh_without_a_false_repeated_effect_block(
    tmp_path: Path,
) -> None:
    from veyra_agent_platform.local.runtime.tools import ToolRuntime

    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    host = _HarnessHost(tmp_path, tool)
    host.tools = ToolRuntime(ResourceCatalog())
    (tmp_path / "facts.txt").write_text("current facts")
    source = _tool_loop_source(tool)
    call = {
        "action": "tool",
        "tool": tool["reference"],
        "arguments": {"path": "facts.txt"},
    }
    model = _ScriptedLoopModel(
        call, call, {"action": "final", "outputs": {"translation": "done"}}
    )
    result = host._execute_loop("project", "run", source, {}, model)
    assert result.result == {"translation": "done"}
    assert len(result.tool_calls) == 2
    assert not any(kind == "tool.input_rejected" for _, kind, _ in host.events)


def test_live_stage_callback_precedes_coverage_and_does_not_fake_completion() -> None:
    task = _stateful_agent()
    stages = []

    def review(requirement, candidate):
        assert stages[-1] == (
            "builder.validation.started",
            {"phase": "coverage_review"},
        )
        assert "builder.compile.completed" in [kind for kind, _ in stages]
        return (
            'coverage_gap: {"requirement":"fixture","reason":"missing capability"}',
        )

    product = generate_builder_product(
        task.goal,
        ResourceCatalog(),
        planner_provider=_Planner(task),
        planner_review=review,
        on_stage=lambda kind, facts: stages.append((kind, facts)),
    )
    assert product.status == "blocked"
    assert not any(kind == "builder.validation.completed" for kind, _ in stages)


def test_native_images_without_policy_reuse_results_at_final(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    source = replace(_source(images=True), finalization=None)
    model = _ScriptedLoopModel(
        {
            "action": "render_images",
            "images": {
                "front": "Chosen blue design, front",
                "side": "Chosen blue design, side",
            },
        },
        _final({"style": "blue"}),
    )
    result = host._execute_loop("project", "run", source, {}, model)
    assert host.rendered == ["front", "side"]
    assert len(model.calls) == 2
    assert result.result["front"]["artifact_id"] == "fixture-1"
    assert result.result["side"]["artifact_id"] == "fixture-2"


def test_no_policy_final_can_reuse_supplied_artifacts_without_generation(
    tmp_path: Path,
) -> None:
    host = _Host(tmp_path)
    source = replace(_source(images=True), finalization=None)
    refs = {
        name: {
            "kind": "artifact",
            "artifact_id": f"existing-{name}",
            "media_type": "image/png",
        }
        for name in ("front", "side")
    }
    model = _ScriptedLoopModel(
        {"action": "final", "outputs": {"result": {"style": "blue"}, **refs}}
    )
    outcome = host._execute_loop("project", "run", source, {}, model)
    assert not host.rendered and outcome.result["front"] == refs["front"]


def test_native_prompt_does_not_append_superseded_initial_inputs() -> None:
    prompts = []
    client = SimpleNamespace(
        configured=True,
        generate_images=lambda prompt, count: prompts.append(prompt)
        or [GeneratedImage(b"fixture", "image/png")],
    )

    class Host:
        _run_image_model = RuntimeService._run_image_model

        def _is_running(self, run_id):
            return True

        def _agent_system_prompt(self, node, source):
            return node.system_prompt

        def _model_for(self, *args):
            return client

        def _require_bound_model_capabilities(self, *args):
            pass

        def _store_artifact(self, *args):
            return {
                "kind": "artifact",
                "artifact_id": "fixture",
                "media_type": "image/png",
            }

    source = replace(
        _source(images=True), inputs=parse_typed_fields({"request": "string"}, "inputs")
    )
    render_image_requests(
        Host(),
        "project",
        "run",
        source,
        {"front": "Confirmed latest blue-silver design with budget 15"},
        {"request": "Obsolete black-gold version with budget 40; do not render"},
        {},
        lambda *args: None,
    )
    assert prompts == ["Confirmed latest blue-silver design with budget 15"]


def test_native_image_review_reserves_delivery_turns_before_any_image_or_review(
    tmp_path: Path,
) -> None:
    host = _Host(tmp_path)
    model = _ScriptedLoopModel(
        {
            "action": "render_images",
            "images": {"front": "blue"},
            "outputs": {"result": {"style": "blue"}},
        }
    )
    outcome = host._execute_loop(
        "project", "run", _source(images=True, max_turns=3), {}, model
    )
    assert outcome.pause is not None and outcome.pause.details["kind"] == "budget"
    assert len(model.calls) == 1 and not host.rendered
    blocked = next(
        payload
        for _, kind, payload in host.events
        if kind == "agent.budget_insufficient"
    )
    assert blocked["budget"] == {
        "scope": "run_model_turns",
        "limit": 3,
        "used": 1,
        "remaining": 2,
    }
    assert blocked["required_remaining"] == 3


@pytest.mark.parametrize("phase", ["pre_render", "images"])
def test_review_timeout_records_phase_without_publishing_or_retrying(
    tmp_path: Path, phase: str
) -> None:
    host = _Host(tmp_path)

    class Model(_ScriptedLoopModel):
        reviews = 0

        def complete_review(self, messages):
            self.reviews += 1
            if phase == "images" and self.reviews == 1:
                return SimpleNamespace(content=json.dumps(_review("pass")))
            raise RuntimeProviderError(
                "runtime_timeout",
                "Runtime model request timed out",
                diagnostic={"timeout_phase": "read", "timeout_seconds": 180},
            )

    model = (
        Model(
            {
                "action": "render_images",
                "images": {"front": "blue"},
                "outputs": {"result": {"style": "blue"}},
            },
            _final({"style": "blue"}),
        )
        if phase == "pre_render"
        else Model(_final({"style": "blue"}))
    )
    source = _source(images=True)
    original_hash = source_hash(source.to_dict())
    with pytest.raises(RuntimeError) as caught:
        host._execute_loop("project", "run", source, {}, model)
    assert caught.value.code == "runtime_timeout"
    failures = [
        payload for _, kind, payload in host.events if kind == "finalization.failed"
    ]
    assert len(failures) == 1
    assert failures[0]["phase"] == phase
    assert failures[0]["published"] is False
    assert failures[0]["elapsed_ms"] >= 0
    assert failures[0]["provider_diagnostic"]["timeout_seconds"] == 180
    assert len(host.rendered) == (0 if phase == "pre_render" else 2)
    assert model.reviews == (1 if phase == "pre_render" else 2)
    assert source_hash(source.to_dict()) == original_hash
    assert not any(kind == "finalization.accepted" for _, kind, _ in host.events)


def test_budget_includes_reviews_and_is_not_reset_by_user_reply(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    source = _source()
    first = host._execute_loop(
        "project",
        "run",
        source,
        {},
        _ScriptedLoopModel({"action": "ask_user", "question": "Choose a design"}),
    )
    assert first.pause is not None
    model = _ScriptedLoopModel(_final({"style": "blue"}), _review("pass"))
    result = host._execute_loop(
        "project", "run", source, {**first.pause.values, "$agent_reply": "Blue"}, model
    )
    assert result.result == {"result": {"style": "blue"}}
    snapshots = [
        payload["budget"] for _, _, payload in host.events if "budget" in payload
    ]
    assert [snapshot["used"] for snapshot in snapshots] == [0, 1, 1, 2, 3]
    assert snapshots[-1]["remaining"] == source.max_turns - 3


def test_review_evidence_does_not_repeat_unexecuted_commands_or_current_candidate() -> (
    None
):
    messages = [
        {
            "role": "assistant",
            "content": json.dumps(
                {
                    "action": "tool",
                    "tool": "native",
                    "arguments": {"private-invalid": "private-value"},
                }
            ),
        },
        {
            "role": "user",
            "content": "Tool native: invalid input. No tool was executed.",
        },
        {
            "role": "assistant",
            "content": json.dumps(
                {"action": "final", "outputs": {"result": "duplicate candidate"}}
            ),
        },
        {
            "role": "assistant",
            "content": json.dumps(
                {"action": "ask_user", "question": "Choose a scheme"}
            ),
        },
        {"role": "user", "content": "Choose scheme two"},
        {
            "role": "assistant",
            "content": json.dumps(
                {"action": "tool", "tool": "native", "arguments": {"value": 2}}
            ),
        },
        {"role": "user", "content": 'Tool result for native:\n{"saved":true}'},
    ]
    observed = review_observations(messages)
    assert "private-invalid" not in json.dumps(observed)
    assert "duplicate candidate" not in json.dumps(observed)
    assert "Choose scheme two" in json.dumps(observed)
    assert "saved" in json.dumps(observed) and len(observed) == 5


def test_native_render_returns_real_refs_before_persistent_final(
    tmp_path: Path,
) -> None:
    host = _Host(tmp_path)
    source = _source(images=True, max_turns=12)
    source = replace(
        source,
        finalization=replace(source.finalization, pre_render_review=False),
        state_contract=StateRequirement(
            entity="Case",
            identity="entity_id",
            scope="project",
            fields={"views": "array"},
            statuses=(),
        ),
    )
    model = _ScriptedLoopModel(
        _final({"design": "ready"}),
        {
            "action": "render_images",
            "images": {"front": "front design", "side": "side design"},
        },
        {"action": "ask_user", "question": "Keep these actual image references?"},
        _final({"design": "ready"}),
        _review("pass"),
    )
    paused = host._execute_loop("project", "run", source, {}, model)
    assert paused.pause is not None
    cache = paused.pause.values["$agent_loop"]["render_cache"]
    assert cache["front"]["artifact"]["artifact_id"] == "fixture-1"
    assert cache["side"]["artifact"]["artifact_id"] == "fixture-2"
    assert "fixture-1" in model.calls[2][-1]["content"]
    result = host._execute_loop(
        "project", "run", source, {**paused.pause.values, "$agent_reply": "Yes"}, model
    )
    assert host.rendered == ["front", "side"]
    assert result.result["front"]["artifact_id"] == "fixture-1"


def test_native_image_provider_failure_is_not_mislabeled_as_input_error(
    tmp_path: Path,
) -> None:
    class Host(_Host):
        def _run_image_model(self, *args):
            raise RuntimeError("runtime_provider_quota", "Provider quota unavailable")

    host = Host(tmp_path)
    source = replace(
        _source(images=True),
        finalization=replace(
            _source(images=True).finalization, pre_render_review=False
        ),
    )
    model = _ScriptedLoopModel(
        {"action": "render_images", "images": {"front": "prompt"}}
    )
    with pytest.raises(RuntimeError) as error:
        host._execute_loop("project", "run", source, {}, model)
    assert error.value.code == "runtime_provider_quota"
    assert len(model.calls) == 1


def test_cached_native_images_need_only_one_complete_post_render_review(
    tmp_path: Path,
) -> None:
    class Host(_Host):
        def _run_image_model(self, *args):
            outputs = super()._run_image_model(*args)
            for name, value in outputs.items():
                value["filename"] = f"{name}.png"
            return outputs

    host = Host(tmp_path)
    source = _source(images=True, max_turns=4)
    original_hash = source.source_hash
    model = _ScriptedLoopModel(
        {
            "action": "render_images",
            "images": {"front": "front", "side": "side"},
            "outputs": {"result": {"style": "blue"}},
        },
        _review("pass"),
        _final({"style": "blue", "saved_revision": 2}),
        _review("pass"),
    )
    result = host._execute_loop("project", "run", source, {}, model)
    assert result.result["result"]["saved_revision"] == 2
    assert len(model.calls) == 4 and host.rendered == ["front", "side"]
    phases = [
        payload.get("phase", "candidate")
        for _, kind, payload in host.events
        if kind == "finalization.started"
    ]
    assert phases == ["pre_render", "images"]
    assert source.source_hash == original_hash


def test_changed_implicit_image_candidate_keeps_before_effect_review(
    tmp_path: Path,
) -> None:
    class Host(_Host):
        def _run_image_model(self, *args):
            outputs = super()._run_image_model(*args)
            for name, value in outputs.items():
                value["filename"] = f"{name}.png"
            return outputs

    host = Host(tmp_path)
    model = _ScriptedLoopModel(
        _final({"style": "blue"}),
        _review("pass"),
        _review("revise"),
        _final({"style": "red"}),
        _review("pass"),
        _review("pass"),
    )
    result = host._execute_loop("project", "run", _source(images=True), {}, model)
    assert result.result["result"]["style"] == "red"
    assert len(model.calls) == 6
    assert host.rendered == ["front", "side", "front", "side"]
    phases = [
        payload.get("phase", "candidate")
        for _, kind, payload in host.events
        if kind == "finalization.started"
    ]
    assert phases == ["pre_render", "images", "pre_render", "images"]


def test_native_pre_review_prevents_rendering_before_missing_user_choice(
    tmp_path: Path,
) -> None:
    host = _Host(tmp_path)
    model = _ScriptedLoopModel(
        {
            "action": "render_images",
            "images": {"front": "prompt"},
            "outputs": {"result": {"choice": "unconfirmed"}},
        },
        _review("needs_input"),
        {"action": "ask_user", "question": "Which concept do you choose?"},
    )
    paused = host._execute_loop("project", "run", _source(images=True), {}, model)
    assert paused.pause is not None
    assert not host.rendered
    assert not any(kind == "finalization.accepted" for _, kind, _ in host.events)


def test_render_cache_reuses_identical_requests_and_honors_explicit_variant(
    tmp_path: Path,
) -> None:
    host = _Host(tmp_path)
    cache = {}
    source = _source(images=True)
    first = render_image_requests(
        host,
        "project",
        "run",
        source,
        {"front": "prompt"},
        {},
        cache,
        lambda *args: None,
    )
    again = render_image_requests(
        host,
        "project",
        "run",
        source,
        {"front": "prompt"},
        {},
        cache,
        lambda *args: None,
    )
    changed = render_image_requests(
        host,
        "project",
        "run",
        source,
        {"front": {"prompt": "prompt", "regenerate": True}},
        {},
        cache,
        lambda *args: None,
    )
    assert first == again
    assert changed != first
    assert len(host.rendered) == 2


def test_hyphenated_and_long_image_outputs_have_valid_wire_node_ids() -> None:
    names = ["render-front", "a" * 61 + "-x", "a" * 61 + "-y"]
    ids = [image_node_id(name) for name in names]
    assert len(set(ids)) == 3
    for node_id in ids:
        RunEvent.from_dict(
            {
                "schema_version": "1.0",
                "event_id": new_uuid7(),
                "run_id": new_uuid7(),
                "sequence": 1,
                "timestamp": "2026-10-14T00:00:00Z",
                "kind": "image.response_received",
                "node_id": node_id,
                "payload": {"image_count": 1},
            }
        )


def test_review_text_never_embeds_image_bytes_as_json_observations() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Actual facts"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,private-bytes"},
                },
            ],
        }
    ]
    observations = review_observations(messages)
    assert observations == [{"role": "user", "content": "Actual facts"}]
    assert "private-bytes" not in json.dumps(observations)
