"""Factory HTTP generation reaches a committed, consent-gated CSV report.

Model transports are synthetic. Compilation, native CSV evidence, permissions,
approvals, filesystem writes, persistence, and Project file reads are real.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from tests.unit.local.test_gated_role_composition import _task
from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.contracts.task_structure import TaskStructure
from veyra_agent_platform.local.builder.task_structure_schema import (
    task_structure_projection,
)
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.client import RuntimeCompletion

from .test_factory_task_structure_planner import PlanningTransport, _completion
from .test_workflow_version_boundary import await_workflow
from .verified_runtime_model import verified_client

_GOAL = (
    "创建一个订单和付款 CSV 对账助手。用户选择两个文件，按订单号汇总金额，"
    "精确比较，保留重复记录和原始物理行号。报告包含差额、未匹配及空订单号。"
    "原文件不可修改，先独立检查报告，再让我确认，确认后只写入 reports。"
    "实际写文件还必须获得该次工具授权；拒绝时不要保存报告。"
)
_ORDERS = (
    b'order_id,order_amount,note\nA-100,0.10,"first line\nsecond line"\n'
    b"A-100,0.20,tail\nB-200,20.00,standard\nC-300,5.50,unpaid\n"
    b",7.00,blank key\nD-400,3.25,mismatch\n"
)
_PAYMENTS = (
    b"order_ref,payment_amount\nA-100,0.30\nB-200,18.50\n"
    b"P-900,8.00\n,2.00\nD-400,4.00\n"
)
_COMPARE = "veyra.tool.tabular.compare@1.0.0"
_COMPARE_INPUTS = "veyra.tool.tabular.compare@1.2.0"
_WRITE = "veyra.tool.filesystem.write@1.0.0"


def _csv_task(input_mode: str = "project_paths") -> TaskStructure:
    """A scripted semantic plan, never a scripted executable Source."""
    data = _task().to_dict()
    data.update(goal=_GOAL, summary="Read-only exact reconciliation, then gated saving")
    data["inputs"] = [
        {
            "name": "orders_path",
            "type": "file" if input_mode == "uploaded_files" else "string",
        },
        {
            "name": "payments_path",
            "type": "file" if input_mode == "uploaded_files" else "string",
        },
    ]
    reader = data["actors"][0]
    reader.update(
        role="CSV reconciliation",
        capabilities=["text_generation", "tabular_compare"],
        reason="Use native exact CSV comparison; never alter selected source files",
        inputs=data["inputs"],
    )
    data["stages"][0]["input_sources"] = {
        "orders_path": "input.orders_path",
        "payments_path": "input.payments_path",
    }
    data["stages"][1]["input_sources"] = {"result": "review.outcome"}
    data["execution_boundaries"][0].update(
        capability="tabular_compare", reason="Compute traceable facts from both CSVs"
    )
    data["execution_boundaries"][1]["checks"] = [
        "required_fields:report-text",
        "schema_valid",
        "constraint_match:result.summary_complete == true",
        "constraint_match:result.truncated == false",
    ]
    # A declined business decision returns the reviewed facts without a file.
    data["outputs"][1]["required"] = False
    data["outputs"].append(
        {"name": "outcome", "type": "object", "source": "review.outcome"}
    )
    data["constraints"] = [
        "Never modify either original CSV",
        "Write report files only inside reports after both approvals",
        "Compute exact totals with the native comparison tool, retaining row evidence",
    ]
    return TaskStructure.from_dict(data)


def _missing_writer_task(input_mode: str) -> TaskStructure:
    data = _csv_task(input_mode).to_dict()
    data["actors"] = data["actors"][:1]
    data["stages"] = data["stages"][:1]
    data["execution_boundaries"] = [data["execution_boundaries"][0]]
    data["outputs"] = [{"name": "report_path", "type": "string", "required": False}]
    data["filesystem_write_roots"] = []
    return TaskStructure.from_dict(data)


def _report(evidence: dict[str, Any]) -> str:
    """Render only the real tool observation; do not supply expected totals."""
    lines = [
        "# 订单与付款对账报告",
        "",
        f"订单文件：{evidence['left']['path']} · SHA-256 {evidence['left']['sha256']}",
        f"付款文件：{evidence['right']['path']} · "
        f"SHA-256 {evidence['right']['sha256']}",
        "",
        "差额方向：付款金额减订单金额。",
        "",
        "| 订单号 | 状态 | 订单合计 | 付款合计 | 差额 | 订单原始行 | 付款原始行 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for group in evidence["groups"]:
        cells = [
            group["key"],
            group["status"],
            group["left_total"],
            group["right_total"],
            group["difference"],
            json.dumps(group["left_rows"], ensure_ascii=False),
            json.dumps(group["right_rows"], ensure_ascii=False),
        ]
        lines.append(
            "| " + " | ".join("—" if v is None else str(v) for v in cells) + " |"
        )
    lines.extend(
        [
            "",
            "## 空订单号记录",
            json.dumps(evidence["blank_keys"], ensure_ascii=False),
            "",
            "## 汇总",
            json.dumps(evidence["counts"], ensure_ascii=False),
            json.dumps(evidence["totals"], ensure_ascii=False),
        ]
    )
    return "\n".join(lines) + "\n"


class ObservationDrivenRuntime:
    """Use native observations and the writer's real input mapping as model facts."""

    def __init__(self, input_mode: str = "project_paths") -> None:
        self.input_mode = input_mode
        self.compare_reference = (
            _COMPARE_INPUTS if input_mode == "uploaded_files" else _COMPARE
        )
        self.calls: list[Any] = []
        self.evidence: dict[str, Any] | None = None
        self.requested_path = ""
        self.requested_content = ""

    def models(self) -> tuple[str, ...]:
        return ("kimi-k3",)

    @staticmethod
    def _observation(messages: Any, reference: str) -> dict[str, Any]:
        prefix = f"Tool result for {reference}:\n"
        text = next(
            message["content"]
            for message in reversed(messages)
            if isinstance(message.get("content"), str)
            and message["content"].startswith(prefix)
        )
        return json.loads(text.removeprefix(prefix))

    def complete(self, messages: Any) -> RuntimeCompletion:
        self.calls.append(deepcopy(messages))
        turn = len(self.calls)
        if turn == 1:
            opening = messages[1]["content"]
            if self.input_mode == "project_paths":
                assert "orders-path: assets/orders.csv" in opening
                assert "payments-path: assets/payments.csv" in opening
                sources = {
                    "left_path": "assets/orders.csv",
                    "right_path": "assets/payments.csv",
                }
            else:
                assert "orders-path: [file orders.csv]" in opening
                assert "payments-path: [file payments.csv]" in opening
                assert "art_" not in opening
                sources = {
                    "left_source": {"input": "orders-path"},
                    "right_source": {"input": "payments-path"},
                }
            response = {
                "action": "tool",
                "tool": self.compare_reference,
                "arguments": {
                    **sources,
                    "left_key": "order_id",
                    "right_key": "order_ref",
                    "left_amount": "order_amount",
                    "right_amount": "payment_amount",
                    "include_all_groups": True,
                },
            }
        elif turn == 2:
            self.evidence = self._observation(messages, self.compare_reference)
            assert self.evidence["summary_complete"] is True
            assert self.evidence["truncated"] is False
            response = {
                "action": "final",
                "outputs": {
                    "report-text": _report(self.evidence),
                    "report-path": "reports/reconciliation.md",
                    "outcome": self.evidence,
                },
            }
        elif turn == 3:
            # Read the actual mapped approved payload, not the reader's local state.
            opening = messages[1]["content"]
            _, body = opening.split("report-text: ", 1)
            self.requested_content = body.split("\nreport-path: ", 1)[0]
            self.requested_path = opening.split("report-path: ", 1)[1].splitlines()[0]
            response = {
                "action": "tool",
                "tool": _WRITE,
                "arguments": {
                    "path": self.requested_path,
                    "content": self.requested_content,
                },
            }
        elif turn == 4:
            if "The user rejected the tool request" in messages[-1]["content"]:
                saved = {"written": False}
            else:
                saved = {
                    **self._observation(messages, _WRITE),
                    "path": self.requested_path,
                }
                assert saved["written"] is True
            response = {"action": "final", "outputs": {"saved-report": saved}}
        else:
            raise AssertionError("Unexpected extra Runtime model call")
        return RuntimeCompletion(
            content=json.dumps(response, ensure_ascii=False), finish_reason="stop"
        )


def _command(client: Any, url: str, run_id: str, command: str) -> dict[str, Any]:
    response = client.post(
        f"{url}/runs/{run_id}/commands",
        json={"command": command},
        headers={"Idempotency-Key": new_uuid7()},
    )
    assert response.status_code == 200, response.text
    return await_workflow(client, url, run_id)


@pytest.mark.parametrize("decision", ["approve", "business_reject", "tool_reject"])
@pytest.mark.parametrize("input_mode", ["project_paths", "uploaded_files"])
@pytest.mark.parametrize("generation_mode", ["first_valid", "repair_missing_writer"])
def test_factory_csv_product_preserves_evidence_and_requires_both_consents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    decision: str,
    input_mode: str,
    generation_mode: str,
) -> None:
    for name in (
        "MOONSHOT_API_KEY",
        "VEYRA_FACTORY_MODEL_BASE_URL",
        "VEYRA_FACTORY_MODEL_ID",
        "VEYRA_RUNTIME_MODEL_BASE_URL",
        "VEYRA_RUNTIME_MODEL_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    responses = [_completion("Ready to plan the specified CSV task")]
    if generation_mode == "repair_missing_writer":
        responses.extend(
            [
                _completion(
                    task_structure_projection(_missing_writer_task(input_mode))
                ),
                _completion(
                    {
                        "verdict": "incomplete",
                        "gaps": [
                            {
                                "requirement": (
                                    "Write the approved report only inside reports"
                                ),
                                "reason": (
                                    "The candidate has only a read-only role "
                                    "and no report writer"
                                ),
                            }
                        ],
                    }
                ),
            ]
        )
    responses.extend(
        [
            _completion(task_structure_projection(_csv_task(input_mode))),
            _completion({"verdict": "covered", "gaps": []}),
        ]
    )
    factory = PlanningTransport(responses)
    runtime = ObservationDrivenRuntime(input_mode)
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'mainline.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with verified_client(settings, runtime, factory_transport=factory) as client:
        created = client.post("/api/v1/projects", json={"name": "CSV reconciliation"})
        assert created.status_code == 201, created.text
        project = created.json()
        pid = project["project_id"]
        root = Path(project["root_path"])
        originals = {"orders.csv": _ORDERS, "payments.csv": _PAYMENTS}
        original_hashes = {
            filename: hashlib.sha256(content).hexdigest()
            for filename, content in originals.items()
        }
        selected: dict[str, Any] = {}
        uploaded: dict[str, Any] = {}
        if input_mode == "project_paths":
            resource = ResourceCatalog().detail("veyra.tool.tabular.compare", "1.0.0")
            bound = client.post(
                f"/api/v1/projects/{pid}/resources",
                json={key: resource[key] for key in ("reference", "content_hash")},
            )
            assert bound.status_code == 201, bound.text
        for filename, content in originals.items():
            field = filename.removesuffix(".csv") + "-path"
            if input_mode == "project_paths":
                imported = client.post(
                    f"/api/v1/projects/{pid}/files/materialize",
                    data={
                        "relative_path": f"assets/{filename}",
                        "expected_sha256": original_hashes[filename],
                        "expected_size": str(len(content)),
                    },
                    files={"file": (filename, content, "text/csv")},
                )
                assert imported.status_code == 201, imported.text
                selected[field] = imported.json()["relative_path"]
            else:
                imported = client.post(
                    f"/api/v1/projects/{pid}/artifacts",
                    files={"file": (filename, content, "text/csv")},
                )
                assert imported.status_code == 201, imported.text
                record = imported.json()
                assert record["sha256"] == original_hashes[filename]
                uploaded[filename] = record
                selected[field] = {
                    key: record[key]
                    for key in ("kind", "artifact_id", "media_type", "filename")
                }
        if input_mode == "uploaded_files":
            assert list((root / "assets").rglob("*")) == []
        created_session = client.post(
            f"/api/v1/projects/{pid}/factory/sessions", json={"goal": _GOAL}
        )
        assert created_session.status_code in {200, 201}, created_session.text
        sid = created_session.json()["session_id"]
        session_url = f"/api/v1/projects/{pid}/factory/sessions/{sid}"
        generated = client.post(f"{session_url}/generate")
        assert generated.status_code == 200, generated.text
        candidate = generated.json()
        assert candidate["state"] == "review", candidate
        assert candidate["proposal_preview"]["planning_source"] == "provider"
        expected_calls = 5 if generation_mode == "repair_missing_writer" else 3
        assert len(factory.calls) == expected_calls and factory.responses == []
        if generation_mode == "repair_missing_writer":
            repair = str(factory.calls[3])
            assert "report writer" in repair and _GOAL in repair
        assert client.get(f"/api/v1/projects/{pid}").json()["agents"] == []
        applied = client.post(f"{session_url}/apply-draft", json={"confirm": True})
        assert applied.status_code == 200, applied.text
        workflow_id = applied.json()["workflow"]["workflow_id"]
        url = f"/api/v1/projects/{pid}/workflows/{workflow_id}"
        draft = client.get(f"{url}/draft").json()
        calls = {
            node["id"]: node
            for node in draft["source"]["nodes"]
            if node["component_type"] == "AgentCall"
        }
        reader_id = calls["review"]["agent_ref"].split("@", 1)[0]
        writer_id = calls["write"]["agent_ref"].split("@", 1)[0]
        reader_source = client.get(
            f"/api/v1/projects/{pid}/agents/{reader_id}/draft"
        ).json()["source"]
        writer_source = client.get(
            f"/api/v1/projects/{pid}/agents/{writer_id}/draft"
        ).json()["source"]
        reader_permissions = reader_source["extensions"]["veyra"]["permissions"]
        writer_permissions = writer_source["extensions"]["veyra"]["permissions"]
        assert reader_permissions["filesystem_write_roots"] == []
        assert reader_permissions["tools"] == ["veyra.tool.tabular.compare"]
        assert runtime.compare_reference in reader_source["lock"]
        assert writer_permissions["tools"] == ["veyra.tool.filesystem.write"]
        assert writer_permissions["filesystem_write_roots"] == ["project/reports"]
        committed = client.post(
            f"{url}/commit",
            json={"expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert committed.status_code == 200, committed.text
        started = client.post(
            f"{url}/run",
            json={
                "inputs": {
                    calls["review"]["input_mapping"][field]: value
                    for field, value in selected.items()
                },
                "source": "committed",
                "version_id": committed.json()["version_id"],
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 200, started.text
        rid = started.json()["run_id"]
        waiting = await_workflow(client, url, rid)
        if waiting["status"] != "waiting" and waiting["children"]:
            child_id = waiting["children"][0]["child_run_id"]
            failed_child = client.get(
                f"/api/v1/projects/{pid}/agents/{reader_id}/runs/{child_id}"
            ).json()
            pytest.fail(f"Reader did not reach review: {failed_child['error']}")
        assert waiting["status"] == "waiting", waiting
        assert waiting["waiting"]["kind"] == "approval", waiting
        assert len(runtime.calls) == 2
        target = root / "reports/reconciliation.md"
        assert not target.exists() and not list(target.parent.glob("*"))
        evidence = runtime.evidence
        assert evidence is not None
        assert evidence["left"]["sha256"] == original_hashes["orders.csv"]
        assert evidence["right"]["sha256"] == original_hashes["payments.csv"]
        if input_mode == "uploaded_files":
            assert evidence["left"]["path"] == "input:orders-path (orders.csv)"
            assert evidence["right"]["path"] == "input:payments-path (payments.csv)"
            assert list((root / "assets").rglob("*")) == []
        groups = {group["key"]: group for group in evidence["groups"]}
        assert groups["A-100"]["difference"] == "0"
        assert groups["A-100"]["left_rows"] == [
            {"line_start": 2, "line_end": 3, "amount": "0.1"},
            {"line_start": 4, "line_end": 4, "amount": "0.2"},
        ]
        assert groups["B-200"]["difference"] == "-1.5"
        assert groups["B-200"]["left_rows"][0]["line_start"] == 5
        assert groups["B-200"]["right_rows"][0]["line_start"] == 3
        assert groups["D-400"]["difference"] == "0.75"
        assert groups["C-300"]["status"] == "left_only"
        assert groups["P-900"]["status"] == "right_only"
        assert evidence["blank_keys"]["left"][0]["line_start"] == 7
        assert evidence["blank_keys"]["right"][0]["line_start"] == 5
        assert any(
            event["kind"] == "verifier.result" and event["payload"]["passed"] is True
            for event in waiting["events"]
        )
        child = waiting["children"][0]
        reader_run = client.get(
            f"/api/v1/projects/{pid}/agents/{reader_id}/runs/{child['child_run_id']}"
        ).json()
        assert any(
            event["kind"] == "tool.completed"
            and event["payload"]["tool_reference"] == runtime.compare_reference
            and event["payload"]["output_digest"] == sha256_digest(evidence)
            for event in reader_run["events"]
        )
        current = _command(
            client, url, rid, "reject" if decision == "business_reject" else "approve"
        )
        if decision == "business_reject":
            assert current["status"] == "cancelled", current
            assert len(runtime.calls) == 2 and len(current["children"]) == 1
            assert current["result"] is None
        else:
            assert (
                current["status"] == "waiting" and current["waiting"]["kind"] == "agent"
            ), current
            assert len(runtime.calls) == 3
            assert runtime.requested_content == _report(evidence)
            assert runtime.requested_path == "reports/reconciliation.md"
            assert not target.exists() and not list(target.parent.glob("*"))
            pending = client.get(
                f"/api/v1/projects/{pid}/agents/{writer_id}/runs/{current['waiting']['child_run_id']}"
            ).json()
            assert any(
                event["kind"] == "approval.requested"
                and event["payload"].get("kind") == "tool_permission"
                and event["payload"].get("tool_reference") == _WRITE
                for event in pending["events"]
            ), pending
            assert not any(
                event["kind"] in {"tool.started", "tool.completed"}
                for event in pending["events"]
            )
            current = _command(
                client, url, rid, "reject" if decision == "tool_reject" else "approve"
            )
        if input_mode == "project_paths":
            assert {
                filename: hashlib.sha256(
                    (root / "assets" / filename).read_bytes()
                ).hexdigest()
                for filename in originals
            } == original_hashes
        else:
            assert list((root / "assets").rglob("*")) == []
            for filename, record in uploaded.items():
                artifact_url = (
                    f"/api/v1/projects/{pid}/artifacts/{record['artifact_id']}"
                )
                original = client.get(f"{artifact_url}/content")
                assert original.status_code == 200, original.text
                assert original.content == originals[filename]
                assert (
                    hashlib.sha256(original.content).hexdigest()
                    == original_hashes[filename]
                )
                assert (
                    client.get(artifact_url).json()["sha256"]
                    == original_hashes[filename]
                )
        if decision != "business_reject":
            writer_run = client.get(
                f"/api/v1/projects/{pid}/agents/{writer_id}/runs/{current['children'][-1]['child_run_id']}"
            ).json()
            assert any(
                event["kind"] == "approval.resolved"
                and event["payload"]["decision"]
                == ("rejected" if decision == "tool_reject" else "approved")
                for event in writer_run["events"]
            )
            completed_writes = [
                event["payload"]
                for event in writer_run["events"]
                if event["kind"] == "tool.completed"
            ]
            if decision == "tool_reject":
                assert completed_writes == []
            else:
                assert len(completed_writes) == 1
                receipt = completed_writes[0]
                assert receipt["tool_reference"] == _WRITE
                assert receipt["authorization"] == "allowed"
                assert receipt["relative_path"] == "reports/reconciliation.md"
                assert receipt["output_digest"] == sha256_digest({"written": True})
        if decision != "approve":
            if decision == "tool_reject":
                assert current["status"] == "verified", current
                assert current["result"]["savedreport"] == {"written": False}
            else:
                assert current["status"] == "cancelled", current
                assert current["result"] is None
            assert not target.exists() and not list(target.parent.glob("*"))
            return
        assert current["status"] == "verified", current
        assert current["result"]["outcome"] == evidence
        assert current["result"]["savedreport"] == {
            "written": True,
            "path": "reports/reconciliation.md",
        }
        assert target.read_text(encoding="utf-8") == _report(evidence)
        opened = client.get(
            f"/api/v1/projects/{pid}/files/content",
            params={"path": "reports/reconciliation.md"},
        )
        assert opened.status_code == 200, opened.text
        assert opened.json()["text"] == _report(evidence)
