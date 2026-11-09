"""Real local persistence and artifact bytes, no real Provider requests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.contracts.evaluation import EvaluationCheck
from veyra_agent_platform.contracts.wire import RunEvent
from veyra_agent_platform.local.storage.objects import object_path

from .test_loop_resource_truth import _client as _runtime_client
from .test_loop_resource_truth import _create_project
from .test_runtime_artifacts import _PNG, _upload
from .test_runtime_routes import ScriptedRuntimeTransport, _run_until_settled
from .test_workflow_version_boundary import (
    agent_source,
    await_workflow,
    save,
    setup_call,
)


def _client(tmp_path: Path, transport):
    # Keep the parent-directory object store private to each corruption fixture.
    return _runtime_client(tmp_path / "database", transport)


def _source() -> dict:
    source = agent_source()
    source.update(inputs={"payload": "object"}, outputs={"result": "object"})
    source["nodes"][1]["mapping"] = {"result": "{{payload}}"}
    return source


def _create(client, value=None, source=None):
    project = _create_project(client, source or _source())
    prefix = (
        f"/api/v1/projects/{project['project_id']}/agents/"
        f"{project['agents'][0]['agent_id']}"
    )
    run = _run_until_settled(
        client,
        f"{prefix}/run",
        {"payload": value or {"amount": "14.50", "lines": [1, 3]}},
    )
    assert run["status"] == "unverified", run
    return project, prefix, run


def _check(path=None, method="number_equals", expected="14.50", **kwargs):
    check = {
        "id": "amount",
        "label": "Exact total",
        "required": True,
        "path": path or ["result", "amount"],
        "method": method,
    }
    if method in {"equals", "number_equals", "set_equals"}:
        check.update(
            expected=expected,
            baseline={
                "kind": "fixture",
                "reference": "independent answer",
                "revision": "1",
            },
        )
    check.update(kwargs)
    return check


def _spec(run, *checks):
    return {
        "version": "1",
        "version_id": run["version_id"],
        "checks": list(checks) or [_check()],
    }


def _evaluate(client, prefix, run, spec=None, key=None):
    return client.post(
        f"{prefix}/runs/{run['run_id']}/evaluations",
        json={"spec": spec or _spec(run)},
        headers={"Idempotency-Key": key or new_uuid7()},
    )


def test_evaluation_pins_version_result_and_baseline_without_model_or_status_changes(
    tmp_path: Path,
):
    transport = ScriptedRuntimeTransport([])
    with _client(tmp_path, transport) as client:
        project, prefix, run = _create(client)
        before = dict(client.app.state.repository.run(run["run_id"]))
        response = _evaluate(client, prefix, run)
        assert response.status_code == 200, response.text
        report = response.json()
        assert report["decision"] == "accepted" and report["scope"] == "declared_checks"
        assert report["checks"][0]["status"] == "pass"
        assert report["spec_hash"] == sha256_digest(report["spec"])
        assert report["result_hash"] == sha256_digest(run["result"])
        assert report["input_hash"] == sha256_digest(
            {"payload": run["result"]["result"]}
        )
        assert (
            report["source_hash"]
            == client.app.state.repository.version(run["version_id"])["source_hash"]
        )
        assert dict(client.app.state.repository.run(run["run_id"])) == before
        assert not transport.calls
        detail = client.get(f"{prefix}/runs/{run['run_id']}").json()
        assert detail["status"] == "unverified" and detail["result"] == run["result"]
        assert detail["events"][-1]["kind"] == "evaluation.completed"
        RunEvent.from_dict(detail["events"][-1])
        assert client.get(f"{prefix}/runs/{run['run_id']}/evaluations").json()[
            "reports"
        ] == [report]
        # Editing the Draft cannot change the frozen definition evaluated above.
        draft = client.get(f"{prefix}/draft").json()
        changed = deepcopy(draft["source"])
        changed["description"] = "Later edit"
        edited = client.patch(
            f"{prefix}/draft",
            json={"source": changed, "expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert edited.status_code == 200, edited.text
        assert (
            _evaluate(client, prefix, run).json()["source_hash"]
            == report["source_hash"]
        )
        assert project["project_id"] == report["project_id"]


def test_wrong_decimal_missing_row_boolean_and_literal_keys_are_evaluated_exactly(
    tmp_path: Path,
):
    with _client(tmp_path, ScriptedRuntimeTransport([])) as client:
        _, prefix, run = _create(
            client,
            {
                "amount": "14.5000001",
                "lines": [1, 3],
                "flag": True,
                "含.点": {"$schema": {"": "yes"}},
            },
        )
        checks = [
            _check(),
            _check(
                ["result", "lines"],
                "set_equals",
                [1, 2, 3],
                id="rows",
                label="Required rows",
            ),
            _check(["result", "flag"], "equals", 1, id="typed", label="Typed value"),
            _check(
                ["result", "missing"],
                "equals",
                None,
                id="missing",
                label="Missing field",
            ),
            _check(
                ["result", "含.点", "$schema", ""],
                "equals",
                "yes",
                id="literal",
                label="Literal keys",
            ),
        ]
        report = _evaluate(client, prefix, run, _spec(run, *checks)).json()
        assert report["decision"] == "rejected"
        assert [check["status"] for check in report["checks"]] == [
            "fail",
            "fail",
            "fail",
            "fail",
            "pass",
        ]
        assert report["checks"][3]["code"] == "output_missing"
        assert report["checks"][0]["actual_value"] == "14.5000001"
        assert report["checks"][2]["actual_value"] is True


def test_model_baseline_and_human_review_never_become_independent_pass(tmp_path: Path):
    with _client(tmp_path, ScriptedRuntimeTransport([])) as client:
        _, prefix, run = _create(client)
        model = _check(
            baseline={
                "kind": "model",
                "reference": "Actor self assessment",
                "revision": "1",
            }
        )
        report = _evaluate(client, prefix, run, _spec(run, model)).json()
        assert report["decision"] == "inconclusive"
        assert report["checks"][0]["status"] == "unknown"
        human = _check(method="human_review")
        report = _evaluate(client, prefix, run, _spec(run, human)).json()
        assert report["decision"] == "inconclusive"
        assert report["checks"][0]["status"] == "awaiting_human"
        advisory = _check(expected="99", required=False, id="advice")
        report = _evaluate(client, prefix, run, _spec(run, _check(), advisory)).json()
        assert report["decision"] == "accepted"
        assert report["checks"][1]["status"] == "fail"
        assert (
            _evaluate(client, prefix, run, _spec(run, advisory)).json()["decision"]
            == "inconclusive"
        )


def test_idempotent_and_concurrent_evaluation_append_exactly_one_report(tmp_path: Path):
    with _client(tmp_path, ScriptedRuntimeTransport([])) as client:
        _, prefix, run = _create(client)
        key = new_uuid7()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(lambda _: _evaluate(client, prefix, run, key=key), range(2))
            )
        assert all(response.status_code == 200 for response in responses)
        assert responses[0].json() == responses[1].json()
        changed = _spec(run, _check(expected="99"))
        assert _evaluate(client, prefix, run, changed, key).status_code == 409
        assert (
            len(
                client.get(f"{prefix}/runs/{run['run_id']}/evaluations").json()[
                    "reports"
                ]
            )
            == 1
        )


def test_evaluation_rejects_active_foreign_and_wrong_version_without_effects(
    tmp_path: Path, monkeypatch
):
    with _client(tmp_path, ScriptedRuntimeTransport([])) as client:
        _, prefix, run = _create(client)
        other, other_prefix, _ = _create(client)
        assert (
            client.get(f"{other_prefix}/runs/{run['run_id']}/evaluations").status_code
            >= 400
        )
        assert (
            _evaluate(
                client, prefix, run, {**_spec(run), "version_id": new_uuid7()}
            ).status_code
            == 422
        )
        monkeypatch.setattr(
            client.app.state.runtime,
            "_schedule_execution",
            lambda *args, **kwargs: None,
        )
        started = client.post(
            f"{prefix}/run",
            json={"inputs": {"payload": {"amount": "1"}}},
            headers={"Idempotency-Key": new_uuid7()},
        ).json()
        assert started["status"] == "running"
        assert (
            _evaluate(client, prefix, started).json()["code"] == "evaluation_run_active"
        )
        assert not client.get(f"{prefix}/runs/{started['run_id']}/evaluations").json()[
            "reports"
        ]
        assert other["project_id"] != run["project_id"]


def test_artifact_check_reads_real_bytes_and_preserves_prior_snapshot(tmp_path: Path):
    with _client(tmp_path, ScriptedRuntimeTransport([])) as client:
        source = _source()
        source.update(inputs={"payload": "image"}, outputs={"result": "image"})
        project = _create_project(client, source)
        prefix = (
            f"/api/v1/projects/{project['project_id']}/agents/"
            f"{project['agents'][0]['agent_id']}"
        )
        uploaded = _upload(
            client, project["project_id"], "one.png", _PNG, "image/png"
        ).json()
        ref = client.app.state.artifacts.ref(
            project["project_id"], uploaded["artifact_id"]
        )
        run = _run_until_settled(client, f"{prefix}/run", {"payload": ref})
        spec = _spec(run, _check(["result"], "artifact_integrity"))
        key = new_uuid7()
        response = _evaluate(client, prefix, run, spec, key)
        assert response.status_code == 200, response.text
        report = response.json()
        assert report["decision"] == "accepted"
        assert report["checks"][0]["evidence"][0]["sha256"] == uploaded["sha256"]
        stored_path = object_path(
            client.app.state.artifacts.object_root, uploaded["sha256"]
        )
        stored_path.write_bytes(b"changed test bytes")
        assert _evaluate(client, prefix, run, spec, key).json() == report
        fresh = _evaluate(client, prefix, run, spec).json()
        assert fresh["decision"] == "rejected"
        assert fresh["checks"][0]["code"] == "artifact_storage_invalid"
        assert fresh["evaluation_id"] != report["evaluation_id"]
        assert client.get(f"{prefix}/runs/{run['run_id']}/evaluations").json()[
            "reports"
        ] == [fresh, report]


def test_forged_foreign_missing_and_empty_artifact_evidence_is_rejected(tmp_path: Path):
    with _client(tmp_path, ScriptedRuntimeTransport([])) as client:
        first, prefix, run = _create(client)
        second, _, _ = _create(client)
        uploaded = _upload(
            client, second["project_id"], "other.png", _PNG, "image/png"
        ).json()
        ref = client.app.state.artifacts.ref(
            second["project_id"], uploaded["artifact_id"]
        )
        service = client.app.state.run_evaluations
        for value, code in (
            (ref, "artifact_not_found"),
            ({**ref, "artifact_id": "art_missing"}, "artifact_not_found"),
            ([], "artifact_empty"),
            ("looks-like-an-image", "artifact_ref_invalid"),
        ):
            check = _check(["result", "image"], "artifact_integrity")
            finding = service._check(
                first["project_id"],
                EvaluationCheck.from_dict(check),
                {"result": {"image": value}},
            )
            assert finding["status"] == "fail" and finding["code"] == code
        owned = _upload(
            client, first["project_id"], "owned.png", _PNG, "image/png"
        ).json()
        owned_ref = client.app.state.artifacts.ref(
            first["project_id"], owned["artifact_id"]
        )
        finding = service._check(
            first["project_id"],
            EvaluationCheck.from_dict(check),
            {"result": {"image": {**owned_ref, "filename": "fake.png"}}},
        )
        assert (
            finding["status"] == "fail" and finding["code"] == "artifact_ref_mismatch"
        )
        assert (
            client.get(f"{prefix}/runs/{run['run_id']}/evaluations").json()["reports"]
            == []
        )


def test_workflow_evaluation_is_offline_and_does_not_invent_original_inputs(
    tmp_path: Path,
):
    transport = ScriptedRuntimeTransport([])
    with _client(tmp_path, transport) as client:
        _, _, _, prefix, draft = setup_call(client)
        save(client, prefix, draft)
        response = client.post(
            f"{prefix}/run",
            json={"inputs": {"request": "facts"}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert response.status_code == 200, response.text
        run = await_workflow(client, prefix, response.json()["run_id"])
        assert run["status"] == "unverified", run
        before = dict(client.app.state.workflow_runtime.store.row(run["run_id"]))
        spec = _spec(run, _check(["result"], "equals", "Version A: facts"))
        response = _evaluate(client, prefix, run, spec)
        assert response.status_code == 200, response.text
        report = response.json()
        assert report["target_kind"] == "workflow" and report["decision"] == "accepted"
        assert report["input_hash"] is None and report["input_evidence"] == "not_saved"
        assert (
            dict(client.app.state.workflow_runtime.store.row(run["run_id"])) == before
        )
        assert not transport.calls
        reports = client.get(f"{prefix}/runs/{run['run_id']}/evaluations").json()[
            "reports"
        ]
        assert reports == [report]
        event = client.app.state.workflow_runtime.store.events(run["run_id"])[-1]
        RunEvent.from_dict(event)
