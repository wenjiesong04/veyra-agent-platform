"""Review schemas use cached protocol facts for the actual Runtime binding."""

import json
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.contracts.finalization import FinalizationContract
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.factory.capability_profile import (
    derive_provider_capability_profile,
)
from veyra_agent_platform.local.factory.config import FactorySettings
from veyra_agent_platform.local.runtime.client import RuntimeCompletion
from veyra_agent_platform.local.runtime.config import RuntimeSettings
from veyra_agent_platform.local.runtime.finalization import candidate_review_schema

from .test_complex_agent_acceptance import _app_start, _commit
from .test_edit_proposal_routes import _target
from .test_loop_resource_truth import _loop_source, _set_io
from .verified_runtime_model import MemorySecretStore, register_verified_model

BASE_URL = "https://api.moonshot.cn/v1"
BUILDER_MODEL = "builder-text-model"
RUNTIME_MODEL = "runtime-text-model"


class _ReviewTransport:
    def __init__(self):
        self.calls = []
        self.script = []

    def models(self):
        return (BUILDER_MODEL, RUNTIME_MODEL, "host-default-model")

    def complete(self, messages, *, response_format=None):
        self.calls.append((messages, response_format))
        content = json.dumps(self.script.pop(0)) if self.script else '{"ok":true}'
        return RuntimeCompletion(content=content, finish_reason="stop")


@contextmanager
def _bound_app(tmp_path: Path, scope="project"):
    transport = _ReviewTransport()
    app = create_app(
        LocalSettings(
            database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
            project_storage_root=tmp_path / "projects",
        ),
        factory_settings=FactorySettings(
            model_id=BUILDER_MODEL, model_base_url=BASE_URL
        ),
        runtime_settings=RuntimeSettings(
            model_id="host-default-model", allow_process_environment_key=False
        ),
        runtime_transport=transport,
        secret_store=MemorySecretStore(),
    )
    with TestClient(app) as client:
        credential_id = register_verified_model(client, model_id=RUNTIME_MODEL)
        pid, target_url, draft = _target(client, "agent")
        aid = draft["source"]["agent_id"]
        binding_url = (
            f"{target_url}/runtime-binding"
            if scope == "agent"
            else f"/api/v1/projects/{pid}/runtime-binding"
        )
        bound = client.patch(
            binding_url,
            json={"credential_id": credential_id, "model_id": RUNTIME_MODEL},
        )
        assert bound.status_code == 200, bound.text
        yield client, transport, pid, aid


def _verified_profile(settings):
    return replace(
        derive_provider_capability_profile(settings),
        strict_json_schema=True,
        strict_json_schema_support="supported",
        json_object_support="supported",
        status="known",
        source="probe",
        probed=True,
        checked_at="2026-10-19T00:00:00Z",
    )


def _schema():
    return candidate_review_schema(
        FinalizationContract(
            criteria=tuple(f"Criterion {index}" for index in range(13))
        ),
        [],
    )


@pytest.mark.parametrize("scope", ["project", "agent"])
def test_app_looks_up_the_selected_runtime_identity_not_the_current_builder_model(
    tmp_path: Path, scope: str
):
    with _bound_app(tmp_path, scope) as (client, transport, pid, aid):
        factory = client.app.state.factory
        runtime = client.app.state.runtime
        builder_profile = _verified_profile(factory.client.settings)
        factory.profiles.put(builder_profile)
        assert factory.resolved_capability_profile().model == BUILDER_MODEL
        model = runtime._model_for(pid, aid)
        assert model.settings.model_id == RUNTIME_MODEL
        assert model.settings.model_base_url == BASE_URL
        assert model.settings.provider_type == "moonshot"
        assert model.settings.allow_process_environment_key is False
        assert model.provider_capability_lookup.__self__ is factory.profiles

        first = model.complete_review([], schema=_schema())
        assert first.review_protocol == "json_object"
        assert transport.calls[-1][1] == {"type": "json_object"}

        selected_profile = _verified_profile(model.settings)
        assert selected_profile.identity_key != builder_profile.identity_key
        factory.profiles.put(selected_profile)
        second = model.complete_review([], schema=_schema())
        assert second.review_protocol == "json_schema"
        assert len(transport.calls) == 2
        response_format = transport.calls[-1][1]
        assert response_format["type"] == "json_schema"
        assert response_format["json_schema"]["strict"] is True
        findings = response_format["json_schema"]["schema"]["properties"]["findings"]
        assert findings["required"] == [str(index) for index in range(13)]
        assert set(findings["properties"]) == set(findings["required"])
        assert (
            factory.resolved_capability_profile().identity_key
            == builder_profile.identity_key
        )


@pytest.mark.parametrize("mismatch", ["model", "base_url"])
def test_cached_protocol_evidence_for_another_runtime_identity_is_not_reused(
    tmp_path: Path, mismatch: str
):
    with _bound_app(tmp_path) as (client, transport, pid, aid):
        model = client.app.state.runtime._model_for(pid, aid)
        settings = model.settings.model_copy(
            update={"model_id": "other-model"}
            if mismatch == "model"
            else {"model_base_url": "https://api.moonshot.cn/v2"}
        )
        unrelated = _verified_profile(settings)
        assert (
            unrelated.identity_key
            != derive_provider_capability_profile(model.settings).identity_key
        )
        client.app.state.factory.profiles.put(unrelated)
        result = model.complete_review([], schema=_schema())
        assert result.review_protocol == "json_object"
        assert transport.calls[-1][1] == {"type": "json_object"}
        assert len(transport.calls) == 1


def test_runtime_structured_output_probe_does_not_supply_strict_schema_evidence(
    tmp_path: Path,
):
    with _bound_app(tmp_path) as (client, transport, pid, aid):
        profiles = client.get("/api/v1/runtime-models").json()["models"]
        selected = next(
            row for row in profiles if row["provider_model_id"] == RUNTIME_MODEL
        )
        assert selected["capabilities"]["structured_output"]["status"] == "supported"
        model = client.app.state.runtime._model_for(pid, aid)
        seed = derive_provider_capability_profile(model.settings)
        assert client.app.state.factory.profiles.get(seed.identity_key) is None
        result = model.complete_review([], schema=_schema())
        assert result.review_protocol == "json_object"
        assert transport.calls[-1][1] == {"type": "json_object"}
        assert len(transport.calls) == 1


def _commit_review_loop(client, pid, aid):
    url = f"/api/v1/projects/{pid}/agents/{aid}"
    draft = client.get(f"{url}/draft").json()
    source = _set_io(
        _loop_source("Summarize only supplied facts"),
        {"request": "string"},
        {"result": "string"},
    )
    source.update(agent_id=aid, slug=draft["source"]["slug"])
    source["extensions"]["veyra"]["finalization"] = {
        "version": "1",
        "checks": ["required_fields:result"],
        "criteria": [f"Criterion {index}" for index in range(13)],
        "review_images": False,
    }
    saved = client.patch(
        f"{url}/draft",
        json={"source": source, "expected_revision": draft["revision"]},
        headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
    )
    assert saved.status_code == 200, saved.text
    version = _commit(client, pid, aid)
    model = client.app.state.runtime._model_for(pid, aid)
    client.app.state.factory.profiles.put(_verified_profile(model.settings))
    return (
        url,
        version,
        client.get(f"{url}/draft").json(),
        client.get(f"{url}/versions").json(),
    )


def _review_result(count):
    return {
        "findings": {
            str(index): {
                "status": "pass",
                "reason": f"Assessment for criterion {index}",
                "evidence": "The supplied facts match the candidate",
            }
            for index in range(count)
        },
        "question": "",
        "invalidate_images": [],
    }


def test_committed_app_run_uses_all_thirteen_review_slots_without_changing_source(
    tmp_path: Path,
):
    with _bound_app(tmp_path) as (client, transport, pid, aid):
        url, version, draft, versions = _commit_review_loop(client, pid, aid)
        transport.script = [
            {"action": "final", "outputs": {"result": "Supported facts"}},
            _review_result(13),
        ]
        run = _app_start(client, f"{url}/run", {"request": "Supplied facts"})
        assert run["status"] == "unverified", run
        assert run["result"] == {"result": "Supported facts"}
        assert run["version_id"] == version["version_id"]
        completed = next(
            event["payload"]
            for event in run["events"]
            if event["kind"] == "finalization.completed"
        )
        assert completed["review_protocol"] == "json_schema"
        assert [row["criterion"] for row in completed["findings"]] == list(range(13))
        assert completed["independent_verification"] is False
        assert not any(event["kind"].startswith("tool.") for event in run["events"])
        assert len(transport.calls) == 2 and not transport.script
        assert transport.calls[0][1] == {"type": "json_object"}
        assert transport.calls[1][1]["type"] == "json_schema"
        assert client.get(f"{url}/draft").json() == draft
        assert client.get(f"{url}/versions").json() == versions


def test_committed_app_run_rejects_nine_slots_even_when_provider_ignores_schema(
    tmp_path: Path,
):
    with _bound_app(tmp_path) as (client, transport, pid, aid):
        url, version, draft, versions = _commit_review_loop(client, pid, aid)
        transport.script = [
            {"action": "final", "outputs": {"result": "Unpublished candidate"}},
            _review_result(9),
        ]
        run = _app_start(client, f"{url}/run", {"request": "Supplied facts"})
        assert run["status"] == "failed", run
        assert run["result"] is None
        assert run["version_id"] == version["version_id"]
        assert run["error"]["code"] == "agent_finalization_review_invalid"
        failed = next(
            event["payload"]
            for event in run["events"]
            if event["kind"] == "finalization.failed"
        )
        assert failed["review_protocol"] == "json_schema"
        assert failed["diagnostic"]["missing_criteria"] == [9, 10, 11, 12]
        assert failed["diagnostic"]["expected_count"] == 13
        assert failed["diagnostic"]["received_count"] == 9
        assert len(failed["diagnostic"]["valid_findings"]) == 9
        assert not any(
            event["kind"] in {"run.completed", "finalization.accepted"}
            or event["kind"].startswith("tool.")
            for event in run["events"]
        )
        assert len(transport.calls) == 2 and not transport.script
        assert transport.calls[1][1]["type"] == "json_schema"
        assert client.get(f"{url}/draft").json() == draft
        assert client.get(f"{url}/versions").json() == versions
