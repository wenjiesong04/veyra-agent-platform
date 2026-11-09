"""Deterministic capability matching for configured Runtime model profiles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .contracts import (
    CapabilityEvidenceSource,
    CapabilityStatus,
    ModelCapabilityRequirement,
    ModelProfile,
    ModelResolution,
    ModelResolutionIssue,
    ModelResolutionStatus,
    ModelRoleDefault,
)

_VERIFIED_EVIDENCE = frozenset(
    {
        CapabilityEvidenceSource.ACTIVE_PROBE,
        CapabilityEvidenceSource.PROVIDER_METADATA,
        CapabilityEvidenceSource.PROVIDER_ADAPTER,
    }
)
_RUNTIME_SLOT_ALIASES = {"primary": "primary_model", "image": "image_model"}
_DEFAULT_ROLE_ALIASES = {"primary_model": "primary", "image_model": "image"}


class ModelResolver:
    """Resolve model roles using explicit bindings, defaults, then eligible profiles."""

    @staticmethod
    def resolve(
        requirements: Sequence[ModelCapabilityRequirement],
        profiles: Sequence[ModelProfile],
        bindings: Mapping[str, Mapping[str, str]],
        defaults: Sequence[ModelRoleDefault],
        *,
        agent_id: str | None = None,
    ) -> tuple[ModelResolution, ...]:
        stable_profiles = tuple(
            sorted(
                profiles,
                key=lambda item: (
                    item.model_profile_id,
                    item.provider_connection_id,
                    item.provider_model_id,
                ),
            )
        )
        by_id: dict[str, ModelProfile] = {}
        for profile in stable_profiles:
            by_id.setdefault(profile.model_profile_id, profile)
        return tuple(
            _resolve_requirement(
                requirement,
                stable_profiles,
                by_id,
                bindings,
                defaults,
                agent_id=agent_id,
            )
            for requirement in requirements
        )


def _resolve_requirement(
    requirement: ModelCapabilityRequirement,
    profiles: Sequence[ModelProfile],
    by_id: Mapping[str, ModelProfile],
    bindings: Mapping[str, Mapping[str, str]],
    defaults: Sequence[ModelRoleDefault],
    *,
    agent_id: str | None,
) -> ModelResolution:
    bound_id, bound_scope = _explicit_binding(
        requirement.slot, bindings, agent_id=agent_id
    )
    if bound_id is not None:
        profile = by_id.get(bound_id)
        if profile is None:
            return _resolution(
                requirement,
                ModelResolutionStatus.NEEDS_SETUP,
                issue=ModelResolutionIssue(
                    code="model_profile_unavailable",
                    message=(
                        "The explicitly bound model is not available in the registry."
                    ),
                    missing=requirement.required,
                ),
            )
        missing, unknown, unsupported = _capability_gaps(profile, requirement.required)
        if not _profile_eligible(profile):
            return _resolution(
                requirement,
                ModelResolutionStatus.NEEDS_SETUP,
                profile=profile,
                issue=ModelResolutionIssue(
                    code="model_profile_not_ready",
                    message="The explicitly bound model is not ready for Runtime use.",
                    missing=missing,
                    unknown=unknown,
                    unsupported=unsupported,
                ),
            )
        if unsupported:
            return _resolution(
                requirement,
                ModelResolutionStatus.UNSUPPORTED,
                profile=profile,
                issue=ModelResolutionIssue(
                    code="model_binding_unsupported",
                    message=(
                        f"The {bound_scope or 'explicit'} model binding does not "
                        "support every required capability."
                    ),
                    missing=missing,
                    unknown=unknown,
                    unsupported=unsupported,
                ),
            )
        if unknown:
            return _resolution(
                requirement,
                ModelResolutionStatus.NEEDS_SETUP,
                profile=profile,
                issue=ModelResolutionIssue(
                    code="model_capability_unverified",
                    message=(
                        "A required capability on the bound model needs verification."
                    ),
                    missing=missing,
                    unknown=unknown,
                ),
            )
        optional_gaps = _capability_gaps(profile, requirement.optional)
        return _resolution(
            requirement,
            ModelResolutionStatus.ALREADY_BOUND,
            profile=profile,
            issue=_optional_issue(optional_gaps),
        )

    default_profiles = _default_profiles(requirement, by_id, defaults)
    for profile in default_profiles:
        if not _profile_eligible(profile):
            continue
        missing, unknown, unsupported = _capability_gaps(profile, requirement.required)
        if not missing and not unknown and not unsupported:
            optional_gaps = _capability_gaps(profile, requirement.optional)
            return _resolution(
                requirement,
                ModelResolutionStatus.WILL_BIND,
                profile=profile,
                issue=_optional_issue(optional_gaps),
            )

    eligible_profiles = [profile for profile in profiles if _profile_eligible(profile)]
    matching: list[tuple[int, ModelProfile]] = []
    for profile in eligible_profiles:
        missing, unknown, unsupported = _capability_gaps(profile, requirement.required)
        if not missing and not unknown and not unsupported:
            optional_missing = _capability_gaps(profile, requirement.optional)[0]
            matching.append(
                (len(requirement.optional) - len(optional_missing), profile)
            )

    if matching:
        matching.sort(key=lambda item: (-item[0], item[1].model_profile_id))
        profile = matching[0][1]
        optional_gaps = _capability_gaps(profile, requirement.optional)
        return _resolution(
            requirement,
            ModelResolutionStatus.WILL_BIND,
            profile=profile,
            issue=_optional_issue(optional_gaps),
        )

    missing, unknown, unsupported = _aggregate_gaps(
        requirement.required, eligible_profiles
    )
    if not requirement.required:
        optional_gaps = _aggregate_gaps(requirement.optional, eligible_profiles)
        return _resolution(
            requirement,
            ModelResolutionStatus.NEEDS_SETUP,
            issue=_optional_issue(optional_gaps),
        )
    if unknown:
        return _resolution(
            requirement,
            ModelResolutionStatus.NEEDS_SETUP,
            issue=ModelResolutionIssue(
                code="model_capability_unverified",
                message=(
                    "No eligible model has verified evidence for every required "
                    "capability."
                ),
                missing=missing,
                unknown=unknown,
                unsupported=unsupported,
            ),
        )
    if unsupported and eligible_profiles:
        return _resolution(
            requirement,
            ModelResolutionStatus.MISSING_CAPABILITY,
            issue=ModelResolutionIssue(
                code="model_capability_missing",
                message=(
                    "No eligible model supports every required capability."
                    if unsupported
                    else "No single eligible model profile meets all requirements."
                ),
                missing=missing,
                unsupported=unsupported,
            ),
        )
    return _resolution(
        requirement,
        ModelResolutionStatus.NEEDS_SETUP,
        issue=ModelResolutionIssue(
            code="model_setup_required",
            message="No configured, eligible model satisfies this requirement.",
            missing=requirement.required,
        ),
    )


def _explicit_binding(
    slot: str,
    bindings: Mapping[str, Mapping[str, str]],
    *,
    agent_id: str | None,
) -> tuple[str | None, str | None]:
    scopes = [f"agent:{agent_id}", "agent"] if agent_id else ["agent"]
    scopes.append("project")
    for scope in scopes:
        scope_bindings = bindings.get(scope, {})
        canonical_slot = _DEFAULT_ROLE_ALIASES.get(slot, slot)
        binding_slots = tuple(
            dict.fromkeys(
                (
                    slot,
                    canonical_slot,
                    _RUNTIME_SLOT_ALIASES.get(canonical_slot, ""),
                )
            )
        )
        for binding_slot in binding_slots:
            profile_id = scope_bindings.get(binding_slot) if binding_slot else None
            if profile_id:
                return profile_id, scope
    return None, None


def _default_profiles(
    requirement: ModelCapabilityRequirement,
    by_id: Mapping[str, ModelProfile],
    defaults: Sequence[ModelRoleDefault],
) -> tuple[ModelProfile, ...]:
    canonical_slot = _DEFAULT_ROLE_ALIASES.get(requirement.slot, requirement.slot)
    role_rank = {
        canonical_slot: 0,
        requirement.slot: 0,
    }
    for role in (*requirement.required, *requirement.optional):
        role_rank.setdefault(role, len(role_rank))
    for role, alias in _RUNTIME_SLOT_ALIASES.items():
        if role in role_rank:
            role_rank[alias] = role_rank[role]
    for runtime_role, canonical_role in _DEFAULT_ROLE_ALIASES.items():
        if canonical_role in role_rank:
            role_rank[runtime_role] = role_rank[canonical_role]
    selected: dict[str, ModelProfile] = {}
    for item in sorted(
        defaults, key=lambda value: (value.role, value.model_profile_id)
    ):
        normalized_role = _DEFAULT_ROLE_ALIASES.get(item.role, item.role)
        if normalized_role not in role_rank:
            continue
        profile = by_id.get(item.model_profile_id)
        if profile is None:
            continue
        selected[item.model_profile_id] = profile
    return tuple(
        sorted(
            selected.values(),
            key=lambda item: (
                min(
                    role_rank[default.role]
                    for default in defaults
                    if default.model_profile_id == item.model_profile_id
                    and _DEFAULT_ROLE_ALIASES.get(default.role, default.role)
                    in role_rank
                ),
                item.model_profile_id,
            ),
        )
    )


def _profile_eligible(profile: ModelProfile) -> bool:
    return profile.enabled and profile.registry_ready


def _capability_gaps(
    profile: ModelProfile, capabilities: Sequence[str]
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    missing: list[str] = []
    unknown: list[str] = []
    unsupported: list[str] = []
    for name in capabilities:
        capability = profile.capabilities.get(name)
        if capability is None:
            missing.append(name)
            continue
        if capability.status == CapabilityStatus.UNSUPPORTED:
            unsupported.append(name)
            continue
        evidence = capability.evidence
        if (
            capability.status != CapabilityStatus.SUPPORTED
            or evidence is None
            or evidence.source not in _VERIFIED_EVIDENCE
        ):
            unknown.append(name)
    return tuple(missing), tuple(unknown), tuple(unsupported)


def _aggregate_gaps(
    required: Sequence[str], profiles: Sequence[ModelProfile]
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    missing: list[str] = []
    unknown: list[str] = []
    unsupported: list[str] = []
    for name in required:
        states = [_capability_gaps(profile, (name,)) for profile in profiles]
        if any(not state[0] and not state[1] and not state[2] for state in states):
            continue
        if any(name in state[1] for state in states):
            unknown.append(name)
        elif any(name in state[2] for state in states):
            unsupported.append(name)
        else:
            missing.append(name)
    return tuple(missing), tuple(unknown), tuple(unsupported)


def _optional_issue(
    gaps: tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]],
) -> ModelResolutionIssue | None:
    missing, unknown, unsupported = gaps
    if not missing and not unknown and not unsupported:
        return None
    return ModelResolutionIssue(
        code="optional_model_capability_unavailable",
        message=(
            "Optional model capabilities are unavailable; review a supported "
            "fallback before running."
        ),
        missing=missing,
        unknown=unknown,
        unsupported=unsupported,
    )


def _resolution(
    requirement: ModelCapabilityRequirement,
    status: ModelResolutionStatus,
    *,
    profile: ModelProfile | None = None,
    issue: ModelResolutionIssue | None = None,
) -> ModelResolution:
    return ModelResolution(
        slot=requirement.slot,
        required=requirement.required,
        optional=requirement.optional,
        reason=requirement.reason,
        source=requirement.source,
        required_for_run=requirement.required_for_run,
        actor_id=requirement.actor_id,
        status=status,
        selected_model_profile_id=(profile.model_profile_id if profile else None),
        selected_model_display_name=(profile.display_name if profile else None),
        selected_provider_label=(profile.provider_label if profile else None),
        issue=issue,
    )
