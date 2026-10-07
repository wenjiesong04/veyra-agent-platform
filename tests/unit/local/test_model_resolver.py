from __future__ import annotations

from veyra_agent_platform.local.builder.generate_product import (
    generate_builder_product,
    proposal_preview,
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
