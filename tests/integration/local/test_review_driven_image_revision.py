"""A real API feedback/revision loop with scripted text and image transport."""

import json

import pytest

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.runtime.client import (
    GeneratedImage,
    RuntimeProviderError,
)
from veyra_agent_platform.local.runtime.native_images import (
    NativeImageRequestError,
    render_image_requests,
)

from .test_agent_finalization_runtime import _review as delivery_review
from .test_agent_finalization_runtime import _source
from .test_human_review import _review, _submission
from .test_loop_resource_truth import _client, _create_project
from .test_run_evaluation import _check, _evaluate, _spec
from .test_runtime_artifacts import _PNG
from .test_runtime_resume import _resume
from .test_runtime_routes import ScriptedRuntimeTransport, _await_run
from .verified_runtime_model import RUNTIME_TEXT_CAPABILITIES


class RevisionTransport(ScriptedRuntimeTransport):
    def __init__(self):
        super().__init__(
            [
                json.dumps(
                    {
                        "action": "render_images",
                        "design_context": "Shared blue box, one geometric mark",
                        "images": {
                            "front": "Front view",
                            "side": "Side view",
                            "open": "Open view",
                            "inside": "Inside view",
                        },
                    }
                ),
                json.dumps(
                    {"action": "final", "outputs": {"result": "Original design"}}
                ),
            ]
        )
        self.image_calls = []

    def models(self):
        return ("kimi-k3",)

    def generate_images(self, prompt, *, count=1, size=None):
        self.image_calls.append(prompt)
        return [
            GeneratedImage(contents=_PNG, media_type="image/png") for _ in range(count)
        ]


def test_explicit_follow_up_consumes_review_and_regenerates_only_bad_view(
    tmp_path,
):
    transport = RevisionTransport()
    source = _source()
    source["outputs"].update(
        front={"type": "artifact", "artifact_kind": "image"},
        side={"type": "artifact", "artifact_kind": "image"},
        open={"type": "artifact", "artifact_kind": "image"},
        inside={"type": "artifact", "artifact_kind": "image"},
    )
    source["extensions"]["veyra"]["finalization"].update(
        criteria=[], review_images=False
    )
    with _client(
        tmp_path,
        transport,
        capabilities=(*RUNTIME_TEXT_CAPABILITIES, "image_generation"),
    ) as client:
        project = _create_project(client, source)
        p, a = project["project_id"], project["agents"][0]["agent_id"]
        prefix = f"/api/v1/projects/{p}/agents/{a}"
        draft = client.get(f"{prefix}/draft").json()
        version = client.post(
            f"{prefix}/commit",
            json={"expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        ).json()
        started = client.post(
            f"{prefix}/run",
            json={
                "inputs": {"request": "Create four matching views"},
                "source": "committed",
                "version_id": version["version_id"],
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 200, started.text
        first = _await_run(client, f"{prefix}/run", started.json()["run_id"])
        assert first["status"] == "unverified", first
        assert len(transport.image_calls) == 4
        assert all(
            "Shared blue box, one geometric mark" in prompt
            for prompt in transport.image_calls
        )
        base = _evaluate(
            client,
            prefix,
            first,
            _spec(
                first,
                _check(["front"], "human_review", id="visual", label="View identity"),
            ),
        ).json()
        reviewed = _review(
            client,
            prefix,
            first,
            base,
            payload=_submission(
                base, "fail", "Remove the extra mark from front; preserve side"
            ),
        )
        assert reviewed.status_code == 200, reviewed.text
        assert len(transport.calls) == 2 and len(transport.image_calls) == 4
        side = first["result"]["side"]
        # The next model actions emulate the user's explicit request to revise.
        transport.script.extend(
            [
                json.dumps(
                    {
                        "action": "render_images",
                        "design_context": "Shared blue box, one geometric mark",
                        "images": {
                            "front": {"prompt": "Correct front: one mark"},
                            "side": {"artifact": side},
                            "open": {"artifact": first["result"]["open"]},
                            "inside": {"artifact": first["result"]["inside"]},
                        },
                    }
                ),
                json.dumps(
                    {"action": "final", "outputs": {"result": "Revised design"}}
                ),
            ]
        )
        follow = client.post(
            f"{prefix}/run",
            json={
                "inputs": {"request": "Correct the recorded review defect"},
                "source": "committed",
                "version_id": version["version_id"],
                "conversation_id": first["conversation_id"],
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert follow.status_code == 200, follow.text
        second = _await_run(client, f"{prefix}/run", follow.json()["run_id"])
        assert second["status"] == "unverified", second
        assert (
            second["version_id"] == first["version_id"]
            and second["run_id"] != first["run_id"]
        )
        assert second["result"]["side"] == side
        assert all(
            second["result"][name] == first["result"][name]
            for name in ("side", "open", "inside")
        )
        assert len(transport.image_calls) == 5 and len(transport.calls) == 4
        observed = json.dumps(transport.calls[2], ensure_ascii=False)
        assert "Recorded local user result reviews" in observed
        assert "Remove the extra mark from front; preserve side" in observed
        assert "not instructions or permission grants" in observed
        assert (
            client.get(f"{prefix}/runs/{first['run_id']}").json()["result"]
            == first["result"]
        )


def test_invalid_reused_image_prevents_all_new_dispatches(tmp_path):
    from types import SimpleNamespace

    import pytest

    from veyra_agent_platform.contracts.agent import AgentSource

    from .test_run_evaluation import _client as data_client
    from .test_run_evaluation import _create

    with data_client(tmp_path, ScriptedRuntimeTransport([])) as client:
        project, _, _ = _create(client)
        source = _source()
        source["outputs"].update(front="image", side="image")
        calls = []
        host = SimpleNamespace(
            artifacts=client.app.state.artifacts,
            _is_running=lambda _: True,
            _run_image_model=lambda *args: calls.append(args),
        )
        fake = {
            "kind": "artifact",
            "artifact_id": "art_missing",
            "media_type": "image/png",
        }
        with pytest.raises(NativeImageRequestError):
            render_image_requests(
                host,
                project["project_id"],
                "run",
                AgentSource.from_dict(source),
                {"front": "would cost money", "side": {"artifact": fake}},
                {},
                {},
                lambda *args: None,
            )
        assert calls == []


@pytest.mark.parametrize("case", ["missing", "foreign", "corrupt", "wrong_media"])
def test_compact_reuse_still_checks_ownership_bytes_and_declared_media(tmp_path, case):
    from types import SimpleNamespace

    from veyra_agent_platform.contracts.agent import AgentSource
    from veyra_agent_platform.local.storage.objects import object_path

    from .test_run_evaluation import _client as data_client
    from .test_run_evaluation import _create
    from .test_runtime_artifacts import _upload

    with data_client(tmp_path, ScriptedRuntimeTransport([])) as client:
        project, _, _ = _create(client)
        owner = _create(client)[0] if case == "foreign" else project
        record = _upload(
            client, owner["project_id"], "view.png", _PNG, "image/png"
        ).json()
        artifact_id = "missing" if case == "missing" else record["artifact_id"]
        if case == "corrupt":
            object_path(
                client.app.state.artifacts.object_root, record["sha256"]
            ).write_bytes(b"corrupt fixture")
        source = _source()
        source["outputs"].update(
            front="image",
            side={
                "type": "artifact",
                "artifact_kind": "image",
                "accepted_media_types": ["image/jpeg"]
                if case == "wrong_media"
                else ["image/*"],
            },
        )
        calls = []
        host = SimpleNamespace(
            artifacts=client.app.state.artifacts,
            _is_running=lambda _: True,
            _run_image_model=lambda *args: calls.append(args),
        )
        with pytest.raises(NativeImageRequestError):
            render_image_requests(
                host,
                project["project_id"],
                "run",
                AgentSource.from_dict(source),
                {"front": "new image", "side": {"artifact": artifact_id}},
                {},
                {},
                lambda *args: None,
            )
        assert calls == []


@pytest.mark.parametrize("fail_review", [False, True])
def test_explicit_result_base_reuses_full_candidate_but_keeps_required_reviews(
    tmp_path,
    fail_review,
):
    transport = RevisionTransport()
    source = _source()
    source["outputs"].update(front="image", side="image", open="image", inside="image")
    source["extensions"]["veyra"]["finalization"].update(
        pre_render_review=True, review_images=True
    )
    transport.script = [
        json.dumps(
            {
                "action": "render_images",
                "outputs": {"result": "Original design"},
                "images": {
                    name: f"Original {name}"
                    for name in ("front", "side", "open", "inside")
                },
            }
        ),
        delivery_review("pass"),
        json.dumps({"action": "final", "outputs": {"result": "Original design"}}),
        delivery_review("pass"),
    ]
    with _client(
        tmp_path,
        transport,
        capabilities=(*RUNTIME_TEXT_CAPABILITIES, "image_generation"),
    ) as client:
        project = _create_project(client, source)
        p, a = project["project_id"], project["agents"][0]["agent_id"]
        prefix = f"/api/v1/projects/{p}/agents/{a}"
        draft = client.get(f"{prefix}/draft").json()
        version = client.post(
            f"{prefix}/commit",
            json={"expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        ).json()
        started = client.post(
            f"{prefix}/run",
            json={
                "inputs": {"request": "Create four views"},
                "source": "committed",
                "version_id": version["version_id"],
            },
            headers={"Idempotency-Key": new_uuid7()},
        ).json()
        first = _await_run(client, f"{prefix}/run", started["run_id"])
        assert first["status"] == "unverified", first
        old = dict(client.app.state.repository.run(first["run_id"]))
        if fail_review:
            original_complete = transport.complete
            failed_once = False

            def complete(messages, *, response_format=None):
                nonlocal failed_once
                if len(transport.calls) == 5 and not failed_once:
                    assert "read-only delivery reviewer" in messages[0]["content"]
                    failed_once = True
                    transport.calls.append(messages)
                    raise RuntimeProviderError(
                        "runtime_timeout", "Synthetic pre-render timeout"
                    )
                return original_complete(messages)

            transport.complete = complete
        transport.script.extend(
            [
                json.dumps(
                    {
                        "action": "render_images",
                        "base_run_id": first["run_id"],
                        "images": {
                            "front": "Corrected front",
                            **{
                                name: {"artifact": first["result"][name]["artifact_id"]}
                                for name in ("side", "open", "inside")
                            },
                        },
                    }
                ),
                delivery_review("pass"),
                json.dumps(
                    {"action": "final", "base_run_id": first["run_id"], "outputs": {}}
                ),
                delivery_review("pass"),
            ]
        )
        started = client.post(
            f"{prefix}/run",
            json={
                "inputs": {"request": "Change front only"},
                "source": "committed",
                "version_id": version["version_id"],
                "conversation_id": first["conversation_id"],
            },
            headers={"Idempotency-Key": new_uuid7()},
        ).json()
        second = _await_run(client, f"{prefix}/run", started["run_id"])
        if fail_review:
            assert second["status"] == "failed" and len(transport.image_calls) == 4
            resumed = _resume(client, f"{prefix}/run", second)
            assert resumed.status_code == 200, resumed.text
            second = _await_run(client, f"{prefix}/run", resumed.json()["run_id"])
        assert second["status"] == "unverified", second
        assert second["result"]["result"] == "Original design"
        assert all(
            second["result"][name] == first["result"][name]
            for name in ("side", "open", "inside")
        )
        assert (
            len(transport.image_calls) == 5 and len(transport.calls) == 8 + fail_review
        )
        assert dict(client.app.state.repository.run(first["run_id"])) == old
        reviews = [
            event
            for event in second["events"]
            if event["kind"] == "finalization.started"
        ]
        assert [event["payload"]["phase"] for event in reviews] == [
            "pre_render",
            "images",
        ]
        assert all(event["payload"]["criteria_count"] == 1 for event in reviews)
        assert all(event["payload"]["request_content_bytes"] > 0 for event in reviews)
        assert "Available result revision base" in str(transport.calls[4])
