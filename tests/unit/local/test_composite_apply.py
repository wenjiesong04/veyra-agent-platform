from __future__ import annotations

from pathlib import Path

import pytest

from veyra_agent_platform.local.builder.composite_apply import (
    CompositeApplyError,
    apply_composite,
)
from veyra_agent_platform.local.builder.generate_product import generate_builder_product
from veyra_agent_platform.local.library.service import LibraryService
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.storage import LocalRepository, migrate_local_database

SECONDHAND = (
    "帮我做一个二手商品整理和上架助手。"
    "我会一次上传很多照片。"
    "它要识别商品、查价格、写介绍。"
    "型号看不出来就问我。"
    "价格要让我确认。"
    "每件商品状态和价格历史都要保存。"
)
GIFT = (
    "帮我做一个礼品包装设计助手。"
    "用户上传商品图片。"
    "分析商品以后生成 3 个设计方向。"
    "用户选定方案以后再生成最终设计。"
    "最后还要生成效果图。"
)


def test_composite_apply_rolls_back_companions_when_workflow_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    product = generate_builder_product(SECONDHAND, ResourceCatalog())
    assert product.orchestration is not None
    assert product.orchestration.companions
    database = tmp_path / "app.sqlite3"
    migrate_local_database(database)
    projects = ProjectService(LocalRepository(database), tmp_path / "objects")
    library = LibraryService(projects.repository, projects)
    created = projects.create_managed(name="Composite Rollback")
    project_id = created["project_id"]

    def boom(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise ProjectError("forced workflow failure", "workflow_invalid")

    monkeypatch.setattr(projects, "create_workflow_from_source", boom)
    with pytest.raises(CompositeApplyError):
        apply_composite(
            projects=projects,
            library=library,
            project_id=project_id,
            companions=product.orchestration.companions,
            workflow=product.orchestration.workflow,
            flow=product.orchestration.flow,
        )
    assert list(projects.repository.agents(project_id)) == []
    summary = projects.project_summary(project_id)
    assert not summary.get("workflows")
    assert not summary.get("agents")


def test_missing_image_model_keeps_packaging_composite_applyable(
    tmp_path: Path,
) -> None:
    product = generate_builder_product(GIFT, ResourceCatalog())
    assert product.status == "review"
    assert product.orchestration is not None
    assert product.resolved is not None
    assert "image_generation" not in {
        item.capability for item in product.resolved.missing_required
    }

    database = tmp_path / "app.sqlite3"
    migrate_local_database(database)
    projects = ProjectService(LocalRepository(database), tmp_path / "objects")
    library = LibraryService(projects.repository, projects)
    created = projects.create_managed(name="Packaging Needs Image Setup")
    project_id = created["project_id"]

    applied = apply_composite(
        projects=projects,
        library=library,
        project_id=project_id,
        companions=product.orchestration.companions,
        workflow=product.orchestration.workflow,
        flow=product.orchestration.flow,
    )

    assert applied["workflow_id"]
    assert len(applied["companion_agents"]) == len(product.orchestration.companions)
    summary = projects.project_summary(project_id)
    assert len(summary["agents"]) == len(product.orchestration.companions)
    assert len(summary["workflows"]) == 1
