from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from veyra_agent_platform.contracts.task_structure import TaskIOField
from veyra_agent_platform.local.builder.generate_product import (
    GenerationProduct,
    generate_builder_product,
    proposal_preview,
)
from veyra_agent_platform.local.builder.task_planner import plan_task_structure
from veyra_agent_platform.local.factory.service import (
    _project_generation_model_readiness,
)
from veyra_agent_platform.local.models.contracts import (
    CAPABILITY_NAMES,
    CapabilityEvidence,
    CapabilityEvidenceSource,
    CapabilityStatus,
    ModelCapability,
    ModelCapabilityRequirement,
    ModelMetadata,
    ModelProfile,
    ModelResolutionIssue,
    ModelResolutionStatus,
    ModelRoleDefault,
    ModelVerification,
    ModelVerificationState,
)
from veyra_agent_platform.local.models.resolver import ModelResolver
from veyra_agent_platform.local.resources import ResourceCatalog


def _profile(
    profile_id: str,
    capabilities: dict[str, CapabilityStatus],
    *,
    evidence_source: CapabilityEvidenceSource = (
        CapabilityEvidenceSource.PROVIDER_METADATA
    ),
) -> ModelProfile:
    evidence = CapabilityEvidence(
        source=evidence_source, observed_at="2026-10-03T00:00:00Z"
    )
    capability_map = {name: ModelCapability() for name in CAPABILITY_NAMES}
    capability_map.update(
        {
            name: ModelCapability(
                status=status,
                evidence=evidence if status == CapabilityStatus.SUPPORTED else None,
            )
            for name, status in capabilities.items()
        }
    )
    return ModelProfile(
        model_profile_id=profile_id,
        provider_connection_id=f"connection-{profile_id}",
        provider_type="openai_compatible",
        provider_label=f"Provider {profile_id}",
        provider_model_id=f"model-{profile_id}",
        display_name=f"Model {profile_id}",
        enabled=True,
        listed=True,
        metadata=ModelMetadata(),
        capabilities=capability_map,
        verification=ModelVerification(
            state=ModelVerificationState.VERIFIED,
            source=evidence_source,
            verified_at="2026-10-03T00:00:00Z",
        ),
        capability_revision=1,
        capability_digest=f"digest-{profile_id}",
        discovered_at=None,
        created_at="2026-10-03T00:00:00Z",
        updated_at="2026-10-03T00:00:00Z",
        connection_readiness="ready",
        registry_ready=True,
    )


def _default(profile: ModelProfile, role: str) -> ModelRoleDefault:
    return ModelRoleDefault(
        role=role,
        model_profile_id=profile.model_profile_id,
        provider_connection_id=profile.provider_connection_id,
        provider_model_id=profile.provider_model_id,
        capability_digest=profile.capability_digest,
        capability_revision=profile.capability_revision,
        updated_at=profile.updated_at,
    )


def test_image_input_does_not_satisfy_image_generation() -> None:
    vision = _profile(
        "vision",
        {
            "text_generation": CapabilityStatus.SUPPORTED,
            "image_input": CapabilityStatus.SUPPORTED,
            "image_generation": CapabilityStatus.UNSUPPORTED,
        },
    )
    requirement = ModelCapabilityRequirement(
        slot="image",
        required=("image_generation",),
        reason="The plan produces an image.",
        source="execution_plan.steps.render",
    )

    result = ModelResolver.resolve((requirement,), (vision,), {}, ())[0]

    assert result.status == ModelResolutionStatus.MISSING_CAPABILITY
    assert result.selected_model_profile_id is None
    assert result.issue is not None
    assert result.issue.unsupported == ("image_generation",)


def test_unknown_or_unverified_evidence_never_satisfies_required() -> None:
    unknown = _profile(
        "unknown",
        {"image_generation": CapabilityStatus.UNKNOWN},
    )
    user_declared = _profile(
        "declared",
        {"image_generation": CapabilityStatus.SUPPORTED},
        evidence_source=CapabilityEvidenceSource.USER_DECLARED,
    )
    requirement = ModelCapabilityRequirement(
        slot="image",
        required=("image_generation",),
        reason="Generate a final design image.",
        source="task_structure.outputs.image",
    )

    for profile in (unknown, user_declared):
        result = ModelResolver.resolve((requirement,), (profile,), {}, ())[0]
        assert result.status == ModelResolutionStatus.NEEDS_SETUP
        assert result.selected_model_profile_id is None
        assert result.issue is not None
        assert result.issue.unknown == ("image_generation",)


def test_binding_precedence_and_defaults_are_deterministic() -> None:
    agent = _profile("agent", {"text_generation": CapabilityStatus.SUPPORTED})
    project = _profile("project", {"text_generation": CapabilityStatus.SUPPORTED})
    default = _profile("default", {"text_generation": CapabilityStatus.SUPPORTED})
    other = _profile("other", {"text_generation": CapabilityStatus.SUPPORTED})
    requirement = ModelCapabilityRequirement(
        slot="primary",
        required=("text_generation",),
        reason="The Agent needs a text model.",
        source="execution_plan.actors.main",
    )
    profiles = (other, default, project, agent)
    defaults = (_default(default, "primary"),)

    bound = ModelResolver.resolve(
        (requirement,),
        profiles,
        {"agent": {"primary": "agent"}, "project": {"primary": "project"}},
        defaults,
    )[0]
    named_agent_bound = ModelResolver.resolve(
        (requirement,),
        profiles,
        {
            "agent:existing-agent": {"primary": "agent"},
            "project": {"primary": "project"},
        },
        defaults,
        agent_id="existing-agent",
    )[0]
    project_bound = ModelResolver.resolve(
        (requirement,),
        profiles,
        {"project": {"primary": "project"}},
        defaults,
    )[0]
    runtime_slot_bound = ModelResolver.resolve(
        (requirement,),
        profiles,
        {"project": {"primary_model": "project"}},
        defaults,
    )[0]
    defaulted = ModelResolver.resolve((requirement,), profiles, {}, defaults)[0]
    deterministic = ModelResolver.resolve((requirement,), (other, default), {}, ())[0]

    assert bound.status == ModelResolutionStatus.ALREADY_BOUND
    assert bound.selected_model_profile_id == "agent"
    assert named_agent_bound.selected_model_profile_id == "agent"
    assert project_bound.selected_model_profile_id == "project"
    assert runtime_slot_bound.selected_model_profile_id == "project"
    assert defaulted.selected_model_profile_id == "default"
    assert deterministic.selected_model_profile_id == "default"


def test_incompatible_explicit_binding_does_not_fall_back() -> None:
    bound = _profile(
        "bound",
        {
            "text_generation": CapabilityStatus.SUPPORTED,
            "image_generation": CapabilityStatus.UNSUPPORTED,
        },
    )
    compatible = _profile(
        "compatible",
        {
            "text_generation": CapabilityStatus.SUPPORTED,
            "image_generation": CapabilityStatus.SUPPORTED,
        },
    )
    requirement = ModelCapabilityRequirement(
        slot="image",
        required=("image_generation",),
        reason="The explicit image model is pinned.",
        source="project binding",
    )

    result = ModelResolver.resolve(
        (requirement,),
        (compatible, bound),
        {"project": {"image_model": "bound"}},
        (_default(compatible, "image"),),
    )[0]

    assert result.status == ModelResolutionStatus.UNSUPPORTED
    assert result.selected_model_profile_id == "bound"
    assert result.issue is not None
    assert result.issue.unsupported == ("image_generation",)

    unresolved = ModelResolver.resolve(
        (requirement,),
        (compatible,),
        {"project": {"image_model": "__unresolved_binding__"}},
        (_default(compatible, "image"),),
    )[0]
    assert unresolved.status == ModelResolutionStatus.NEEDS_SETUP
    assert unresolved.selected_model_profile_id is None
    assert unresolved.issue is not None
    assert unresolved.issue.code == "model_profile_unavailable"


def test_capability_default_is_used_before_generic_profiles() -> None:
    default = _profile(
        "image-default",
        {"image_generation": CapabilityStatus.SUPPORTED},
    )
    generic = _profile(
        "generic-image",
        {"image_generation": CapabilityStatus.SUPPORTED},
    )
    requirement = ModelCapabilityRequirement(
        slot="image",
        required=("image_generation",),
        reason="Generate the final image.",
        source="execution_plan.steps.render",
    )

    result = ModelResolver.resolve(
        (requirement,),
        (generic, default),
        {},
        (_default(default, "image_generation"),),
    )[0]

    assert result.status == ModelResolutionStatus.WILL_BIND
    assert result.selected_model_profile_id == "image-default"

    runtime_slot_requirement = ModelCapabilityRequirement(
        slot="image_model",
        required=("image_generation",),
        reason="Runtime image output requires an image model.",
        source="runtime_preflight",
    )
    runtime_slot_result = ModelResolver.resolve(
        (runtime_slot_requirement,),
        (generic, default),
        {},
        (_default(default, "image"),),
    )[0]
    assert runtime_slot_result.selected_model_profile_id == "image-default"


def test_optional_missing_capability_is_reported_without_becoming_required() -> None:
    requirement = ModelCapabilityRequirement(
        slot="image",
        optional=("image_generation",),
        reason="Image generation is preferred.",
        source="task_structure.outputs.image",
        required_for_run=False,
    )

    result = ModelResolver.resolve((requirement,), (), {}, ())[0]

    assert result.status == ModelResolutionStatus.NEEDS_SETUP
    assert result.required == ()
    assert result.optional == ("image_generation",)
    assert result.required_for_run is False
    assert result.issue is not None
    assert result.issue.code == "optional_model_capability_unavailable"
    assert result.issue.missing == ("image_generation",)
    assert "review a supported fallback before running" in result.issue.message


def test_proposal_candidate_is_stable_when_profile_rows_reorder() -> None:
    alpha = _profile("alpha", {"text_generation": CapabilityStatus.SUPPORTED})
    beta = _profile("beta", {"text_generation": CapabilityStatus.SUPPORTED})
    goal = "帮我做一个中英翻译 Agent"
    first = generate_builder_product(
        goal,
        ResourceCatalog(),
        model_profiles=(beta, alpha),
    )
    reordered = generate_builder_product(
        goal,
        ResourceCatalog(),
        model_profiles=(alpha, beta),
    )

    first_model = proposal_preview(first)["models"][0]
    reordered_model = proposal_preview(reordered)["models"][0]
    assert first_model["status"] == "will_bind"
    assert first_model["selected_model_profile_id"] == "alpha"
    assert reordered_model["selected_model_profile_id"] == "alpha"


def _image_product(
    profiles: tuple[ModelProfile, ...],
    bindings: dict[str, dict[str, str]] | None = None,
) -> GenerationProduct:
    structure = plan_task_structure("Translate supplied text into English").structure
    assert structure is not None
    outputs = (*structure.outputs, TaskIOField(name="view", type="image"))
    actor = replace(
        structure.actors[0],
        capabilities=("text_generation", "image_generation"),
        outputs=outputs,
    )
    structure = replace(structure, actors=(actor,), outputs=outputs)
    product = generate_builder_product(
        structure.goal,
        ResourceCatalog(),
        model_profiles=profiles,
        model_bindings=bindings,
        planner_provider=SimpleNamespace(
            complete_json=lambda prompt, schema: structure.to_dict()
        ),
    )
    assert product.status == "review", product.diagnostics
    assert product.plan is not None and product.plan.product_shape == "PURE_AGENT"
    assert {item.slot for item in product.model_requirements} == {"primary", "image"}
    return product


def _model_plan() -> list[dict[str, str]]:
    return [
        {
            "kind": "component",
            "reference": "veyra.component.model@1.0.0",
            "availability": "requires_configuration",
            "runtime_status": "runtime_not_configured",
        },
        {
            "kind": "tool",
            "reference": "external.tool@1.0.0",
            "availability": "requires_configuration",
            "runtime_status": "runtime_not_configured",
        },
    ]


@pytest.mark.parametrize("already_bound", [False, True])
def test_verified_model_roles_project_static_model_setup_only(
    already_bound: bool,
) -> None:
    primary = _profile("primary", {"text_generation": CapabilityStatus.SUPPORTED})
    image = _profile("image", {"image_generation": CapabilityStatus.SUPPORTED})
    bindings = (
        {"project": {"primary_model": "primary", "image_model": "image"}}
        if already_bound
        else None
    )
    product = _image_product((primary, image), bindings)
    plan = _model_plan()
    projected = _project_generation_model_readiness(product, plan)
    assert projected[0]["availability"] == "ready"
    assert projected[0]["runtime_status"] == "supported"
    assert projected[1] == plan[1]
    assert plan[0]["availability"] == "requires_configuration"
    assert (
        ResourceCatalog().by_reference("veyra.component.model@1.0.0")["availability"]
        == "requires_configuration"
    )


@pytest.mark.parametrize(
    "failure",
    [
        "missing_primary_profile",
        "missing_image_profile",
        "unknown_image",
        "declared_image",
        "explicit_mismatch",
        "stale_binding",
        "missing_resolution",
        "missing_profile_id",
        "duplicate_resolution",
        "requirement_mismatch",
        "optional_issue",
        "workflow",
    ],
)
def test_incomplete_model_proof_never_projects_ready(failure: str) -> None:
    primary = _profile("primary", {"text_generation": CapabilityStatus.SUPPORTED})
    image = _profile(
        "image",
        {
            "image_generation": CapabilityStatus.UNKNOWN
            if failure == "unknown_image"
            else CapabilityStatus.SUPPORTED
        },
        evidence_source=CapabilityEvidenceSource.USER_DECLARED
        if failure == "declared_image"
        else CapabilityEvidenceSource.PROVIDER_METADATA,
    )
    profiles = (
        (primary,)
        if failure == "missing_image_profile"
        else (image,)
        if failure == "missing_primary_profile"
        else (primary, image)
    )
    binding_id = (
        "primary"
        if failure == "explicit_mismatch"
        else "missing-profile"
        if failure == "stale_binding"
        else None
    )
    product = _image_product(
        profiles, {"project": {"image_model": binding_id}} if binding_id else None
    )
    if failure == "missing_resolution":
        product = replace(
            product,
            model_resolutions=tuple(
                item for item in product.model_resolutions if item.slot != "image"
            ),
        )
    elif failure in {"missing_profile_id", "requirement_mismatch"}:
        product = replace(
            product,
            model_resolutions=(
                replace(
                    product.model_resolutions[0],
                    **(
                        {"selected_model_profile_id": None}
                        if failure == "missing_profile_id"
                        else {"required": ()}
                    ),
                ),
                *product.model_resolutions[1:],
            ),
        )
    elif failure == "duplicate_resolution":
        product = replace(
            product,
            model_resolutions=(
                *product.model_resolutions,
                product.model_resolutions[0],
            ),
        )
    elif failure == "optional_issue":
        product = replace(
            product,
            model_resolutions=(
                replace(
                    product.model_resolutions[0],
                    issue=ModelResolutionIssue(
                        code="optional_model_capability_unavailable",
                        message="A declared capability still needs a fallback.",
                        unknown=("structured_output",),
                    ),
                ),
                *product.model_resolutions[1:],
            ),
        )
    elif failure == "workflow":
        assert product.plan is not None
        product = replace(
            product,
            plan=replace(
                product.plan, shape=replace(product.plan.shape, shape="AGENT_WORKFLOW")
            ),
        )
    plan = _model_plan()
    assert _project_generation_model_readiness(product, plan) == plan


def test_model_projection_does_not_override_an_unavailable_component() -> None:
    primary = _profile("primary", {"text_generation": CapabilityStatus.SUPPORTED})
    image = _profile("image", {"image_generation": CapabilityStatus.SUPPORTED})
    product = _image_product((primary, image))
    plan = _model_plan()
    plan[0]["availability"] = "quarantined"
    assert _project_generation_model_readiness(product, plan) == plan
