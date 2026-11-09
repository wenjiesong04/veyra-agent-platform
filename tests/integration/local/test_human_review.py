"""User feedback uses real snapshots and SQLite, never a paid model."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.contracts.wire import RunEvent
from veyra_agent_platform.local.storage.objects import object_path

from .test_run_evaluation import _check, _client, _create, _evaluate, _spec
from .test_runtime_artifacts import _PNG, _upload
from .test_runtime_routes import ScriptedRuntimeTransport
from .test_workflow_version_boundary import await_workflow, save, setup_call


def _human(run, path=None):
    return _spec(
        run,
        _check(
            path or ["result"], "human_review", id="visual", label="Visual identity"
        ),
    )


def _submission(
    report, outcome="fail", reason="The view does not match the chosen identity"
):
    return {
        "expected_report_id": report["evaluation_id"],
        "version_id": report["version_id"],
        "spec_hash": report["spec_hash"],
        "result_hash": report["result_hash"],
        "decisions": [{"check_id": "visual", "outcome": outcome, "reason": reason}],
    }


def _review(client, prefix, run, base, *, payload=None, key=None):
    root = base.get("root_evaluation_id", base["evaluation_id"])
    return client.post(
        f"{prefix}/runs/{run['run_id']}/evaluations/{root}/reviews",
        json=payload or _submission(base),
        headers={"Idempotency-Key": key or new_uuid7()},
    )


def test_user_review_appends_history_and_explicit_corrections_without_changing_run(
    tmp_path,
):
    transport = ScriptedRuntimeTransport([])
    with _client(tmp_path, transport) as client:
        _, prefix, run = _create(client)
        before = dict(client.app.state.repository.run(run["run_id"]))
        original = _evaluate(client, prefix, run, _human(run)).json()
        key = new_uuid7()
        rejected = _review(client, prefix, run, original, key=key)
        assert rejected.status_code == 200, rejected.text
        rejected = rejected.json()
        assert rejected["decision"] == "rejected"
        assert rejected["checks"][0]["human_review"]["source"] == "local_user"
        corrected = _review(
            client,
            prefix,
            run,
            rejected,
            payload=_submission(
                rejected, "pass", "Independently inspected the selected output"
            ),
        ).json()
        assert corrected["decision"] == "accepted"
        assert corrected["parent_evaluation_id"] == rejected["evaluation_id"]
        assert (
            corrected["review"]["supersedes_review_id"]
            == rejected["review"]["review_id"]
        )
        assert _review(client, prefix, run, original, key=key).json() == rejected
        assert _review(client, prefix, run, original).status_code == 409
        reports = client.get(f"{prefix}/runs/{run['run_id']}/evaluations").json()[
            "reports"
        ]
        assert reports == [corrected, rejected, original]
        assert dict(client.app.state.repository.run(run["run_id"])) == before
        assert not transport.calls
        events = client.get(f"{prefix}/runs/{run['run_id']}").json()["events"]
        for event in events:
            RunEvent.from_dict(event)
        assert sum(event["kind"] == "evaluation.reviewed" for event in events) == 2


@pytest.mark.parametrize("same_key", [False, True])
def test_concurrent_human_reviews_have_one_head_and_idempotent_replay(
    tmp_path, same_key
):
    with _client(tmp_path, ScriptedRuntimeTransport([])) as client:
        _, prefix, run = _create(client)
        base = _evaluate(client, prefix, run, _human(run)).json()
        key = new_uuid7()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda _: _review(
                        client, prefix, run, base, key=key if same_key else new_uuid7()
                    ),
                    range(2),
                )
            )
        assert sorted(response.status_code for response in responses) == (
            [200, 200] if same_key else [200, 409]
        )
        reports = client.get(f"{prefix}/runs/{run['run_id']}/evaluations").json()[
            "reports"
        ]
        assert len(reports) == 2
        if same_key:
            assert responses[0].json() == responses[1].json()
        changed = _submission(
            base, "pass", "Different decision with the same request key"
        )
        if same_key:
            assert (
                _review(client, prefix, run, base, key=key, payload=changed).status_code
                == 409
            )


def test_user_review_cannot_override_machine_checks_or_snapshot_identity(tmp_path):
    with _client(tmp_path, ScriptedRuntimeTransport([])) as client:
        _, prefix, run = _create(client)
        base = _evaluate(
            client, prefix, run, _spec(run, _check(), *_human(run)["checks"])
        ).json()
        for field in ("version_id", "spec_hash", "result_hash"):
            payload = _submission(base)
            payload[field] = new_uuid7() if field == "version_id" else "0" * 64
            response = _review(client, prefix, run, base, payload=payload)
            assert (
                response.status_code == 422
                and response.json()["code"] == "evaluation_review_mismatch"
            )
        payload = _submission(base)
        payload["decisions"][0]["check_id"] = "amount"
        response = _review(client, prefix, run, base, payload=payload)
        assert response.json()["code"] == "evaluation_check_not_reviewable"
        payload = _submission(base)
        payload["decisions"][0]["source"] = "model"
        assert _review(client, prefix, run, base, payload=payload).status_code == 422
        unknown = _review(
            client,
            prefix,
            run,
            base,
            payload=_submission(base, "unknown", "Need a source image"),
        ).json()
        assert (
            unknown["decision"] == "inconclusive"
            and unknown["checks"][0]["status"] == "pass"
        )


def test_visual_review_is_bound_to_owned_artifact_bytes_not_only_the_reference(
    tmp_path,
):
    with _client(tmp_path, ScriptedRuntimeTransport([])) as client:
        project, prefix, _ = _create(client)
        uploaded = _upload(
            client, project["project_id"], "identity.png", _PNG, "image/png"
        ).json()
        reference = client.app.state.artifacts.ref(
            project["project_id"], uploaded["artifact_id"]
        )
        from .test_runtime_routes import _run_until_settled

        run = _run_until_settled(
            client, f"{prefix}/run", {"payload": {"image": reference}}
        )
        base = _evaluate(client, prefix, run, _human(run, ["result", "image"])).json()
        assert base["checks"][0]["evidence"][0]["sha256"] == uploaded["sha256"]
        path = object_path(client.app.state.artifacts.object_root, uploaded["sha256"])
        path.write_bytes(b"corrupt fixture image")
        response = _review(
            client,
            prefix,
            run,
            base,
            payload=_submission(base, "pass", "Old image looked correct"),
        )
        assert (
            response.status_code == 409
            and response.json()["code"] == "evaluation_snapshot_changed"
        )
        assert client.get(f"{prefix}/runs/{run['run_id']}/evaluations").json()[
            "reports"
        ] == [base]


def test_missing_human_output_cannot_be_approved(tmp_path):
    with _client(tmp_path, ScriptedRuntimeTransport([])) as client:
        _, prefix, run = _create(client)
        base = _evaluate(client, prefix, run, _human(run, ["missing"])).json()
        response = _review(
            client,
            prefix,
            run,
            base,
            payload=_submission(base, "pass", "Cannot fabricate a missing output"),
        )
        assert (
            response.status_code == 422
            and response.json()["code"] == "evaluation_check_not_reviewable"
        )


def test_manual_pass_cannot_erase_required_machine_failure(tmp_path):
    with _client(tmp_path, ScriptedRuntimeTransport([])) as client:
        _, prefix, run = _create(client)
        base = _evaluate(
            client,
            prefix,
            run,
            _spec(run, _check(expected="999"), *_human(run)["checks"]),
        ).json()
        result = _review(
            client,
            prefix,
            run,
            base,
            payload=_submission(base, "pass", "Visual check only"),
        )
        assert result.status_code == 200, result.text
        assert result.json()["decision"] == "rejected"
        assert result.json()["checks"][0]["status"] == "fail"


def test_workflow_user_review_has_the_same_append_only_contract(tmp_path):
    transport = ScriptedRuntimeTransport([])
    with _client(tmp_path, transport) as client:
        _, _, _, prefix, draft = setup_call(client)
        save(client, prefix, draft)
        started = client.post(
            f"{prefix}/run",
            json={"inputs": {"request": "facts"}},
            headers={"Idempotency-Key": new_uuid7()},
        ).json()
        run = await_workflow(client, prefix, started["run_id"])
        before = dict(client.app.state.workflow_runtime.store.row(run["run_id"]))
        base = _evaluate(client, prefix, run, _human(run)).json()
        accepted = _review(
            client,
            prefix,
            run,
            base,
            payload=_submission(base, "pass", "Manually read this workflow output"),
        )
        assert accepted.status_code == 200, accepted.text
        assert (
            accepted.json()["decision"] == "accepted"
            and accepted.json()["input_hash"] is None
        )
        assert (
            dict(client.app.state.workflow_runtime.store.row(run["run_id"])) == before
        )
        assert not transport.calls
