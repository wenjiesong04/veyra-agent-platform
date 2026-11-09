"""Native path effects honor committed Project subdirectory permissions."""

from dataclasses import replace
from pathlib import Path

import pytest

from veyra_agent_platform.contracts.agent import (
    FlowNode,
    PermissionContract,
)
from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.filesystem_scope import (
    filesystem_roots_satisfied,
    normalize_project_scope,
    path_in_project_scopes,
)
from veyra_agent_platform.local.builder.agent_loop_compiler import compile_loop_agent
from veyra_agent_platform.local.builder.specification import infer_agent_specification
from veyra_agent_platform.local.library.dependencies import _permission_detail
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.tools import ToolRuntime, ToolRuntimeError


def _case(resource_id: str, *, read=(), write=()):
    catalog = ResourceCatalog()
    resource = catalog.detail(resource_id, "1.0.0")
    spec = infer_agent_specification("Translate the supplied request")
    source = compile_loop_agent(spec, catalog, requirement=spec.goal)
    source = replace(
        source,
        lock={**source.lock, resource["reference"]: resource["content_hash"]},
        permissions=PermissionContract(
            network_hosts=(),
            tools=(resource_id,),
            filesystem_read_roots=tuple(read),
            filesystem_write_roots=tuple(write),
        ),
    )
    node = FlowNode.from_dict(
        {"id": "tool", "component_type": "Tool", "uses": resource["reference"]}
    )
    return catalog, resource, source, node


@pytest.mark.parametrize(
    "scope", ["project", "project/reports", "project/reports/2026"]
)
def test_canonical_scopes(scope: str) -> None:
    assert normalize_project_scope(scope) == scope


@pytest.mark.parametrize(
    "scope",
    [
        "/tmp",
        "reports",
        "project/",
        "project/../assets",
        "project/reports/../assets",
        "project/reports//daily",
        "project/reports/./daily",
        "project/reports/",
        "project/C:/private",
        "project/reports/D:/private",
        "project/reports/file:stream",
        "project/.env",
        "project/private.key",
        "project/reports\\daily",
        "project/reports\x00",
        "project/ reports",
    ],
)
def test_invalid_scope_is_not_a_project_grant(scope: str) -> None:
    with pytest.raises(ContractValidationError):
        normalize_project_scope(scope)
    assert not filesystem_roots_satisfied(["project"], [scope], allow_subscopes=True)


def test_scope_containment_uses_directory_segments_and_keeps_root_compatibility() -> (
    None
):
    assert path_in_project_scopes("reports/daily/result.md", ["project/reports"])
    assert not path_in_project_scopes("reports-old/result.md", ["project/reports"])
    assert not path_in_project_scopes("assets/orders.csv", ["project/reports"])
    assert path_in_project_scopes("notes/result.md", ["project"])
    assert path_in_project_scopes(".", ["project"], allow_root=True)
    assert not path_in_project_scopes(".", ["project/reports"], allow_root=True)


@pytest.mark.parametrize(
    "adapter",
    [
        "veyra.runtime.filesystem.write",
        "veyra.runtime.filesystem.read",
        "veyra.runtime.filesystem.list",
        "veyra.runtime.filesystem.search",
        "veyra.runtime.tabular.compare",
    ],
)
def test_library_accepts_native_scopes_but_not_opaque_executors(adapter: str) -> None:
    catalog, resource, source, _ = _case(
        "veyra.tool.filesystem.write",
        read=("project/reports",),
        write=("project/reports",),
    )
    del catalog
    required = resource["required_permissions"]
    assert _permission_detail(source, required, adapter=adapter) is None
    for opaque in (
        None,
        "veyra.runtime.shell.exec",
        "veyra.runtime.mcp.call",
        "custom.files.write",
    ):
        assert _permission_detail(source, required, adapter=opaque) is not None


def test_scoped_write_succeeds_but_denies_outside_paths_before_mkdir(
    tmp_path: Path,
) -> None:
    catalog, resource, source, node = _case(
        "veyra.tool.filesystem.write", write=("project/reports",)
    )
    runtime = ToolRuntime(catalog)
    values = {"path": "reports/daily/report.md", "content": "synthetic report"}
    auth = runtime.authorize(source=source, node=node, values=values)
    assert auth.decision == "allowed" and auth.approval_required
    result = runtime.execute(
        project_root=tmp_path,
        source=source,
        node=node,
        values=values,
        authorization=auth,
        approved=True,
    )
    assert result.receipt["relative_path"] == "reports/daily/report.md"
    assert (tmp_path / values["path"]).read_text() == "synthetic report"
    assert (
        catalog.detail(resource["resource_id"], "1.0.0")["content_hash"]
        == resource["content_hash"]
    )
    for path in (
        "assets/new/report.md",
        "reports-old/new/report.md",
        "../outside.md",
        "/outside.md",
        "reports/.env",
    ):
        denied = runtime.authorize(
            source=source, node=node, values={"path": path, "content": "no"}
        )
        assert denied.decision == "denied"
        with pytest.raises(ToolRuntimeError) as caught:
            runtime.execute(
                project_root=tmp_path,
                source=source,
                node=node,
                values={"path": path, "content": "no"},
                authorization=denied,
                approved=True,
            )
        assert caught.value.code == "tool_path_denied"
    assert not (tmp_path / "assets").exists()
    assert not (tmp_path / "reports-old").exists()


def test_execution_rechecks_scope_after_authorization_and_approval(
    tmp_path: Path,
) -> None:
    catalog, _, source, node = _case("veyra.tool.filesystem.write", write=("project",))
    runtime = ToolRuntime(catalog)
    values = {"path": "assets/new/report.md", "content": "no"}
    auth = runtime.authorize(source=source, node=node, values=values)
    assert auth.decision == "allowed"
    narrowed = replace(
        source,
        permissions=replace(
            source.permissions, filesystem_write_roots=("project/reports",)
        ),
    )
    with pytest.raises(ToolRuntimeError) as caught:
        runtime.execute(
            project_root=tmp_path,
            source=narrowed,
            node=node,
            values=values,
            authorization=auth,
            approved=True,
        )
    assert caught.value.code == "tool_path_denied"
    assert not (tmp_path / "assets").exists()


@pytest.mark.parametrize(
    "resource_id,values",
    [
        ("veyra.tool.filesystem.read", {"path": "reports/input.txt"}),
        ("veyra.tool.filesystem.list", {"path": "reports"}),
        ("veyra.tool.filesystem.search", {"path": "reports", "query": "marker"}),
    ],
)
def test_native_read_operations_stay_in_the_granted_directory(
    tmp_path: Path, resource_id: str, values: dict
) -> None:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports/input.txt").write_text("public marker")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/secret.txt").write_text("outside marker")
    (tmp_path / "reports/.env").mkdir()
    (tmp_path / "reports/.env/hidden.txt").write_text("private marker")
    catalog, _, source, node = _case(resource_id, read=("project/reports",))
    runtime = ToolRuntime(catalog)
    auth = runtime.authorize(source=source, node=node, values=values)
    assert auth.decision == "allowed"
    result = runtime.execute(
        project_root=tmp_path,
        source=source,
        node=node,
        values=values,
        authorization=auth,
        approved=False,
    )
    assert "outside marker" not in str(result.output)
    assert "private marker" not in str(result.output)
    outside = {
        **values,
        "path": "assets/secret.txt" if resource_id.endswith("read") else ".",
    }
    assert (
        runtime.authorize(source=source, node=node, values=outside).decision == "denied"
    )


def test_scoped_access_never_follows_a_symlink(tmp_path: Path) -> None:
    (tmp_path / "reports").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "reports/link").symlink_to(outside, target_is_directory=True)
    catalog, _, source, node = _case(
        "veyra.tool.filesystem.write", write=("project/reports",)
    )
    runtime = ToolRuntime(catalog)
    values = {"path": "reports/link/new/report.md", "content": "no"}
    auth = runtime.authorize(source=source, node=node, values=values)
    with pytest.raises(ToolRuntimeError, match="symlinks"):
        runtime.execute(
            project_root=tmp_path,
            source=source,
            node=node,
            values=values,
            authorization=auth,
            approved=True,
        )
    assert not (outside / "new").exists()


def test_tabular_compare_requires_both_inputs_inside_the_read_scope(
    tmp_path: Path,
) -> None:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports/left.csv").write_text("code,amount\na,1.20\n")
    (tmp_path / "reports/right.csv").write_text("code,amount\na,1.20\n")
    catalog, _, source, node = _case(
        "veyra.tool.tabular.compare", read=("project/reports",)
    )
    runtime = ToolRuntime(catalog)
    values = {
        "left_path": "reports/left.csv",
        "right_path": "reports/right.csv",
        "left_key": "code",
        "right_key": "code",
        "left_amount": "amount",
        "right_amount": "amount",
    }
    auth = runtime.authorize(source=source, node=node, values=values)
    assert auth.decision == "allowed"
    result = runtime.execute(
        project_root=tmp_path,
        source=source,
        node=node,
        values=values,
        authorization=auth,
        approved=False,
    )
    assert result.output["counts"]["equal_groups"] == 1
    assert result.output["left"]["path"] == "reports/left.csv"
    outside = {**values, "right_path": "assets/right.csv"}
    denied = runtime.authorize(source=source, node=node, values=outside)
    assert denied.decision == "denied"
    with pytest.raises(ToolRuntimeError) as caught:
        runtime.execute(
            project_root=tmp_path,
            source=source,
            node=node,
            values=outside,
            authorization=denied,
            approved=False,
        )
    assert caught.value.code == "tool_path_denied"
