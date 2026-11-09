"""Exact methods survive generation without replacing executable tools."""

from copy import deepcopy
from dataclasses import replace
from typing import Any

import pytest

from veyra_agent_platform.contracts.common import SCHEMA_VERSION
from veyra_agent_platform.contracts.task_structure import (
    ExecutionBoundary,
    SkillChoice,
    TaskActor,
    TaskIOField,
    TaskLifecycle,
    TaskStage,
    TaskStructure,
)
from veyra_agent_platform.local.builder.capability_requirements import requirement_for
from veyra_agent_platform.local.builder.composite_composer import (
    compose_execution_product,
)
from veyra_agent_platform.local.builder.execution_planner import compile_execution_plan
from veyra_agent_platform.local.builder.generate_product import generate_builder_product
from veyra_agent_platform.local.builder.plan_resources import resolve_plan_resources
from veyra_agent_platform.local.builder.task_planner import (
    normalize_task_structure,
    required_task_duties,
    validate_task_structure,
)
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.resources.resolver import ResourceResolver


class MethodCatalog(ResourceCatalog):
    """Use real immutable descriptor construction for synthetic registered methods."""

    def __init__(self, *, capability: str = "document_analysis") -> None:
        super().__init__()
        sample = self.by_reference("veyra.skill.document-analyzer@1.0.0")
        additions = []
        for name in ("chosen", "other"):
            method = deepcopy(sample)
            for key in ("reference", "content_hash", "origin"):
                method.pop(key)
            method.update(
                resource_id=f"test.skill.{name}", name=name, capabilities=[capability]
            )
            method["spec"]["instruction"] = (
                f"Use the {name} method; record source rows."
            )
            additions.append(self._descriptor(method, origin="workshop"))
        self._resources = (*self._resources, *additions)
        self._by_reference.update(
            {(row["resource_id"], row["version"]): row for row in additions}
        )


def task(*, capability: str = "document_analysis") -> TaskStructure:
    return TaskStructure(
        schema_version=SCHEMA_VERSION,
        goal="Review supplied evidence",
        summary="Use the chosen method and retain evidence",
        entities=(),
        actors=(
            TaskActor(
                id="reviewer",
                role="reviewer",
                capabilities=("text_generation", capability),
            ),
        ),
        stages=(
            TaskStage(id="review", summary="Apply the chosen method", actor="reviewer"),
        ),
        inputs=(TaskIOField(name="request", type="string"),),
        outputs=(TaskIOField(name="result", type="string"),),
        execution_boundaries=(),
        lifecycle=TaskLifecycle(persistent=False, interaction="single_run"),
        orchestration_complexity="single",
        uncertainty=(),
        skill_choices=(
            SkillChoice(
                "reviewer",
                capability,
                "test.skill.chosen@1.0.0",
                "The user needs this method",
            ),
        ),
    )


class Planner:
    def __init__(self, structure: TaskStructure) -> None:
        self.structure = structure

    def complete_json(self, prompt: str, schema: Any) -> dict[str, Any]:
        return self.structure.to_dict()


def test_generation_preserves_exact_method_instead_of_same_capability_builtin() -> None:
    catalog = MethodCatalog()
    product = generate_builder_product(
        task().goal, catalog, planner_provider=Planner(task())
    )
    assert product.status == "review" and product.source is not None
    assert product.source.skill_refs == ("test.skill.chosen@1.0.0",)
    assert (
        product.source.lock["test.skill.chosen@1.0.0"]
        == catalog.by_reference("test.skill.chosen@1.0.0")["content_hash"]
    )
    assert "veyra.skill.document-analyzer@1.0.0" not in product.source.lock
    restored = TaskStructure.from_dict(product.structure.to_dict())
    assert normalize_task_structure(restored).skill_choices == task().skill_choices


def test_method_with_tool_capability_keeps_real_executor_separately() -> None:
    catalog = MethodCatalog(capability="workspace_read")
    product = generate_builder_product(
        "Read files with this method",
        catalog,
        planner_provider=Planner(task(capability="workspace_read")),
    )
    assert product.source is not None, product.diagnostics
    assert "test.skill.chosen@1.0.0" in product.source.skill_refs
    assert "veyra.tool.filesystem.read@1.0.0" in product.source.lock
    assert product.source.permissions.tools == ("veyra.tool.filesystem.read",)
    assert product.source.permissions.filesystem_write_roots == ()


@pytest.mark.parametrize(
    "reference",
    [
        "test.skill.absent@1.0.0",
        "veyra.tool.filesystem.read@1.0.0",
        "test.skill.chosen@2.0.0",
    ],
)
def test_invalid_selected_method_is_a_gap_without_same_capability_substitute(
    reference: str,
) -> None:
    structure = replace(
        task(), skill_choices=(replace(task().skill_choices[0], reference=reference),)
    )
    product = generate_builder_product(
        structure.goal, MethodCatalog(), planner_provider=Planner(structure)
    )
    assert product.resolved is not None and product.resolved.missing_required
    assert not any(row.kind == "skill" for row in product.resolved.selected)


def test_changed_hash_and_conflicting_project_pin_fail_closed() -> None:
    catalog = MethodCatalog()
    structure = task()
    plan = compile_execution_plan(structure)
    snapshot = catalog.resources()["resources"]
    next(row for row in snapshot if row["reference"] == "test.skill.chosen@1.0.0")[
        "content_hash"
    ] = "0" * 64
    resolved, _ = resolve_plan_resources(
        plan,
        structure,
        ResourceResolver(catalog),
        requirement=structure.goal,
        catalog_snapshot=snapshot,
    )
    assert resolved.missing_required and not resolved.selected
    actual = catalog.by_reference("test.skill.chosen@1.0.0")
    pin = {**actual, "scope": "project", "bound_content_hash": "0" * 64}
    resolved, _ = resolve_plan_resources(
        plan,
        structure,
        ResourceResolver(catalog),
        requirement=structure.goal,
        project_resources=[pin],
    )
    assert resolved.missing_required and not resolved.selected


def test_companion_actors_receive_only_their_own_same_capability_method() -> None:
    structure = task()
    structure = replace(
        structure,
        actors=(
            *structure.actors,
            TaskActor(
                id="checker",
                role="checker",
                capabilities=("text_generation", "document_analysis"),
            ),
        ),
        stages=(
            *structure.stages,
            TaskStage(
                id="check",
                summary="Check the result independently",
                actor="checker",
                input_sources={"request": "review.result"},
            ),
        ),
        skill_choices=(
            *structure.skill_choices,
            SkillChoice(
                "checker",
                "document_analysis",
                "test.skill.other@1.0.0",
                "Independent checking method",
            ),
        ),
    )
    plan = compile_execution_plan(structure)
    plan = replace(plan, shape=replace(plan.shape, shape="AGENT_WORKFLOW"))
    # Recompile actor IDs and typed handoffs using the actual composite decision.
    plan = compile_execution_plan(structure, decision=plan.shape)
    resolved, scoped = resolve_plan_resources(
        plan, structure, ResourceResolver(MethodCatalog()), requirement=structure.goal
    )
    assert scoped is not None
    assert {row.reference for row in resolved.selected} == {
        "test.skill.chosen@1.0.0",
        "test.skill.other@1.0.0",
    }
    _, orchestration = compose_execution_product(plan, resolved, actor_resources=scoped)
    assert orchestration is not None
    assert [source.skill_refs for source in orchestration.companions] == [
        ("test.skill.chosen@1.0.0",),
        ("test.skill.other@1.0.0",),
    ]


def test_choice_cannot_attach_to_an_unknown_or_incompatible_actor() -> None:
    for choice in (
        replace(task().skill_choices[0], actor="absent"),
        replace(task().skill_choices[0], capability="workspace_write"),
    ):
        with pytest.raises(ValueError, match="declared actor"):
            validate_task_structure(replace(task(), skill_choices=(choice,)))


def test_method_channel_does_not_weaken_explicit_executor_selection() -> None:
    from veyra_agent_platform.local.builder.composite_composer import (
        specification_from_plan,
    )

    catalog = MethodCatalog(capability="workspace_read")
    structure = task(capability="workspace_read")
    plan = compile_execution_plan(structure)
    resolved = ResourceResolver(catalog).resolve(
        specification_from_plan(plan),
        (requirement_for("workspace_read"),),
        requested_references={"workspace_read": ["test.skill.chosen@1.0.0"]},
    )
    assert resolved.missing_required and not resolved.selected


def test_method_cannot_hide_executor_missing_from_selectable_snapshot() -> None:
    catalog = MethodCatalog(capability="workspace_read")
    structure = task(capability="workspace_read")
    snapshot = [
        row for row in catalog.resources()["resources"] if row["kind"] == "skill"
    ]
    resolved, _ = resolve_plan_resources(
        compile_execution_plan(structure),
        structure,
        ResourceResolver(catalog),
        requirement=structure.goal,
        catalog_snapshot=snapshot,
    )
    assert any(row.capability == "workspace_read" for row in resolved.missing_required)
    assert {row.reference for row in resolved.selected} == {"test.skill.chosen@1.0.0"}


def test_factory_mode_cannot_compose_an_unread_default_method() -> None:
    planner = Planner(replace(task(), skill_choices=()))
    planner.requires_skill_grounding = True
    product = generate_builder_product(
        task().goal, MethodCatalog(), planner_provider=planner
    )
    assert product.status == "blocked" and product.source is None
    assert product.blocked_reason == "execution_plan_invalid"
    assert "methods can be read" in product.diagnostics[0]


def test_normalization_preserves_distinct_questions_and_obligation_contracts() -> None:
    choice = ExecutionBoundary(
        kind="human_input",
        stage="choose",
        reason="Wait for user",
        question="Choose?",
        source="user requested confirmation",
        required=True,
        expected_schema={"answer": "string"},
    )
    confirm = replace(choice, stage="final_confirm", question="Confirm final result?")
    structure = replace(task(), execution_boundaries=(choice, confirm))
    normalized = normalize_task_structure(structure)
    assert len(normalized.execution_boundaries) == 2
    assert len(required_task_duties(normalized)) == 2
    same_stage = replace(
        structure, execution_boundaries=(choice, replace(confirm, stage="choose"))
    )
    assert len(normalize_task_structure(same_stage).execution_boundaries) == 2
    tampered = replace(
        normalized,
        execution_boundaries=(
            choice,
            replace(confirm, expected_schema={"approved": "boolean"}),
        ),
    )
    assert required_task_duties(normalized) - required_task_duties(tampered)


def test_generator_compiles_report_directory_limit_into_actual_permissions() -> None:
    structure = replace(
        task(capability="workspace_write"),
        skill_choices=(),
        filesystem_write_roots=("project/reports",),
    )
    product = generate_builder_product(
        "Write reports only in reports",
        ResourceCatalog(),
        planner_provider=Planner(structure),
    )
    assert product.source is not None, product.diagnostics
    assert product.source.permissions.filesystem_write_roots == ("project/reports",)
    restored = TaskStructure.from_dict(product.structure.to_dict())
    assert normalize_task_structure(restored).filesystem_write_roots == (
        "project/reports",
    )
    assert product.resolved.selected[0].adapter == "veyra.runtime.filesystem.write"


def test_generator_cannot_claim_shell_enforces_a_native_directory_limit() -> None:
    structure = replace(
        task(capability="shell_exec"),
        skill_choices=(),
        filesystem_write_roots=("project/reports",),
    )
    product = generate_builder_product(
        "Run a command but only write reports",
        ResourceCatalog(),
        planner_provider=Planner(structure),
    )
    assert product.source is None and product.status == "blocked"
    assert "directory write limit" in product.diagnostics[0]
    broad = generate_builder_product(
        "Run a Project command",
        ResourceCatalog(),
        planner_provider=Planner(
            replace(structure, filesystem_write_roots=("project",))
        ),
    )
    assert broad.source is not None, broad.diagnostics


@pytest.mark.parametrize(
    "root",
    [
        "reports",
        "project/../reports",
        "project/.env",
        "project//reports",
        "project/C:other",
    ],
)
def test_write_scope_contract_rejects_nonportable_or_escaping_limits(root: str) -> None:
    value = task().to_dict()
    value["filesystem_write_roots"] = [root]
    with pytest.raises(ValueError):
        TaskStructure.from_dict(value)
