import json
from copy import deepcopy
from dataclasses import replace

import pytest

from veyra_agent_platform.local.runtime.client import RuntimeProviderError
from veyra_agent_platform.local.runtime.finalization import candidate_review_prompt
from veyra_agent_platform.local.runtime.finalization_gate import review_before_render
from veyra_agent_platform.local.runtime.service import RuntimeError, _RunAbandoned

from .test_agent_finalization import _final, _Host, _review, _ScriptedLoopModel, _source


def _preview(host, source, model, *, images=None, outputs=None, remaining_requests=1):
    return review_before_render(
        host,
        "project",
        "run",
        source,
        model,
        {},
        outputs if outputs is not None else {"result": {"design": "blue"}},
        [],
        lambda node, kind, payload: host._persist_event("run", node, kind, payload),
        remaining_requests=remaining_requests,
        user_replies=[{"question": "Which design?", "answer": "Blue"}],
        pending_images=images or {"front": "Repair the confirmed blue front"},
        design_context="Keep the confirmed blue design",
    )


def test_pre_review_keeps_original_image_scope_and_returns_actionable_revision(
    tmp_path,
):
    host = _Host(tmp_path)
    source = _source(images=True)
    before = source.source_hash
    model = _ScriptedLoopModel(_review("revise", images=["front"]))
    decision = _preview(host, source, model)
    assert decision.outputs is None and decision.model_requests == 1
    assert decision.feedback["invalidate_images"] == ["front"]
    assert source.source_hash == before
    assert not host.rendered and not host.effects
    assert not any(kind == "finalization.accepted" for _, kind, _ in host.events)
    assert host.events[-1][1:] == (
        "finalization.rejected",
        {"phase": "pre_render", **decision.feedback, "published": False},
    )


def test_pre_review_unknown_image_remains_invalid_with_safe_scope_diagnostic(tmp_path):
    host = _Host(tmp_path)
    model = _ScriptedLoopModel(_review("revise", images=["unknown"]))
    with pytest.raises(RuntimeError) as caught:
        _preview(host, _source(images=True), model)
    assert caught.value.code == "agent_finalization_review_invalid"
    failure = host.events[-1][2]
    assert failure["phase"] == "pre_render"
    assert failure["diagnostic"]["declared_image_outputs"] == ["front", "side"]
    assert failure["diagnostic"]["invalid_image_indexes"] == [0]
    assert not host.rendered


def test_readiness_receives_pending_target_and_explicit_reuse_not_final_delivery(
    tmp_path,
):
    host = _Host(tmp_path)
    model = _ScriptedLoopModel(_review("pass"))
    requests = {
        "front": {"prompt": "Repair only the front", "regenerate": True},
        "side": {"artifact": {"$artifact": "owned-side"}},
    }
    decision = _preview(host, _source(images=True), model, images=requests)
    evidence = json.loads(model.calls[0][1]["content"])
    assert evidence["review_scope"] == {
        "phase": "pre_render",
        "declared_image_outputs": ["front", "side"],
        "pending_image_requests": requests,
        "design_context": "Keep the confirmed blue design",
    }
    assert decision.outputs == {"result": {"design": "blue"}}
    assert decision.feedback is None and not host.rendered
    assert all(kind != "finalization.accepted" for _, kind, _ in host.events)
    completed = [p for _, k, p in host.events if k == "finalization.completed"]
    assert len(completed) == 1 and completed[0]["phase"] == "pre_render"
    assert not completed[0]["published"]


@pytest.mark.parametrize("status", ["revise", "needs_input", "uncertain"])
def test_existing_prerequisite_defects_still_prevent_image_effects(tmp_path, status):
    host = _Host(tmp_path)
    decision = _preview(host, _source(images=True), _ScriptedLoopModel(_review(status)))
    assert decision.outputs is None and decision.feedback["status"] == status
    assert not host.rendered and not host.effects


def test_pre_review_deterministic_failure_does_not_call_model_or_render(tmp_path):
    host = _Host(tmp_path)
    model = _ScriptedLoopModel()
    decision = _preview(host, _source(images=True), model, outputs={})
    assert decision.feedback["failed_checks"] == ["required_fields:result"]
    assert not model.calls and not host.rendered


def test_readiness_pass_never_replaces_actual_post_render_delivery_review(tmp_path):
    class Host(_Host):
        def _run_image_model(self, *args):
            outputs = super()._run_image_model(*args)
            for name, value in outputs.items():
                value["filename"] = f"{name}.png"
            return outputs

    host = Host(tmp_path)
    model = _ScriptedLoopModel(
        {
            "action": "render_images",
            "images": {"front": "front", "side": "side"},
            "outputs": {"result": {"design": "blue"}},
        },
        _review("pass"),
        _final({"design": "blue", "persistence": "missing"}),
        _review("revise", images=["front"]),
        {"action": "ask_user", "question": "Delivery remains incomplete"},
    )
    outcome = host._execute_loop("project", "run", _source(images=True), {}, model)
    assert outcome.result is None and outcome.pause is not None
    assert host.rendered == ["front", "side"]
    phases = [p["phase"] for _, k, p in host.events if k == "finalization.started"]
    assert phases == ["pre_render", "images"]
    assert not any(k == "finalization.accepted" for _, k, _ in host.events)


def test_readiness_cache_does_not_approve_a_changed_prompt_or_design_context(tmp_path):
    host = _Host(tmp_path)
    request = {
        "action": "render_images",
        "images": {"front": "front"},
        "outputs": {"result": {"design": "blue"}},
    }
    model = _ScriptedLoopModel(
        request,
        _review("pass"),
        {**request, "images": {"front": "unreviewed new front"}},
        _review("revise"),
        {**request, "design_context": "unreviewed new identity"},
        _review("needs_input"),
        {"action": "ask_user", "question": "Choose the identity"},
    )
    outcome = host._execute_loop("project", "run", _source(images=True), {}, model)
    assert outcome.pause is not None and outcome.result is None
    assert host.rendered == ["front"]
    assert len([k for _, k, _ in host.events if k == "finalization.started"]) == 3


def test_phase_instructions_defer_only_readiness_not_delivery_criteria():
    policy = _source(images=True).finalization
    pre = candidate_review_prompt(policy, phase="pre_render")
    post = candidate_review_prompt(policy, phase="images")
    assert "NOT final delivery" in pre
    assert "persistence of their returned references" in pre
    assert "pending prompts, reuse references" in pre
    assert "must be supported now" in post
    assert "Do not accept a plan or a prior readiness pass" in post
    for criterion in policy.review_criteria:
        assert criterion in pre and criterion in post


def test_partial_render_resume_reuses_reviewed_plan_without_an_extra_model_turn(
    tmp_path,
):
    class Host(_Host):
        interrupted = False
        saved = None

        def _run_image_model(self, *args):
            outputs = super()._run_image_model(*args)
            for name, value in outputs.items():
                value["filename"] = f"{name}.png"
            return outputs

        def _checkpoint_execution(self, project_id, run_id, source, node, values, **kw):
            state = values["$agent_loop"]
            action = state.get("pending_action") or {}
            if (
                not self.interrupted
                and "front" in state["render_cache"]
                and set(action.get("images", {})) == {"side"}
            ):
                self.saved = deepcopy(values)
                self.interrupted = True
                raise _RunAbandoned()

    host = Host(tmp_path)
    model = _ScriptedLoopModel(
        {
            "action": "render_images",
            "images": {"front": "front", "side": "side"},
            "outputs": {"result": {"design": "blue"}},
        },
        _review("pass"),
        _final({"design": "blue"}),
        _review("pass"),
    )
    source = _source(images=True, max_turns=4)
    with pytest.raises(_RunAbandoned):
        host._execute_loop("project", "run", source, {}, model)
    assert host.saved is not None and host.rendered == ["front"]
    pending = host.saved["$agent_loop"]["pending_action"]
    assert set(pending["_image_plan"]) == {"front", "side"}
    assert set(pending["images"]) == {"side"}
    result = host._execute_loop("project", "run", source, host.saved, model)
    assert result.result is not None and result.pause is None
    assert host.rendered == ["front", "side"] and len(model.calls) == 4
    assert [p["phase"] for _, k, p in host.events if k == "finalization.started"] == [
        "pre_render",
        "images",
    ]


@pytest.mark.parametrize("remaining", [0, 1])
def test_advisory_pre_review_unavailable_does_not_block_required_rules(
    tmp_path, remaining
):
    host = _Host(tmp_path)
    source = _source(images=True)
    source = replace(
        source,
        finalization=replace(
            source.finalization, criteria=(), advisory_criteria=("Consider style",)
        ),
    )

    class Model(_ScriptedLoopModel):
        def complete_review(self, messages):
            self.calls.append(messages)
            raise RuntimeProviderError("runtime_timeout", "Review unavailable")

    model = Model()
    decision = _preview(host, source, model, remaining_requests=remaining)
    assert decision.outputs is not None and decision.feedback is None
    assert decision.model_requests == remaining and len(model.calls) == remaining
    assert not host.rendered
    assert not any(k == "finalization.accepted" for _, k, _ in host.events)


def test_cancel_during_readiness_cannot_publish_or_begin_images(tmp_path):
    host = _Host(tmp_path)

    class Model(_ScriptedLoopModel):
        def complete(self, messages):
            response = super().complete(messages)
            host.running = False
            return response

    with pytest.raises(_RunAbandoned):
        _preview(host, _source(images=True), Model(_review("pass")))
    assert not host.rendered and not host.effects
    assert not any(k == "finalization.accepted" for _, k, _ in host.events)
