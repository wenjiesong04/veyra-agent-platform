from __future__ import annotations

import pytest

from veyra_agent_platform.contracts.agent import ComponentType
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.builder.workflow_orchestration import (
    compile_workflow_orchestration,
    materialize_workflow_source,
)
from veyra_agent_platform.local.resources import ResourceCatalog

PACKAGING = (
    "创建一个商品包装设计流程。"
    "先让商品分析 Agent 分析上传的商品图片，"
    "再让市场研究 Agent 调研竞品，"
    "然后让包装设计 Agent 提出设计，"
    "我确认后再生成最终包装效果图。"
)


def test_packaging_process_compiles_typed_workflow() -> None:
    orchestration = compile_workflow_orchestration(PACKAGING, ResourceCatalog())
    types = [node["component_type"] for node in orchestration.workflow["nodes"]]
    assert types[0] == "Start"
    assert types.count("AgentCall") >= 3
    assert "HumanApproval" in types
    assert types[-1] == "Output"
    names = [item.name for item in orchestration.companions]
    assert len(names) >= 3
    for companion in orchestration.companions:
        assert companion.is_loop


def test_daily_sales_compiles_condition_and_approval() -> None:
    requirement = (
        "每天先抓取销售数据，低于目标就通知负责人，"
        "高于目标就生成日报，日报必须由经理确认后再发送。"
    )
    orchestration = compile_workflow_orchestration(requirement, ResourceCatalog())
    types = [node["component_type"] for node in orchestration.workflow["nodes"]]
    assert types[0] == "Start"
    assert "Condition" in types
    assert "HumanApproval" in types
    assert types[-1] == "Output"


def test_materialize_requires_committed_versions() -> None:
    orchestration = compile_workflow_orchestration(PACKAGING, ResourceCatalog())
    with pytest.raises(ValueError, match="committed Agent version"):
        materialize_workflow_source(orchestration, {}, source_hashes={})


def test_materialize_pins_immutable_agent_versions() -> None:
    orchestration = compile_workflow_orchestration(PACKAGING, ResourceCatalog())
    version_ids = {item.agent_id: new_uuid7() for item in orchestration.companions}
    hashes = {item.agent_id: item.source_hash for item in orchestration.companions}
    source = materialize_workflow_source(
        orchestration, version_ids, source_hashes=hashes
    )
    calls = [
        node for node in source.nodes if node.component_type is ComponentType.AGENT_CALL
    ]
    assert calls
    for node in calls:
        agent_id, version_id = str(node.agent_ref).split("@", 1)
        assert version_id == version_ids[agent_id]
        assert node.agent_ref in source.lock
        assert version_id != "draft"
