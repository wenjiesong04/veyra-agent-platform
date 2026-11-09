"""Committed scripted Runs exercise native input protection without a Provider."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.client import (
    RuntimeCompletion,
    RuntimeProviderError,
)

from .test_loop_resource_truth import (
    _attach,
    _client,
    _loop_source,
    _pin,
    _set_io,
)
from .test_runtime_routes import (
    ScriptedRuntimeTransport,
    _await_run,
    _command_until_settled,
)
from .test_workflow_version_boundary import await_workflow, save

READ = "veyra.tool.filesystem.read@1.0.0"
WRITE = "veyra.tool.filesystem.write@1.0.0"
SHELL = "veyra.tool.shell.exec@1.0.0"
INPUT = "reports/input.csv"
ORIGINAL = b"sku,quantity\r\nA,2\r\nB,3\r\n"


class ObservedTransport(ScriptedRuntimeTransport):
    def __init__(self, actions: Sequence[dict[str, Any]], *, fail_first: bool = False):
        super().__init__([json.dumps(action) for action in actions])
        self.before_complete: Callable[[], None] | None = None
        self.fail_first = fail_first

    def complete(self, messages: object) -> RuntimeCompletion:
        if self.before_complete is not None:
            self.before_complete()
        if self.fail_first:
            self.fail_first = False
            self.calls.append(messages)
            raise RuntimeProviderError(
                "runtime_provider_error", "Scripted interruption"
            )
        return super().complete(messages)


def _tool(reference: str, **arguments: Any) -> dict[str, Any]:
    return {"action": "tool", "tool": reference, "arguments": arguments}


def _final(result: str = "finished") -> dict[str, Any]:
    return {"action": "final", "outputs": {"result": result}}


def _resource(reference: str) -> dict[str, Any]:
    return ResourceCatalog().detail(*reference.rsplit("@", 1))


def _source(
    *references: str,
    protect: bool = True,
    explicit_input: bool = False,
    grant_input_read: bool = True,
    slug: str = "protected-runner",
) -> dict[str, Any]:
    source = _attach(
        _set_io(
            _loop_source("Return a short response"),
            {"inputpath": "string"},
            {"result": "string"},
        ),
        *(_resource(reference) for reference in references),
    )
    source.update(agent_id=new_uuid7(), slug=slug, name=slug)
    veyra = source["extensions"]["veyra"]
    veyra["max_turns"] = 12
    permissions = veyra["permissions"]
    permissions["protect_input_files"] = protect
    if explicit_input:
        permissions["protected_input_fields"] = ["inputpath"]
        if grant_input_read:
            permissions["filesystem_read_roots"] = list(
                dict.fromkeys(
                    [
                        *(permissions.get("filesystem_read_roots") or []),
                        "project/reports",
                    ]
                )
            )
    if WRITE in references:
        permissions["filesystem_write_roots"] = ["project/reports"]
    return source


def _commit(client: TestClient, url: str) -> dict[str, Any]:
    response = client.get(f"{url}/draft")
    assert response.status_code == 200, response.text
    draft = response.json()
    committed = client.post(
        f"{url}/commit",
        json={"expected_revision": draft["revision"]},
        headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
    )
    assert committed.status_code == 200, committed.text
    return committed.json()


def _project(
    client: TestClient, sources: Sequence[dict[str, Any]], references: Sequence[str]
) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]], Path]:
    created = client.post(
        "/api/v1/projects", json={"name": "Input protection", "agents": list(sources)}
    )
    assert created.status_code == 201, created.text
    project = created.json()
    _pin(client, project["project_id"], *(_resource(ref) for ref in references))
    versions = []
    for source in sources:
        agent = next(
            item for item in project["agents"] if item["slug"] == source["slug"]
        )
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}"
        versions.append((url, _commit(client, url)))
    path = Path(project["root_path"]) / INPUT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ORIGINAL)
    return project, versions, path


def _start(client: TestClient, url: str, version: dict[str, Any]) -> dict[str, Any]:
    started = client.post(
        f"{url}/run",
        json={
            "inputs": {"inputpath": INPUT},
            "source": "committed",
            "version_id": version["version_id"],
        },
        headers={"Idempotency-Key": new_uuid7()},
    )
    assert started.status_code == 200, started.text
    return _await_run(client, f"{url}/run", started.json()["run_id"])


def _finish(client: TestClient, url: str, current: dict[str, Any]) -> dict[str, Any]:
    for _ in range(4):
        if current["status"] != "waiting":
            return current
        current = _command_until_settled(
            client, f"{url}/run", current["run_id"], "approve"
        )
    raise AssertionError(f"Run did not leave approval waits: {current}")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _protected_events(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [event for event in run["events"] if event["kind"] == "input.protected"]


def _assert_protected_failure(run: dict[str, Any], path: Path) -> None:
    assert run["status"] == "failed", run
    assert run["error"]["code"] == "input_file_protected", run
    assert _digest(path) == hashlib.sha256(ORIGINAL).hexdigest()
    assert any(
        event["kind"] == "node.failed"
        and event["payload"].get("code") == "input_file_protected"
        for event in run["events"]
    ), run
    assert not any(
        event["kind"] == "tool.completed"
        and event["payload"].get("tool_reference") == WRITE
        for event in run["events"]
    ), run


def test_explicit_input_is_protected_before_the_first_model_write(
    tmp_path: Path,
) -> None:
    source = _source(WRITE, explicit_input=True)
    transport = ObservedTransport([_tool(WRITE, path=INPUT, content="overwritten")])
    snapshots: list[list[dict[str, Any]]] = []
    with _client(tmp_path, transport) as client:
        project, versions, path = _project(client, [source], [WRITE])
        url, version = versions[0]
        repository = client.app.state.runtime.repository
        transport.before_complete = lambda: snapshots.append(
            repository.run_events(repository.runs(url.rsplit("/", 1)[1])[0]["run_id"])
        )
        current = _finish(client, url, _start(client, url, version))
        _assert_protected_failure(current, path)
        assert len(transport.calls) == 1
        assert snapshots
        protected = [
            event for event in snapshots[0] if event["kind"] == "input.protected"
        ]
        assert len(protected) == 1
        assert protected[0]["payload"]["relative_path"] == INPUT
        assert protected[0]["payload"]["sha256"] == _digest(path)
        assert not any(event["kind"] == "tool.started" for event in snapshots[0])
        assert str(Path(project["root_path"])) not in json.dumps(protected)


def test_explicit_input_without_read_scope_fails_before_open_model_or_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(WRITE, explicit_input=True, grant_input_read=False)
    transport = ObservedTransport([_tool(WRITE, path=INPUT, content="overwritten")])
    with _client(tmp_path, transport) as client:
        _, versions, path = _project(client, [source], [WRITE])
        url, version = versions[0]
        read_opens: list[Path] = []
        real_open = os.open

        def observed_open(target: Any, flags: int, *args: Any, **kwargs: Any) -> int:
            if (
                isinstance(target, str | os.PathLike)
                and Path(target).resolve() == path.resolve()
                and flags & os.O_ACCMODE == os.O_RDONLY
            ):
                read_opens.append(Path(target))
            return real_open(target, flags, *args, **kwargs)

        monkeypatch.setattr(
            "veyra_agent_platform.local.runtime.file_sources.os.open", observed_open
        )
        failed = _start(client, url, version)

        assert failed["status"] == "failed", failed
        assert failed["error"]["code"] == "tool_path_denied", failed
        assert read_opens == []
        assert transport.calls == []
        assert _protected_events(failed) == []
        assert not any(event["kind"] == "tool.started" for event in failed["events"])
        assert _digest(path) == hashlib.sha256(ORIGINAL).hexdigest()


def test_native_read_protects_actual_input_before_later_write(tmp_path: Path) -> None:
    source = _source(READ, WRITE)
    transport = ObservedTransport(
        [_tool(READ, path=INPUT), _tool(WRITE, path=INPUT, content="overwritten")]
    )
    with _client(tmp_path, transport) as client:
        _, versions, path = _project(client, [source], [READ, WRITE])
        url, version = versions[0]
        current = _finish(client, url, _start(client, url, version))
        _assert_protected_failure(current, path)
        assert len(transport.calls) == 2
        events = current["events"]
        protected = _protected_events(current)
        assert len(protected) == 1
        read_completed = next(
            event
            for event in events
            if event["kind"] == "tool.completed"
            and event["payload"]["tool_reference"] == READ
        )
        assert protected[0]["sequence"] < read_completed["sequence"]
        prefix = f"Tool result for {READ}:\n"
        observation = next(
            message["content"]
            for message in transport.calls[1]
            if isinstance(message.get("content"), str)
            and message["content"].startswith(prefix)
        )
        assert (
            json.loads(observation.removeprefix(prefix))["content"] == ORIGINAL.decode()
        )


def test_native_write_rejects_a_hardlink_to_a_protected_input(tmp_path: Path) -> None:
    alias = "reports/result.csv"
    source = _source(READ, WRITE)
    transport = ObservedTransport(
        [_tool(READ, path=INPUT), _tool(WRITE, path=alias, content="overwritten")]
    )
    with _client(tmp_path, transport) as client:
        project, versions, path = _project(client, [source], [READ, WRITE])
        linked = Path(project["root_path"]) / alias
        os.link(path, linked)
        url, version = versions[0]
        current = _finish(client, url, _start(client, url, version))
        _assert_protected_failure(current, path)
        assert linked.stat().st_ino == path.stat().st_ino
        assert _digest(linked) == _digest(path)


def test_workflow_children_share_inputs_protected_by_the_reader(tmp_path: Path) -> None:
    reader = _source(READ, protect=False, slug="reader")
    writer = _source(WRITE, protect=False, slug="writer")
    transport = ObservedTransport(
        [
            _tool(READ, path=INPUT),
            _final("read complete"),
            _tool(WRITE, path=INPUT, content="overwritten by second Agent"),
        ]
    )
    with _client(tmp_path, transport) as client:
        project, versions, path = _project(client, [reader, writer], [READ, WRITE])
        project_id = project["project_id"]
        created = client.post(
            f"/api/v1/projects/{project_id}/workflows",
            json={"name": "Shared input protection"},
        )
        assert created.status_code == 201, created.text
        workflow_id = created.json()["workflow_id"]
        url = f"/api/v1/projects/{project_id}/workflows/{workflow_id}"
        draft = client.get(f"{url}/draft").json()
        source = draft["source"]
        refs = [
            f"{agent_url.rsplit('/', 1)[1]}@{version['version_id']}"
            for agent_url, version in versions
        ]
        source.update(
            inputs={"inputpath": "string"},
            outputs={"result": "string"},
            nodes=[
                {"id": "start", "component_type": "Start"},
                {
                    "id": "read",
                    "component_type": "AgentCall",
                    "agent_ref": refs[0],
                    "input_mapping": {"inputpath": "inputpath"},
                    "output_mapping": {"result": "reader_result"},
                },
                {
                    "id": "write",
                    "component_type": "AgentCall",
                    "agent_ref": refs[1],
                    "input_mapping": {"inputpath": "inputpath"},
                    "output_mapping": {"result": "result"},
                },
                {"id": "output", "component_type": "Output", "output_name": "result"},
            ],
            transitions=[
                {"from": "start", "port": "next", "to": "read"},
                {"from": "read", "port": "next", "to": "write"},
                {"from": "write", "port": "next", "to": "output"},
            ],
            lock={
                reference: version["source_hash"]
                for reference, (_, version) in zip(refs, versions, strict=True)
            },
            ui={
                "positions": {
                    name: {"x": index * 200, "y": 0}
                    for index, name in enumerate(("start", "read", "write", "output"))
                }
            },
        )
        source["extensions"]["veyra"]["permissions"] = {
            "tools": [READ.rsplit("@", 1)[0], WRITE.rsplit("@", 1)[0]],
            "network_hosts": [],
            "filesystem_read_roots": ["project"],
            "filesystem_write_roots": ["project/reports"],
            "shell_workspace_only": False,
            "protect_input_files": True,
        }
        save(client, url, draft)
        version = _commit(client, url)
        started = client.post(
            f"{url}/run",
            json={
                "inputs": {"inputpath": INPUT},
                "source": "committed",
                "version_id": version["version_id"],
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 200, started.text
        run_id = started.json()["run_id"]
        current = await_workflow(client, url, run_id)
        assert current["status"] == "waiting", current
        approval = client.post(
            f"{url}/runs/{run_id}/commands",
            json={"command": "approve"},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert approval.status_code == 200, approval.text
        current = await_workflow(client, url, run_id)
        assert current["status"] == "failed", current
        assert current["error"]["code"] == "workflow_agent_failed", current
        assert len(current["children"]) == 2
        children = [
            client.get(
                f"/api/v1/projects/{project_id}/agents/{child['agent_id']}/runs/{child['child_run_id']}"
            ).json()
            for child in current["children"]
        ]
        assert children[0]["status"] == "unverified", children[0]
        _assert_protected_failure(children[1], path)
        for child in children:
            created_event = next(
                event for event in child["events"] if event["kind"] == "run.created"
            )
            assert created_event["payload"]["input_protection"] == {
                "scope_kind": "workflow",
                "scope_run_id": run_id,
            }
            assert _protected_events(child) == []
        protected = _protected_events(current)
        assert len(protected) == 1
        assert protected[0]["payload"]["relative_path"] == INPUT
        assert protected[0]["payload"]["sha256"] == _digest(path)


def test_editing_agent_can_modify_read_input_when_protection_is_disabled(
    tmp_path: Path,
) -> None:
    edited = "sku,quantity\nA,7\n"
    source = _source(READ, WRITE, protect=False)
    transport = ObservedTransport(
        [_tool(READ, path=INPUT), _tool(WRITE, path=INPUT, content=edited), _final()]
    )
    with _client(tmp_path, transport) as client:
        _, versions, path = _project(client, [source], [READ, WRITE])
        url, version = versions[0]
        current = _finish(client, url, _start(client, url, version))
        assert current["status"] == "unverified", current
        assert path.read_bytes() == edited.encode()
        assert _digest(path) != hashlib.sha256(ORIGINAL).hexdigest()
        assert _protected_events(current) == []
        assert not any(
            "input_protection" in event["payload"]
            for event in current["events"]
            if event["kind"] == "run.created"
        )


def test_native_output_can_be_read_back_and_updated_in_the_same_run(
    tmp_path: Path,
) -> None:
    output = "reports/result.csv"
    source = _source(READ, WRITE)
    transport = ObservedTransport(
        [
            _tool(READ, path=INPUT),
            _tool(WRITE, path=output, content="first report"),
            _tool(READ, path=output),
            _tool(WRITE, path=output, content="final report"),
            _final(),
        ]
    )
    with _client(tmp_path, transport) as client:
        project, versions, path = _project(client, [source], [READ, WRITE])
        url, version = versions[0]
        current = _finish(client, url, _start(client, url, version))
        assert current["status"] == "unverified", current
        assert (Path(project["root_path"]) / output).read_text() == "final report"
        assert _digest(path) == hashlib.sha256(ORIGINAL).hexdigest()
        assert [
            event["payload"]["relative_path"] for event in _protected_events(current)
        ] == [INPUT]
        assert (
            sum(
                event["kind"] == "tool.completed"
                and event["payload"]["tool_reference"] == WRITE
                for event in current["events"]
            )
            == 2
        )
        assert any(
            event["kind"] == "input.output_created"
            and event["payload"]["relative_path"] == output
            for event in current["events"]
        )


def test_retry_inherits_the_original_scope_and_protected_inputs(tmp_path: Path) -> None:
    source = _source(WRITE, explicit_input=True)
    transport = ObservedTransport(
        [_tool(WRITE, path=INPUT, content="overwritten on retry")], fail_first=True
    )
    with _client(tmp_path, transport) as client:
        _, versions, path = _project(client, [source], [WRITE])
        url, version = versions[0]
        failed = _start(client, url, version)
        assert failed["status"] == "failed", failed
        assert failed["error"]["code"] == "runtime_provider_error"
        assert len(_protected_events(failed)) == 1
        assert not any(event["kind"] == "tool.started" for event in failed["events"])
        retried = _command_until_settled(
            client, f"{url}/run", failed["run_id"], "retry"
        )
        assert retried["run_id"] != failed["run_id"]
        current = _finish(client, url, retried)
        _assert_protected_failure(current, path)
        created = next(
            event for event in current["events"] if event["kind"] == "run.created"
        )
        assert created["payload"]["input_protection"] == {
            "scope_kind": "agent",
            "scope_run_id": failed["run_id"],
        }
        assert _protected_events(current) == []
        ancestor = client.get(f"{url}/runs/{failed['run_id']}").json()
        assert len(_protected_events(ancestor)) == 1


@pytest.mark.parametrize("adapter_kind", ["shell", "untrusted_adapter"])
def test_protected_run_rejects_unenforceable_adapter_before_effects(
    tmp_path: Path, adapter_kind: str
) -> None:
    called: list[dict[str, Any]] = []

    def untrusted_adapter(**kwargs: Any) -> Any:
        called.append(kwargs)
        (kwargs["project_root"] / INPUT).write_bytes(b"unauthorized mutation")
        raise AssertionError("Untrusted adapter must not be dispatched")

    reference = SHELL if adapter_kind == "shell" else WRITE
    source = _source(reference, explicit_input=True)
    action = (
        _tool(SHELL, command="printf overwritten > reports/input.csv")
        if adapter_kind == "shell"
        else _tool(WRITE, path=INPUT, content="overwritten")
    )
    transport = ObservedTransport([action])
    kwargs = (
        {"tool_adapters": {"veyra.runtime.filesystem.write": untrusted_adapter}}
        if adapter_kind == "untrusted_adapter"
        else {}
    )
    with _client(tmp_path, transport, **kwargs) as client:
        _, versions, path = _project(client, [source], [reference])
        url, version = versions[0]
        current = _start(client, url, version)
        assert current["status"] == "failed", current
        assert current["error"]["code"] == "input_protection_not_enforceable", current
        assert _digest(path) == hashlib.sha256(ORIGINAL).hexdigest()
        assert called == []
        assert transport.calls == []
        assert not any(event["kind"] == "tool.started" for event in current["events"])
