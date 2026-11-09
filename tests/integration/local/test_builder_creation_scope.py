from __future__ import annotations

import json

import pytest

from tests.integration.local.test_builder_conversations import (
    ResolveThenProviderError,
    _turn,
)
from tests.integration.local.test_builder_resolution import intent
from tests.integration.local.test_edit_proposal_routes import _target
from tests.integration.local.test_factory_routes import (
    ScriptedKimiTransport,
    _client,
    _completion,
)


@pytest.mark.parametrize("kind", ["agent", "workflow"])
def test_new_product_can_contain_new_companions_without_existing_mutations(
    tmp_path, kind
):
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project, url, draft = _target(client, "agent")
        request = f"创建一个{kind}，分析员与独立复核员协作，确认后交付。"
        before = client.get(f"/api/v1/projects/{project}").json()
        transport.completions.append(
            _completion(
                json.dumps(
                    intent(
                        intent="create",
                        create_kind=kind,
                        multi_object=True,
                        creation_scope="single_product",
                    )
                )
            )
        )
        response = client.post(
            f"/api/v1/projects/{project}/builder/resolve",
            json={"content": request, "locale": "zh"},
        )
        assert response.status_code == 200, response.text
        resolved = response.json()
        assert resolved["status"] == "resolved"
        assert resolved["decision_reason"] == "single_product_creation"
        assert resolved["model_multi_object"] is True
        assert resolved["creation_scope"] == "single_product"
        assert resolved["instruction"] == request
        assert resolved["targets"] == []
        assert client.get(f"/api/v1/projects/{project}").json() == before
        assert client.get(f"{url}/draft").json() == draft
        context = json.loads(transport.calls[0][0][1]["content"])
        assert context["authority"]["multi_object_mutation"] is False
        assert context["authority"]["composite_product_creation"]
        assert "new companion Agents" in transport.calls[0][0][0]["content"]


@pytest.mark.parametrize("multi_object", [False, True])
def test_independent_products_are_not_silently_merged(tmp_path, multi_object):
    transport = ScriptedKimiTransport(
        [
            _completion(
                json.dumps(
                    intent(
                        intent="create",
                        create_kind="workflow",
                        creation_scope="independent_products",
                        multi_object=multi_object,
                    )
                )
            )
        ]
    )
    with _client(tmp_path, transport) as client:
        project, url, draft = _target(client, "agent")
        payload = _turn(
            client,
            project,
            content="分别创建一个对账助手和一个独立的研究工作流。",
            locale="zh",
        ).json()
        operation = payload["operations"][0]
        assert payload["factory_session"] is None
        assert operation["proposal_id"] is None
        assert (
            operation["diagnostic"]["decision_reason"]
            == "independent_products_requested"
        )
        assert operation["diagnostic"]["resolution_status"] == "unsupported"
        assert "resolution_json" not in operation["diagnostic"]
        assert len(transport.calls) == 1
        assert client.get(f"{url}/draft").json() == draft


def test_legacy_ambiguous_multi_object_create_asks_about_scope_not_missing_target(
    tmp_path,
):
    transport = ScriptedKimiTransport(
        [
            _completion(
                json.dumps(
                    intent(intent="create", create_kind="workflow", multi_object=True)
                )
            )
        ]
    )
    with _client(tmp_path, transport) as client:
        project, url, draft = _target(client, "agent")
        response = client.post(
            f"/api/v1/projects/{project}/builder/resolve",
            json={"content": "创建分析与复核角色", "locale": "zh"},
        ).json()
        assert response["status"] == "clarification"
        assert response["decision_reason"] == "creation_scope_ambiguous"
        assert "一个 Workflow" in response["message"]
        assert "目标对象" not in response["message"]
        assert client.get(f"{url}/draft").json() == draft


@pytest.mark.parametrize("operation", ["create", "edit"])
def test_new_product_scope_never_authorizes_changes_to_existing_objects(
    tmp_path, operation
):
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project, url, draft = _target(client, "agent")
        transport.completions.append(
            _completion(
                json.dumps(
                    intent(
                        target_id=draft["source"]["agent_id"],
                        intent=operation,
                        create_kind="workflow" if operation == "create" else None,
                        multi_object=True,
                        creation_scope="single_product",
                    )
                )
            )
        )
        response = client.post(
            f"/api/v1/projects/{project}/builder/resolve",
            json={"content": "Create a Workflow and modify Editable Agent."},
        ).json()
        assert response["status"] == "unsupported"
        assert response["decision_reason"] == (
            "creation_with_existing_mutations"
            if operation == "create"
            else "multi_object_edit"
        )
        assert client.get(f"{url}/draft").json() == draft


def test_workflow_creation_reaches_planning_and_retains_safe_scope_diagnostics(
    tmp_path,
):
    transport = ScriptedKimiTransport(
        [
            _completion(
                json.dumps(
                    intent(
                        intent="create",
                        create_kind="workflow",
                        multi_object=True,
                        creation_scope="single_product",
                    )
                )
            ),
            _completion("Ready for a proposal."),
        ]
    )
    with _client(tmp_path, transport) as client:
        project, url, draft = _target(client, "agent")
        content = (
            "创建一个商品包装设计流程。先让商品分析 Agent 分析上传的商品图片，"
            "再让市场研究 Agent 调研竞品，然后让包装设计 Agent 提出设计，"
            "我确认后再生成最终包装效果图。"
        )
        payload = _turn(client, project, content=content, locale="zh").json()
        operation = payload["operations"][0]
        assert operation["status"] == "waiting", payload
        assert operation["kind"] == "create_workflow"
        assert operation["proposal_id"] is not None
        assert operation["diagnostic"]["creation_scope"] == "single_product"
        assert operation["diagnostic"]["model_multi_object"] == "True"
        assert operation["diagnostic"]["decision_reason"] == "single_product_creation"
        assert "resolution_json" not in operation["diagnostic"]
        assert not any(content in value for value in operation["diagnostic"].values())
        types = [
            node["component_type"]
            for node in payload["factory_session"]["blueprint"]["nodes"]
        ]
        assert types.count("AgentCall") >= 3
        assert "HumanApproval" in types
        assert client.get(f"{url}/draft").json() == draft
        restored = client.get(
            f"/api/v1/projects/{project}/builder/conversations/"
            f"{payload['conversation']['conversation_id']}"
        ).json()
        assert restored["operations"][0]["diagnostic"] == operation["diagnostic"]


def test_failed_creation_keeps_private_resolution_out_of_public_facts(tmp_path):
    transport = ResolveThenProviderError(
        "factory_timeout",
        "Factory model service timed out",
        {},
        intent(
            intent="create",
            create_kind="workflow",
            multi_object=True,
            creation_scope="single_product",
        ),
    )
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        payload = _turn(
            client, project, content="创建一个分析与复核 Workflow。", locale="zh"
        ).json()
        operation = payload["operations"][0]
        assert operation["status"] == "failed"
        assert operation["diagnostic"]["decision_reason"] == "single_product_creation"
        assert "resolution_json" not in operation["diagnostic"]
        failed_events = [
            event
            for event in operation["events"]
            if event["kind"] == "builder.operation.failed"
        ]
        assert failed_events
        assert all("resolution_json" not in event["facts"] for event in failed_events)
        failures = [
            message for message in payload["messages"] if message["kind"] == "failure"
        ]
        assert failures
        assert all("resolution_json" not in message["payload"] for message in failures)
        with client.app.state.repository.transaction() as connection:
            row = connection.execute(
                "SELECT diagnostic_json FROM builder_operations WHERE operation_id = ?",
                (operation["operation_id"],),
            ).fetchone()
        saved = json.loads(json.loads(row["diagnostic_json"])["resolution_json"])
        assert saved["creation_scope"] == "single_product"
        assert saved["model_multi_object"] is True
