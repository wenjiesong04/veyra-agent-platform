import json
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from veyra_agent_platform.local.runtime.finalization import (
    ReviewProtocolError,
    parse_candidate_review,
)
from veyra_agent_platform.local.runtime.service import _RunAbandoned

from .test_agent_finalization import _final, _Host, _review, _ScriptedLoopModel, _source


class Host(_Host):
    def _run_image_model(self, *args):
        outputs = super()._run_image_model(*args)
        for name, value in outputs.items():
            value["filename"] = f"{name}.png"
        return outputs


@pytest.mark.parametrize("phase", ["candidate", "images"])
def test_only_readiness_can_pass_while_identifying_old_images_to_replace(phase):
    policy = _source(images=True).finalization
    value = json.dumps(_review("pass", images=["front"]))
    ready = parse_candidate_review(value, policy, ["front"], phase="pre_render")
    assert ready.status == "pass" and ready.invalidate_images == ("front",)
    with pytest.raises(ReviewProtocolError) as caught:
        parse_candidate_review(value, policy, ["front"], phase=phase)
    assert caught.value.diagnostic["invalidated_image_outputs"] == ["front"]
    assert caught.value.diagnostic["phase"] == phase


def test_readiness_still_rejects_unknown_image_names():
    with pytest.raises(ReviewProtocolError) as caught:
        parse_candidate_review(
            json.dumps(_review("pass", images=["foreign"])),
            _source(images=True).finalization,
            ["front", "side"],
            phase="pre_render",
        )
    assert caught.value.diagnostic["category"] == "image_scope"
    assert caught.value.diagnostic["invalid_image_indexes"] == [0]


def test_native_readiness_invalidates_planned_cached_view_without_expanding_effects(
    tmp_path,
):
    host = Host(tmp_path)
    action = {
        "action": "render_images",
        "images": {"front": "same prompt"},
        "outputs": {"result": {"design": "blue"}},
    }
    model = _ScriptedLoopModel(
        action,
        _review("pass"),
        {**action, "outputs": {"result": {"design": "blue", "revision": 2}}},
        _review("pass", images=["front"]),
        {"action": "ask_user", "question": "Review the corrected view"},
    )
    outcome = host._execute_loop("project", "run", _source(images=True), {}, model)
    assert outcome.pause is not None and outcome.result is None
    assert host.rendered == ["front", "front"]
    completed = [p for _, k, p in host.events if k == "finalization.completed"]
    assert completed[-1]["applied_image_invalidations"] == ["front"]
    assert completed[-1]["unapplied_image_invalidations"] == []
    assert not any(k == "finalization.accepted" for _, k, _ in host.events)


@pytest.mark.parametrize("advisory", ["required", "mixed", "advisory_only"])
def test_readiness_suggestions_cannot_regenerate_an_explicitly_reused_view(
    tmp_path, advisory
):
    host = Host(tmp_path)
    source = _source(images=True)
    pre = _review("pass", images=["side"])
    post = _review("pass")
    if advisory == "mixed":
        source = replace(
            source,
            finalization=replace(
                source.finalization, advisory_criteria=("Consider style",)
            ),
        )
        for review in (pre, post):
            review["findings"].append(
                {
                    "criterion": 1,
                    "status": "revise",
                    "reason": "Optional style",
                    "evidence": "Existing side view",
                }
            )
    elif advisory == "advisory_only":
        source = replace(
            source,
            finalization=replace(
                source.finalization, criteria=(), advisory_criteria=("Consider style",)
            ),
        )
        for review in (pre, post):
            review["findings"][0]["status"] = "revise"
    side = {
        "kind": "artifact",
        "artifact_id": "owned-side",
        "filename": "side.png",
        "media_type": "image/png",
    }
    record = SimpleNamespace(
        media_type="image/png", to_dict=lambda: side, to_ref=lambda: side
    )
    host.artifacts = SimpleNamespace(read_bytes=lambda _p, _a: (record, b"fixture"))
    model = _ScriptedLoopModel(
        {
            "action": "render_images",
            "images": {"front": "new front", "side": {"artifact": side}},
            "outputs": {"result": {"design": "blue"}},
        },
        pre,
        _final({"design": "blue"}),
        post,
    )
    outcome = host._execute_loop("project", "run", source, {}, model)
    assert host.rendered == ["front"] and outcome.result["side"] == side
    ready = next(
        p
        for _, k, p in host.events
        if k == "finalization.completed" and p["phase"] == "pre_render"
    )
    assert ready["applied_image_invalidations"] == []
    assert ready["unapplied_image_invalidations"] == ["side"]
    assert len(model.calls) == 4


@pytest.mark.parametrize("interrupt", [False, True])
def test_implicit_readiness_invalidation_is_checkpointed_before_a_new_effect(
    tmp_path, interrupt
):
    class CheckpointHost(Host):
        saved = None
        interrupted = False

        def _checkpoint_execution(
            self, project_id, run_id, source, node, values, **kwargs
        ):
            if (
                interrupt
                and not self.interrupted
                and self.events[-1][2].get("applied_image_invalidations") == ["front"]
            ):
                self.saved = deepcopy(values)
                self.interrupted = True
                raise _RunAbandoned()

    host = CheckpointHost(tmp_path)
    source = _source(images=True)
    model = _ScriptedLoopModel(
        _final({"design": "blue"}),
        _review("pass"),
        _review("revise", images=["side"]),
        _final({"design": "blue", "revision": 2}),
        _review("pass", images=["front"]),
        _review("pass"),
    )
    if interrupt:
        with pytest.raises(_RunAbandoned):
            host._execute_loop("project", "run", source, {}, model)
        assert host.saved is not None
        assert "front" not in host.saved["$agent_loop"]["render_cache"]
        outcome = host._execute_loop("project", "run", source, host.saved, model)
    else:
        outcome = host._execute_loop("project", "run", source, {}, model)
    assert outcome.result is not None and host.rendered == [
        "front",
        "side",
        "front",
        "side",
    ]
    assert len(model.calls) == 6
