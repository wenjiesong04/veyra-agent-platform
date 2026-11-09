"""Bounded, metadata-only Project context shared by Builder adapters."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, NamedTuple

from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.condition import CONDITION_PLANNING_GUIDANCE
from veyra_agent_platform.local.projects.service import ProjectService
from veyra_agent_platform.local.resources import ResourceCatalog

from .prompt import BUILDER_SYSTEM_PROMPT, RUNNABLE_AGENT_PRIMITIVES

MAX_CONTEXT_BYTES = 400_000
BuilderMode = Literal[
    "interview", "create_agent", "edit_source", "resolve_intent", "plan_task"
]
ContextCategory = Literal[
    "conversation_recent_messages",
    "project_agents_metadata",
    "workflows_metadata",
    "knowledge_metadata",
    "project_resource_bindings",
    "catalog_capabilities",
    "project_files_metadata",
    "project_config",
]
ExcludedCategory = Literal[
    "knowledge_contents",
    "project_file_contents",
    "credentials",
    "secrets",
    "raw_runtime_events",
    "hidden_reasoning",
    "raw_prompts",
    "provider_response_bodies",
]

INCLUDED_CONTEXT_CATEGORIES: tuple[ContextCategory, ...] = (
    "conversation_recent_messages",
    "project_agents_metadata",
    "workflows_metadata",
    "knowledge_metadata",
    "project_resource_bindings",
    "catalog_capabilities",
    "project_files_metadata",
    "project_config",
)
EXCLUDED_CONTEXT_CATEGORIES: tuple[ExcludedCategory, ...] = (
    "knowledge_contents",
    "project_file_contents",
    "credentials",
    "secrets",
    "raw_runtime_events",
    "hidden_reasoning",
    "raw_prompts",
    "provider_response_bodies",
)


class SnapshotFacts(NamedTuple):
    project_hash: str
    catalog_hash: str
    context_size_bytes: int


class BuilderHarness:
    def __init__(self, projects: ProjectService, catalog: ResourceCatalog) -> None:
        self.projects = projects
        self.catalog = catalog

    def context_document(
        self,
        project_id: str,
        mode: BuilderMode,
        *,
        target: dict[str, Any] | None = None,
        conversation: dict[str, Any] | None = None,
        include_tool_output_schemas: bool = True,
    ) -> dict[str, Any]:
        project = self.projects.project_summary(project_id)
        inventory = {
            kind: [
                {key: value for key, value in item.items() if key != "source_path"}
                for item in project.get(kind, [])
            ]
            for kind in ("agents", "workflows", "knowledge")
        }
        for kind in ("agent", "workflow"):
            reader = getattr(
                self.projects.repository,
                "draft" if kind == "agent" else "workflow_draft",
            )
            versions = getattr(self.projects.repository, f"{kind}_versions")
            for item in inventory[f"{kind}s"]:
                identity = item[f"{kind}_id"]
                draft = reader(identity)
                if draft is not None:
                    item["draft"] = {
                        key: draft[key]
                        for key in ("revision", "etag", "source_file_hash")
                    }
                    source = json.loads(draft["source_json"])
                    item["nodes"] = [
                        {
                            key: node[key]
                            for key in (
                                "id",
                                "component_type",
                                "agent_id",
                                "version_id",
                            )
                            if key in node
                        }
                        for node in source["nodes"]
                    ]
                    item["transitions"] = source["transitions"]
                    item["lock"] = source["lock"]
                item["versions"] = [
                    {
                        key: row[key]
                        for key in ("version_id", "source_hash", "behavior_hash")
                    }
                    for row in versions(identity)
                ]
        resources = self.catalog.factory_snapshot()
        if mode == "plan_task":
            # Task planning needs capability truth, not legacy graph node specs.
            resources = [
                item
                for item in resources
                if item["kind"] in {"tool", "mcp_tool", "skill", "policy"}
            ]
        for resource in resources:
            descriptor = self.catalog.by_reference(resource["reference"])
            resource.update(
                content_hash=descriptor["content_hash"],
                origin=descriptor["origin"],
                factory_selectable=descriptor["factory_selectable"],
                capabilities=list(descriptor.get("capabilities") or ()),
            )
            if mode == "plan_task":
                spec = resource.get("spec") or {}
                resource["spec"] = {
                    key: spec[key]
                    for key in (
                        "adapter",
                        "input_schema",
                        "input_constraints",
                        "output_schema",
                        "approval_required",
                        "input_json_schema",
                        "output_json_schema",
                        "output_validation",
                        "schema_status",
                    )
                    if key in spec
                    and (include_tool_output_schemas or key != "output_json_schema")
                }
            elif mode in {"resolve_intent", "interview"}:
                # Intent/goal understanding needs capability metadata, not every
                # Tool schema, legacy graph template or unselected Skill body.
                compact = {
                    key: resource[key]
                    for key in (
                        "reference",
                        "kind",
                        "name",
                        "description",
                        "availability",
                        "runtime_status",
                        "factory_selectable",
                        "capabilities",
                    )
                    if key in resource
                }
                resource.clear()
                resource.update(compact)
        context = {
            "scope": "project" if target is None else target["kind"],
            "operation": mode,
            "project": {
                key: project[key]
                for key in ("project_id", "name", "description", "manifest_hash")
            },
            "inventory": inventory,
            "project_bindings": [
                binding.to_dict()
                for binding in self.projects.project_resource_bindings(project_id)
            ],
            "files": self.projects.list_files(project_id)["files"],
            "resources": resources,
            "unselectable_resources": [
                {
                    key: item[key]
                    for key in ("reference", "kind", "availability", "runtime_status")
                }
                for item in self.catalog.resources()["resources"]
                if not item["factory_selectable"]
            ],
            "target": target,
            "conversation": conversation,
            "runtime_contract": {
                "file_inputs": {
                    "representation": "typed_ArtifactRef",
                    "metadata_fields": [
                        "kind",
                        "artifact_id",
                        "media_type",
                        "filename",
                    ],
                    "filename": "server_canonical_sanitized_uploaded_basename",
                    "model_visibility": "selected_input_name_and_stored_filename",
                    "native_tool_source_label": (
                        "input:<declared input> (<stored filename>)"
                    ),
                    "content_access": "metadata_does_not_prove_contents_were_read",
                    "future_uploads": (
                        "actual_filenames_are_runtime_data_not_build_prerequisites"
                    ),
                },
                "agent": {
                    "execution": "bounded_model_tool_loop",
                    "actions": ["tool", "ask_user", "render_images", "final"],
                    "images": "render_after_final",
                    "image_inputs": "typed_image_ArtifactRefs_to_vision_model",
                    "image_outputs": "one_real_render_per_named_image_output",
                    "image_capability": "native_model.image_not_Tool_dependency",
                    "image_artifact_feedback": "real_refs_before_state_writes",
                    "model_setup": "requires_configuration_not_unsupported_task",
                    "context": "durable_messages_and_replies_within_one_run",
                    "finalization": {
                        "version": "1",
                        "actor_owned_verification": "same_run_candidate_feedback",
                        "required_criteria": "withhold_delivery_until_supported",
                        "advisory_criteria": "report_without_blocking_delivery",
                        "image_review": "inspect_actual_artifacts_once_by_default",
                        "pre_render_review": "explicit_opt_in_only",
                        "evidence": "model_assessment_not_independent_verification",
                    },
                    "cross_run_entities": "require_explicit_state_tools_and_identity",
                },
                "workflow": {
                    "execution": "DAG",
                    "cycles": "unsupported",
                    "human_input": "typed_reply",
                    "approval_outcomes": "approved_rejected_control_ports_not_data",
                    "stop": "cancel_without_business_outputs",
                },
                "skills": "pinned_instructions_do_not_grant_permissions",
                "policies": "partial_enforcement_only",
            },
            "authority": {
                "writes": "explicit_confirmation_only",
                "file_contents": "not_loaded",
                "resource_creation": "not_supported_by_this_adapter",
                "multi_object_mutation": False,
                "composite_product_creation": "one_workflow_with_new_companion_agents",
                "runtime_host_configuration": "not_checked",
                "runtime_execution": "not_performed",
            },
        }
        encoded = json.dumps(context, ensure_ascii=False)
        if len(encoded.encode()) > MAX_CONTEXT_BYTES:
            raise ContractValidationError("Builder context exceeds the size limit")
        return context

    def messages(
        self,
        project_id: str,
        mode: BuilderMode,
        *,
        target: dict[str, Any] | None = None,
        schema: dict[str, Any] | None = None,
        conversation: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        context = self.context_document(
            project_id,
            mode,
            target=target,
            conversation=conversation,
            include_tool_output_schemas=mode != "plan_task",
        )
        encoded = json.dumps(context, ensure_ascii=False)
        contract = {
            "plan_task": (
                "Return only TaskStructureV1 JSON matching the supplied schema: "
                + json.dumps(schema, ensure_ascii=False)
                + ". Preserve every user requirement, constraints and success "
                "criteria. Understand semantic duties instead of matching "
                "occupations or keywords. actors contains autonomous AI roles "
                "only, never the user, approver or a Tool. "
                "Use concise user-facing role labels in the user's language. "
                "Declare actual user inputs and final outputs; "
                "every task/actor input and output declares name and type. "
                "Use the canonical defaults for omitted metadata; include multiple, "
                "required, cardinality, description and source only when meaningful "
                "or non-default. Actual data bindings must remain explicit. "
                "Do not use empty placeholders, names alone or $ref aliases. "
                "files use typed document/file/image "
                "fields, not an empty array or a generic request/result substitute. "
                "Capability names come from each resource's capabilities array, "
                "not its reference/name. "
                "Propose skill_choices only for methods needed by this task, using "
                "an exact supplied skill reference, its declared capability, the "
                "actor that will use it, and a task-specific reason. Do not treat "
                "a negated, historical or background mention as a selection. "
                "Select the user's requested method when it exists in this catalog; "
                "do not replace it with a same-capability generic method. An empty "
                "skill_choices array is valid when no method fits. Selected methods "
                "will be read before composition. Skills do not replace Tools: "
                "declare their real executable dependencies separately. "
                "When the user limits file writes to a directory, declare "
                "filesystem_write_roots as project/<relative directory>, e.g. "
                "project/reports. Otherwise use an empty array to inherit Tool "
                "requirements. These limits only narrow native filesystem Tools; "
                "they cannot authorize Shell, MCP or any new capability. "
                "When the task requires arithmetic, totals, amounts or numeric "
                "comparisons, select the supplied arithmetic Tool capability "
                "and require computed evidence instead of model mental math. "
                "Describe explicit ordered stages and actor input/output contracts. "
                "File/image/document I/O types are real ArtifactRefs, never paths "
                "or invented IDs. Match output types to the supplied Tool results: "
                "Vision is a native model capability for image inputs. Actual "
                "generated images use image_generation and named image outputs; "
                "they do not require an image Tool in the catalog. Use separate "
                "named image outputs for separately requested views. Lack of a "
                "configured image model is a setup need, not permission to replace "
                "requested images with Prompt text. "
                "a Project file write can deliver its relative path and receipt "
                "without declaring an ArtifactRef output. Declare an artifact "
                "output only when an actual selected Tool returns that reference "
                "or a selected input artifact is being passed through, or the "
                "native image model renders a declared image output. Outputs "
                "produced only on an approved branch are optional at Workflow "
                "level on rejection; their producer's outputs remain required "
                "when that producer executes. "
                "Verification checks are executable, not prose. Supported checks "
                "are output.not_empty, schema_valid (a mapped result object), "
                "required_fields:<bound field>, artifact_exists:<bound field>, "
                "and constraint_match:<field or nested path> <comparison> <literal>. "
                "Declare verifier stage input_sources for its actual subjects; "
                "keep business explanations in reason and success_criteria. Do not "
                "replace business validation with a generic non-empty check. "
                "Separate required output fields from minimum item counts. "
                "Reviews, searches and comparisons may legitimately return zero "
                "findings; do not require an error, match or difference to exist "
                "unless the user actually requires a minimum count. Preserve an "
                "explicit user minimum, but never invent findings to fill it. "
                "Typed required outputs already enforce field presence. The "
                "required_fields check also rejects empty collections; do not "
                "apply it to a list that may validly have zero findings. "
                + CONDITION_PLANNING_GUIDANCE
                + " "
                "In a Workflow, a stage with an actor runs that actor's complete "
                "instructions and declared input/output contract. Do not split "
                "one actor's internal inspection, calculation and drafting into "
                "separate calls with invented intermediate ports. Group those "
                "methods into one actor stage, returning its actual declared "
                "outputs. Reuse an actor across stages only to repeat its full "
                "role with the same declared contract. If an independent business "
                "gate or verifier separates review from a later write, use a "
                "read-only producer and a separate restricted effect role after "
                "that gate; the producer must not own the write Tool. "
                "Bind inputs using input.name or "
                "stage_id.output_port; ordering alone never transfers data. Each "
                "execution boundary must refer to its actual stage. Human decisions "
                "use human_input with typed expected_schema or human_approval; "
                "skills are procedures, tools are permitted capabilities. Use only "
                "supplied available capabilities, report missing capabilities and "
                "uncertainty. Never invent refs, permissions, credentials or "
                "immutable versions. The server decides Agent versus Workflow. A "
                "single autonomous role may use multiple tools; do not split Agents "
                "only for different prompt sections. Workflow is a DAG and cannot "
                "repeat a stage indefinitely. The current Agent loop supports "
                "tool/final/ask_user actions with durable replies. A single "
                "interactive role can ask questions inside its loop; represent "
                "these requested questions/choices with human_input boundaries. "
                "Attach native questions to their actor stage; they run when that "
                "actor needs the answer, not unconditionally after its completion. "
                "Distinguish optional conversation from a delivery prerequisite. "
                "Supporting later additions or corrections does not require a "
                "human_input gate: the Agent already has conversation context. "
                "A human_input boundary must explicitly set required=false for "
                "optional follow-up; required=true means the task actually needs "
                "that answer or user decision before delivery. If the user asks "
                "to report missing or conflicting facts, preserve them as reported "
                "gaps instead of requiring every gap to be resolved. Do not invent "
                "a clarification prerequisite or an approval the user did not ask "
                "for. Retain actual required choices and before-effect approvals. "
                "Attach a role's own final delivery verification to that actor "
                "stage: the compiler creates its Runtime finalization policy. "
                "Failed checks or missing evidence return to the same loop for "
                "revision, tools or questions; no Workflow backedge is required. "
                "When a persistent role must remember generated images, it uses "
                "render_images before final, receives real ArtifactRefs, then "
                "records those through its declared state Tools. Artifact references "
                "cannot be written before they exist. Intermediate business state "
                "is retained; only Runtime delivery evidence establishes acceptance. "
                "An independent checker remains an actor-less verification stage. "
                "A verification boundary's reason states the actual business "
                "review criteria; its checks remain executable rules. Required "
                "criteria withhold delivery. Mark advisory boundaries required=false "
                "only when they are genuinely optional; never weaken a user must. "
                "A completed review with no defects is a valid outcome: its "
                "finding list may be empty with an explicit no-findings summary, "
                "not fabricated defects or padded no-error checklist rows. "
                "Do not upgrade a design plausibility check into a physical "
                "certification requirement the user did not request. "
                "An independent business approval uses its own actor-less stage. "
                "When it governs an effect, name that capability on the gate and "
                "grant it only to the post-gate effect role, never the producer. "
                "A single role may also manage its declared state through the "
                "supplied entity Tools; attach that state boundary to its actor "
                "stage. A separate state stage remains a deterministic Workflow "
                "step. Independent roles need real declared handoffs even when "
                "both use only text_generation; role names do not supply Tools. "
                "ask_user and conversation context are native runtime actions, "
                "not Tool capability names. Use text_generation for a reasoning "
                "role, plus actual supplied Tool capabilities if needed. "
                "Repeated choice, modification and confirmation within one task "
                "use that role's loop, not a cyclic Workflow. Conversation context "
                "does not need entity tools: lifecycle.persistent=false and "
                "state=null unless the user needs separately stored records. "
                "Reusable definitions and Runtime execution receipts do not by "
                "themselves require a business Entity or an extra persistence step. "
                "Do not invent cross-session persistence when the user only asks "
                "to continue the current task. Model binding/configuration is "
                "resolved by the server after planning; it is not uncertainty. "
                "Cost estimates can be labeled estimates in constraints, without "
                "inventing a live quotation dependency. uncertainty contains only "
                "unresolved user requirements that block faithful execution, not "
                "optional features, caveats or unsupported extras. Deterministic "
                "Facts that users provide per task (file selection, column names, "
                "budget, confirmation) belong in inputs or runtime questions, "
                "not blocking uncertainty. A planning example: a role produces "
                "draft.options (object), a human_input boundary at choose declares "
                "expected_schema=[{name:selection,type:string}], and a later "
                "role receives input_sources=[{input:options,source:draft.options}, "
                "{input:selection,source:choose.selection}]. Human stages leave "
                "actor empty. Pure Agent stages inside one loop need no dataflow "
                "bindings; their questions and decisions remain instructions. "
                "Deterministic human gates "
                "belong in explicit Workflow boundaries. Cross-run edits require "
                "explicit supported state and identity. If a request needs "
                "record persistence, state.identity must be a declared data field "
                "and state must describe the entity fields to save; a persistent "
                "lifecycle with state=null is incomplete. "
                "or entity_id, the platform's stable record ID. Never invent "
                "undeclared task_key/record_key fields. Query by declared fields "
                "to locate records, and ask_user on ambiguous matches. Users need "
                "not design an ID scheme in advance; task-instance matching facts "
                "are runtime questions, not blocking uncertainty. If a request needs "
                "unsupported repeat interaction, report that limitation in "
                "uncertainty, never silently return a simpler task. Arrays of named "
                "types/bindings are the provider projection."
            ),
            "interview": (
                "Ask one concise follow-up about goal, inputs, outputs, risks or "
                "success criteria. Do not ask users to learn internal node types."
            ),
            "create_agent": (
                "Return only an AgentSemanticPlanV1 JSON matching the supplied "
                "response schema. Describe the Agent's goal, inputs, outputs, "
                "summary steps, and step_intents. Give every input and output a "
                "description of what a good value contains. step_intents fields "
                "are only semantic_key, name, purpose, operation_kind, depends_on, "
                "capability_requirement, dependency_requirement, "
                "reusable_capability, inputs, outputs, branches, "
                "condition_expression, branch_condition, branch_key, and "
                "output_mapping. Mark a step reusable only when the requirement "
                "needs a Project-reusable capability; model, transform, or "
                "capability steps with reusable_capability=true may declare typed "
                "step inputs/outputs, which define the reusable component "
                "contract, not general inter-step dataflow. "
                "depends_on expresses ordering/control only. Only the last Model "
                "on each path to Output emits the declared Agent outputs. Earlier "
                "Models write a working note named by semantic_key. Transforms may "
                "read only top-level Agent inputs or literals, never prior Model "
                "or step outputs. Preserve declared Agent output names exactly. "
                "Keep a Transform when it performs a real user-requested mapping "
                "from Agent inputs/literals; do not invent a mapping-only Transform "
                "to rename Model outputs. If such an invalid mapping-only step is "
                "present, remove only that step and preserve the producing Model's "
                "duty using the declared output fields. "
                "operation_kind enum is closed: model, capability, transform, "
                "condition, approval, verification. Human confirmation is always "
                "approval, never model, confirm, review, or human_review. Later "
                "duties after approval set branch_condition to that approval and "
                "branch_key to approved or rejected. A check of a prior result is "
                "verification; describe what to check, do not invent a verifier "
                "implementation. A branch over a user-supplied Run input is "
                "condition; for every condition emit exactly two semantic branches "
                "with key and label. Put the executable predicate in "
                "condition_expression using a supported comparison over a declared "
                "Agent input; keep human intent in purpose. Do not use a "
                "non-empty fallback for natural-language classification. Mark every "
                "branch-local step with branch_condition and branch_key; "
                "the server chooses runtime ports. "
                "capability_intents names a Project-bound tool from "
                "project_bindings or stays empty. capability_requirement names "
                "a Project-bound capability for operation_kind=capability, or "
                "the semantic capability to reuse. dependency_requirement may "
                "name an existing Project-bound Tool for a safe wrapper. The "
                "server chooses implementation and derives IDs, pins, hashes, "
                "and permissions. "
                "Reuse a bound ready Project capability; never invent a second "
                "copy. Never put constraints or prohibitions in capability_intents; "
                "those belong in user_constraints. "
                "A simple translation, summary, or one-duty text Agent needs one "
                "model step. Split model steps when duties are distinct. Do not "
                "omit step_intents after approval, condition, verification, a "
                "genuine transform, capability, or a second model duty is required. Do "
                "not emit resource hashes, Knowledge UUIDs, node IDs, canvas "
                "positions, source.lock, permission sets, or filesystem roots. "
                + RUNNABLE_AGENT_PRIMITIVES
                + " The server compiles a canonical AgentBlueprint and reviews it "
                "before creation."
            ),
            "edit_source": (
                "Return only the complete candidate Source JSON. Change only the "
                "selected target to satisfy the request. The server derives the "
                "Proposal, Diff and Impact. Source schema: " + json.dumps(schema)
            ),
            "resolve_intent": (
                "Resolve the latest natural-language request using this Project and "
                "conversation. Return only JSON matching this schema: "
                + json.dumps(schema)
                + ". Distinguish create, edit, discuss and clarify. "
                "conversation.requirement_context contains the original user "
                "statements frozen for this request. Use it to retain the goal "
                "and explicit corrections even when recent history is bounded. "
                "The current request selects the task; unrelated completed tasks "
                "are context only. Assistant messages are explanations, not user "
                "requirements or permission grants. "
                "Questions and discussion are not edit commands. Do not invent a "
                "target or infer "
                "creation because a named target is absent. targets lists existing "
                "objects to be modified, not new roles or read-only dependencies. "
                "For Agent/Workflow creation set creation_scope=single_product "
                "when the user wants one work product, including a Workflow and "
                "its new companion Agents. The number of roles does not make "
                "that a multi-object edit. Set creation_scope=independent_products "
                "only for multiple separately usable top-level products. If that "
                "distinction is unclear, ask one short clarification. multi_object "
                "still describes edits spanning existing objects; it must not "
                "block new companion creation. Cross-Agent handoffs may belong "
                "to one Workflow, never a silent edit of one existing Agent. "
                "Read-only reuse does not authorize modifying a dependency. "
                "A target mention must quote "
                "its name, slug or ID from user messages. Use basis=context only "
                "for an unambiguous reference to the current conversational/page "
                "target. If multiple objects could match, return clarify with a "
                "short question in the user's language; never choose the first or "
                "default Agent. A clarified reply must retain the original change "
                "in instruction. For Agent create, set create_kind=agent. For a "
                "direct reusable-component request, use intent=create_component, "
                "create_kind=custom_component, and component_plan with only the "
                "semantic capability, purpose, typed inputs/outputs, operation "
                "kind, and optional name of an already-bound Tool dependency. "
                "Never output component IDs, versions, hashes, implementation "
                "code, permissions, or Project paths. Recognize Workflow and "
                "Resource creation even when the adapter cannot apply it. "
                "message explains your interpretation, not completed work. "
                "plan describes the candidate change, not authorization to write."
            ),
        }[mode]
        return [
            {"role": "system", "content": BUILDER_SYSTEM_PROMPT + "\n" + contract},
            {"role": "user", "content": encoded},
        ]

    def snapshot_facts(self, project_id: str, mode: BuilderMode) -> SnapshotFacts:
        context = self.context_document(project_id, mode)
        encoded = json.dumps(context, ensure_ascii=False)
        catalog_rows = [
            {**item, **self.catalog.by_reference(item["reference"])}
            for item in context["resources"]
        ]
        return SnapshotFacts(
            project_hash=canonical_json_hash(project_snapshot_projection(context)),
            catalog_hash=canonical_json_hash(catalog_snapshot_projection(catalog_rows)),
            context_size_bytes=len(encoded.encode("utf-8")),
        )


def canonical_json_hash(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def project_snapshot_projection(context: dict[str, Any]) -> dict[str, Any]:
    inventory = context.get("inventory") or {}
    return {
        "project": _pick(
            context.get("project") or {},
            ("project_id", "name", "description", "manifest_hash"),
        ),
        "agents": [_agent_projection(item) for item in inventory.get("agents") or []],
        "workflows": [
            _pick(
                item,
                (
                    "workflow_id",
                    "slug",
                    "name",
                    "description",
                    "version",
                    "source_file_hash",
                ),
            )
            | _graph_projection(item)
            for item in inventory.get("workflows") or []
        ],
        "knowledge": [
            _knowledge_projection(item) for item in inventory.get("knowledge") or []
        ],
        "project_bindings": list(context.get("project_bindings") or []),
        "files": [
            _pick(item, ("path", "kind", "byte_length", "agent_id"))
            for item in context.get("files") or []
        ],
    }


def catalog_snapshot_projection(
    resources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        _pick(
            item,
            (
                "reference",
                "kind",
                "name",
                "description",
                "availability",
                "runtime_status",
                "required_permissions",
                "factory_selectable",
                "content_hash",
                "origin",
                "component_class",
            ),
        )
        for item in resources
    ]


def _agent_projection(item: dict[str, Any]) -> dict[str, Any]:
    payload = _pick(
        item,
        ("agent_id", "slug", "name", "description", "version", "source_file_hash"),
    )
    origin = item.get("community_origin")
    if isinstance(origin, dict):
        payload["community_origin"] = _pick(
            origin, ("owner_handle", "slug", "version", "source_hash")
        )
    payload.update(_graph_projection(item))
    return payload


def _graph_projection(item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    draft = item.get("draft")
    if isinstance(draft, dict):
        payload["draft"] = _pick(draft, ("revision", "etag", "source_file_hash"))
    if "nodes" in item:
        payload["nodes"] = item["nodes"]
    if "transitions" in item:
        payload["transitions"] = item["transitions"]
    if "lock" in item:
        payload["lock"] = item["lock"]
    if "versions" in item:
        payload["versions"] = item["versions"]
    return payload


def _knowledge_projection(item: dict[str, Any]) -> dict[str, Any]:
    payload = _pick(
        item,
        (
            "knowledge_id",
            "slug",
            "name",
            "description",
            "version",
            "source_file_hash",
        ),
    )
    processing = item.get("processing")
    if isinstance(processing, dict):
        payload["index_status"] = processing.get("index_status")
        payload["chunk_count"] = processing.get("chunk_count")
    return payload


def _pick(item: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: item[key] for key in keys if key in item and item[key] is not None}
