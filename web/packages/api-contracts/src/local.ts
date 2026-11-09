/**
 * Wire contracts for the local desktop sidecar.
 *
 * The local API deliberately returns the resource object directly (rather
 * than wrapping it in a `data` envelope).  These types mirror the FastAPI
 * routes in `backend/src/veyra_agent_platform/local/api/projects/routes.py`.
 */

import type { ConversationAttachment, ProjectOrigin } from "./cloud";

export const LOCAL_API_SCHEMA_VERSION = "1.0" as const;

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export type JsonObject = { [key: string]: JsonValue };

export const COMPACT_FIELD_TYPES = [
  "string",
  "number",
  "integer",
  "boolean",
  "object",
  "array",
  "table",
  "image",
  "pdf",
  "document",
  "file",
  "audio",
  "video",
  "collection",
] as const;

export type CompactFieldType = (typeof COMPACT_FIELD_TYPES)[number];
export type ArtifactKind = "image" | "pdf" | "document" | "file" | "audio" | "video" | "collection";
export type FieldValueType =
  | "string"
  | "number"
  | "integer"
  | "boolean"
  | "object"
  | "array"
  | "table"
  | "artifact";

export type TypedFieldDescriptor = {
  type: FieldValueType | ArtifactKind;
  artifact_kind?: ArtifactKind;
  required?: boolean;
  multiple?: boolean;
  description?: string;
  accepted_media_types?: string[];
  json_schema?: JsonObject;
};

export type TypedFieldSpec = string | TypedFieldDescriptor;
export type TypedFields = Record<string, TypedFieldSpec>;

const compactFieldTypeSet = new Set<string>(COMPACT_FIELD_TYPES);

export function compactFieldType(spec: TypedFieldSpec): string {
  if (typeof spec === "string") return spec;
  if (spec.type === "artifact") return spec.artifact_kind ?? "file";
  return spec.type;
}

export const ARTIFACT_FIELD_TYPES: readonly ArtifactKind[] = [
  "image",
  "pdf",
  "document",
  "file",
  "audio",
  "video",
  "collection",
];

export function isArtifactCompactType(type: string): type is ArtifactKind {
  return (ARTIFACT_FIELD_TYPES as readonly string[]).includes(type);
}

export function fieldIsMultiple(spec: TypedFieldSpec): boolean {
  return typeof spec !== "string" && spec.multiple === true;
}

export function fieldIsRequired(spec: TypedFieldSpec): boolean {
  return typeof spec === "string" || spec.required !== false;
}

export function acceptedMediaTypes(spec: TypedFieldSpec): string[] {
  if (typeof spec !== "string" && spec.accepted_media_types?.length) {
    return spec.accepted_media_types;
  }
  const type = compactFieldType(spec);
  if (type === "image") return ["image/*"];
  if (type === "pdf") return ["application/pdf", ".pdf"];
  if (type === "audio") return ["audio/*"];
  if (type === "video") return ["video/*"];
  if (type === "document") {
    return [
      ".pdf",
      ".txt",
      ".md",
      ".csv",
      ".rtf",
      ".doc",
      ".docx",
      ".xlsx",
      "application/pdf",
      "text/plain",
      "text/csv",
      "application/rtf",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ];
  }
  if (type === "collection" || type === "file") return [];
  return [];
}

export type ArtifactRef = {
  kind: "artifact";
  artifact_id: string;
  media_type: string;
  filename: string;
  relative_path?: string;
};

export type ArtifactCollection = {
  kind: "collection";
  collection_id: string;
  items: ArtifactRef[];
};

export function isArtifactRef(value: unknown): value is ArtifactRef {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  if (record.kind !== "artifact") return false;
  return typeof record.artifact_id === "string" && record.artifact_id.length > 0
    && typeof record.media_type === "string" && record.media_type.length > 0
    && typeof record.filename === "string" && record.filename.length > 0;
}

export function isArtifactCollection(value: unknown): value is ArtifactCollection {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  if (record.kind !== "collection" || typeof record.collection_id !== "string") return false;
  return Array.isArray(record.items) && record.items.every(isArtifactRef);
}

export type ArtifactRecord = ArtifactRef & {
  project_id: string;
  sha256: string;
  size_bytes: number;
  storage_ref: string;
  source_kind: "upload" | "runtime_output" | "project_file_import";
  created_at: string;
  run_id?: string;
};

export type CapabilityState = "supported" | "unsupported" | "unknown";

export type RuntimeModelCapabilities = {
  provider: string;
  model_id: string;
  text_input: CapabilityState;
  image_input: CapabilityState;
  video_input: CapabilityState;
  audio_input: CapabilityState;
  structured_json_output: CapabilityState;
  source: "static_profile" | "registry" | "unknown";
};

export function isTypedFieldSpec(value: unknown): value is TypedFieldSpec {
  if (typeof value === "string") return compactFieldTypeSet.has(value);
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  if (typeof record.type !== "string") return false;
  if (record.type === "artifact") {
    return typeof record.artifact_kind === "string" && compactFieldTypeSet.has(record.artifact_kind);
  }
  return compactFieldTypeSet.has(record.type);
}

export type PermissionContract = {
  network_hosts: string[];
  tools: string[];
  filesystem_read_roots?: string[];
  filesystem_write_roots?: string[];
  shell_workspace_only?: boolean;
  protect_input_files?: boolean;
  protected_input_fields?: string[];
};

export type VerificationContract = {
  required: boolean;
  checks: string[];
};

export type FlowNode = {
  id: string;
  component_type:
    | "Start"
    | "Agent"
    | "Model"
    | "AgentCall"
    | "Tool"
    | "CustomComponent"
    | "Condition"
    | "Transform"
    | "HumanApproval"
    | "Verifier"
    | "Stop"
    | "Output";
  model_ref?: string;
  system_prompt?: string;
  agent_ref?: string;
  input_mapping?: Record<string, string>;
  output_mapping?: Record<string, string>;
  uses?: string;
  network_hosts?: string[];
  expression?: string;
  mapping?: Record<string, string>;
  prompt?: string;
  review?: string;
  checks?: string[];
  output_name?: string;
  inputs?: TypedFields;
  outputs?: TypedFields;
};

export type DataPortRef = {
  kind: "run_input" | "node" | "run_output";
  port: string;
  node_id?: string;
};

export type DataEdge = {
  source: DataPortRef;
  target: DataPortRef;
};

export type FlowTransition = {
  from: string;
  port: "next" | "true" | "false" | "approved" | "rejected" | "passed" | "failed";
  to: string;
};

export type StudioNoteColor = "teal" | "amber" | "violet" | "slate";

export type StudioNote = {
  x: number;
  y: number;
  text: string;
  color?: StudioNoteColor;
  width?: number;
  height?: number;
  manual_position?: boolean;
};

export type AgentSource = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  agentspec_version: "26.1";
  component_type: "Flow";
  agent_id: string;
  slug: string;
  name: string;
  description: string;
  inputs: TypedFields;
  outputs: TypedFields;
  nodes: FlowNode[];
  transitions: FlowTransition[];
  extensions: {
    veyra: {
      runtime_profile: string;
      secret_refs: string[];
      permissions: PermissionContract;
      verification: VerificationContract;
      skill_refs?: string[];
      policy_refs?: string[];
      knowledge_refs?: string[];
      execution_kind?: "loop" | "graph";
      instructions?: string;
      max_turns?: number;
      interaction_mode?: "auto" | "chat" | "form" | "hybrid";
      handoff_agent_refs?: string[];
      finalization?: {
        version: "1";
        checks: string[];
        criteria: string[];
        review_images: boolean;
        advisory_criteria?: string[];
        pre_render_review?: boolean;
        review_strategy?: "direct" | "evidence_first";
        evidence_inputs?: string[];
      };
      state_contract?: {
        entity: string;
        identity: string;
        scope: "run" | "conversation" | "project" | "entity";
        fields: Record<string, string>;
        statuses: string[];
        revision: boolean;
        source?: string;
      };
    };
  };
  ui: {
    positions: Record<string, { x: number; y: number }>;
    bindings?: Record<string, CatalogBinding>;
    notes?: Record<string, StudioNote>;
    labels?: Record<string, string>;
    branch_labels?: Record<string, { true: string; false: string }>;
  };
  lock: Record<string, string>;
  data_edges?: DataEdge[];
};

export type AgentImportCapability = {
  kind: string;
  original: string;
  status: "supported" | "partial" | "unsupported";
  reason: string;
  reference?: string;
  included?: boolean;
};

export type AgentImportWarning = {
  code: string;
  message: string;
  path?: string;
};

export type AgentImportPreview = {
  name: string;
  description: string;
  instructions: string;
  model: Record<string, string>;
  inputs: TypedFields;
  outputs: TypedFields;
  tools: string[];
  skills: string[];
  knowledge_files: string[];
  workflow_present: boolean;
  source_path?: string;
};

export type CommunityAgentImportOrigin = {
  owner_handle: string;
  slug: string;
  version: string;
  source_hash: string;
};

export type AgentImportProjectValidation = {
  project_id: string;
  source_hash: string;
  assessment_hash: string;
  dependencies: AgentDependencyCheck[];
  dependency_summary: AgentDependencySummary;
  runtime_ready: boolean;
  runtime_ready_scope: "agent_dependencies";
};

export type AgentImportRecord = {
  schema_version: "agent.import.v1";
  import_id: string;
  state: "analyzed" | "applied";
  source_kind: "yaml" | "zip" | "folder";
  source_name: string;
  source_path: string;
  detected_format: "generic_yaml" | "veyra_agent_yaml";
  compatibility: number;
  preview: AgentImportPreview;
  capabilities: AgentImportCapability[];
  warnings: AgentImportWarning[];
  generated_source: AgentSource;
  manifest: Record<string, JsonValue>;
  community_origin?: CommunityAgentImportOrigin;
  project_validation?: AgentImportProjectValidation;
  applied_agent?: CreatedAgentResponse;
};

export type AgentImportApplyRequest = {
  project_id: string;
  confirm: boolean;
  name?: string;
  description?: string;
  parent_agent_id?: string;
};

export type AgentImportApplyResponse = {
  schema_version: "agent.import.v1";
  import: AgentImportRecord;
  agent: CreatedAgentResponse;
};

export type WorkflowSource = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  component_type: "Workflow";
  workflow_id: string;
  slug: string;
  name: string;
  description: string;
  version?: string;
  inputs: TypedFields;
  outputs: TypedFields;
  nodes: FlowNode[];
  transitions: FlowTransition[];
  extensions: {
    veyra: {
      permissions: PermissionContract;
      verification: VerificationContract;
    };
  };
  ui: {
    positions: Record<string, { x: number; y: number }>;
    notes?: Record<string, StudioNote>;
    labels?: Record<string, string>;
    branch_labels?: Record<string, { true: string; false: string }>;
  };
  lock: Record<string, string>;
};

export type StudioSource = AgentSource | WorkflowSource;

export type EditTargetKind = "agent" | "workflow";
export type BuilderResolveRequest = {
  content: string;
  history: { role: "user" | "assistant"; content: string }[];
  focus: { kind: EditTargetKind; target_id: string } | null;
  locale: "zh" | "en";
};
export type BuilderResolution = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  intent: "create" | "edit" | "discuss" | "clarify";
  create_kind: "agent" | "workflow" | "resource" | null;
  status: "resolved" | "clarification" | "unsupported";
  message: string;
  instruction: string;
  plan: string[];
  targets: { kind: EditTargetKind; target_id: string; name: string; revision?: number; etag?: string }[];
};
export type BuilderMessageKind =
  | "user"
  | "assistant"
  | "plan"
  | "clarification"
  | "failure"
  | "proposal_reference"
  | "reject"
  | "confirm"
  | "apply_summary"
  | "validation_summary"
  | "result";
export type BuilderTargetKind = "agent" | "workflow";
export type BuilderOperationEventKind =
  | "builder.operation.started"
  | "builder.intent.started"
  | "builder.intent.resolved"
  | "builder.specification.started"
  | "builder.specification.completed"
  | "builder.semantic_plan.started"
  | "builder.semantic_plan.completed"
  | "builder.capabilities.started"
  | "builder.capabilities.resolved"
  | "builder.compile.started"
  | "builder.compile.completed"
  | "builder.validation.started"
  | "builder.validation.completed"
  | "builder.component_design.started"
  | "builder.component_design.completed"
  | "builder.component.created"
  | "builder.proposal.ready"
  | "builder.proposal.confirmed"
  | "builder.proposal.rejected"
  | "builder.apply.started"
  | "builder.apply.completed"
  | "builder.test_run.started"
  | "builder.test_run.waiting_approval"
  | "builder.test_run.completed"
  | "builder.test_run.failed"
  | "builder.test_run.stopped"
  | "builder.operation.completed"
  | "builder.operation.failed";
export type BuilderOperationEvent = {
  event_id: string;
  operation_id: string;
  sequence: number;
  kind: BuilderOperationEventKind;
  label: string;
  summary: string;
  facts: Record<string, string>;
  created_at: string;
};
export type BuilderHarnessInvocationKind =
  | "resolve_intent"
  | "interview"
  | "semantic_plan"
  | "semantic_plan_repair";
export type BuilderHarnessReceiptStatus = "prepared" | "success" | "failed";
export type BuilderHarnessStructuredMode = "strict_json_schema" | "json_object" | "none";
export type BuilderHarnessContextCategory =
  | "conversation_recent_messages"
  | "project_agents_metadata"
  | "workflows_metadata"
  | "knowledge_metadata"
  | "project_resource_bindings"
  | "catalog_capabilities"
  | "project_files_metadata"
  | "project_config";
export type BuilderHarnessExcludedCategory =
  | "knowledge_contents"
  | "project_file_contents"
  | "credentials"
  | "secrets"
  | "raw_runtime_events"
  | "hidden_reasoning"
  | "raw_prompts"
  | "provider_response_bodies";
export type BuilderHarnessReceipt = {
  receipt_id: string;
  operation_id: string;
  conversation_id: string;
  project_id: string;
  invocation_kind: BuilderHarnessInvocationKind;
  sequence: number;
  status: BuilderHarnessReceiptStatus;
  started_at: string;
  completed_at: string | null;
  harness_mode: string;
  policy_version: string;
  policy_hash: string;
  output_contract: string;
  schema_version: string;
  schema_hash: string;
  structured_mode: BuilderHarnessStructuredMode;
  project_snapshot_hash: string;
  catalog_snapshot_hash: string;
  included_categories: BuilderHarnessContextCategory[];
  excluded_categories: BuilderHarnessExcludedCategory[];
  history_message_count: number;
  context_size_bytes: number;
  request_size_bytes: number;
  provider_id: string;
  model: string;
  endpoint_kind: string;
  provider_profile_status: string;
  provider_profile_source: string;
  schema_profile: string;
  failure_stage: string | null;
  error_code: string | null;
  safe_provider_error_type: string | null;
  safe_provider_error_param: string | null;
  provider_request_id: string | null;
  fallback_from: string | null;
  fallback_to: string | null;
};
export type BuilderConversationMessage = {
  message_id: string;
  conversation_id: string;
  sequence: number;
  role: "user" | "assistant" | "system";
  kind: BuilderMessageKind;
  content: string;
  operation_id: string | null;
  payload: Record<string, string>;
  attachments?: ConversationAttachment[];
  created_at: string;
};
export type BuilderOperationStatus = "in_progress" | "waiting" | "succeeded" | "failed" | "rejected";
export type BuilderRunClassification = "none" | "repairable" | "user_action" | "environment" | "semantic";
export type BuilderRunObservation = {
  run_id: string | null;
  agent_id: string;
  version_id: string | null;
  status: string;
  runtime_model_id: string;
  runtime_model_source: string;
  output_summary: string | null;
  failure_code: string | null;
  failed_node: string | null;
  tool_failure: string | null;
  knowledge_failure: string | null;
  approval_required: boolean;
  duration_ms: number | null;
  evidence_count: number;
  classification: BuilderRunClassification;
  explanation: string;
  repair_proposal_id: string | null;
  repair_code: string | null;
  next_action: string | null;
};
export type BuilderConversationOperation = {
  operation_id: string;
  conversation_id: string;
  kind: string;
  target_kind: BuilderTargetKind | null;
  status: BuilderOperationStatus;
  retry_of: string | null;
  error_code: string | null;
  proposal_id: string | null;
  run_id: string | null;
  factory_session_id: string | null;
  workspace_id?: string | null;
  created_at: string;
  updated_at: string;
  diagnostic: Record<string, string>;
  generation_feedback?: string[];
  has_request: boolean;
  events: BuilderOperationEvent[];
  receipts: BuilderHarnessReceipt[];
  run_observation?: BuilderRunObservation | null;
};
export type BuilderTestRunRequest = {
  agent_id?: string;
  workspace_id?: string;
  inputs: Record<string, unknown>;
  locale: "zh" | "en";
};
export type BuilderTestRunCommandRequest = {
  command: "approve" | "reject" | "stop";
  locale: "zh" | "en";
  expected_request_id?: string;
};
export type BuilderTestRepairRequest = {
  locale: "zh" | "en";
};
export type BuilderConversationSummary = {
  conversation_id: string;
  project_id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
  last_activity_at: string;
  last_operation_status: BuilderOperationStatus | null;
};
export type BuilderConversationSnapshot = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  conversation: BuilderConversationSummary;
  messages: BuilderConversationMessage[];
  operations: BuilderConversationOperation[];
  resolution: BuilderResolution | null;
  factory_session: FactorySession | null;
};
export type BuilderTurnRequest = {
  conversation_id?: string;
  content?: string;
  focus: { kind: EditTargetKind; target_id: string } | null;
  locale: "zh" | "en";
  retry_of?: string;
  request_limit?: number;
  resume_only?: boolean;
};
export type BuilderRecordKind = "proposal_reference" | "reject" | "confirm" | "apply_summary" | "validation_summary";
export type BuilderConversationRecordRequest = {
  kind: BuilderRecordKind;
  content: string;
  operation_id?: string;
  proposal_id?: string;
  details?: Record<string, string>;
};
export type BuilderActivityItem = {
  kind: "conversation";
  id: string;
  conversation_id: string;
  project_id?: string;
  title: string;
  status: string;
  operation_kind: string;
  occurred_at: string;
};
export type BuilderActivityResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  items: BuilderActivityItem[];
};
export type BuilderConversationRenameRequest = {
  title: string;
};
export type BuilderConversationDeleted = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  conversation_id: string;
  deleted: true;
};

export type WorkspaceTrashKind = "project" | "agent" | "workflow" | "knowledge" | "conversation" | "plugin";
export type WorkspaceTrashItem = {
  kind: WorkspaceTrashKind;
  id: string;
  name: string;
  project_id: string | null;
  project_name: string | null;
  removed_at: string;
  expires_at: string;
  restorable: boolean;
};
export type ListWorkspaceTrashResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  retention_days: number;
  items: WorkspaceTrashItem[];
};
export type WorkspaceTrashMutationResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  kind: WorkspaceTrashKind;
  id: string;
  restored?: true;
  deleted?: true;
};
export type EditProposalCommand = "apply" | "reject" | "undo";
export type CreateEditProposalRequest = {
  target_kind: EditTargetKind;
  target_id: string;
  instruction: string;
  expected_revision: number;
  expected_etag: string;
};
export type CreateKnowledgeBindingRequest = {
  agent_id: string;
  instruction: string;
  expected_revision: number;
  expected_etag: string;
};
export type KnowledgeBindingPlan = {
  reference: string;
  name: string;
  source_file_hash: string;
  index_status: KnowledgeProcessing["index_status"];
  chunk_count?: number | null;
  failure_reason: string | null;
  runnable: boolean;
  required_action: "build_index" | "rebuild_index" | null;
};
export type CreateResourceBindingRequest = {
  agent_id: string;
  instruction: string;
  expected_revision: number;
  expected_etag: string;
};
export type CreateValidationRepairRequest = {
  agent_id: string;
  reference: string;
  code: string;
  expected_revision: number;
  expected_etag: string;
};
export type ValidationRepairPlan = {
  code: string;
  kind: string;
  reference: string;
  name: string;
  repairable: true;
  automatic_upgrade: false;
  project_resource_changed: false;
  locked_hash?: string | null;
  bound_content_hash?: string | null;
  content_hash?: string | null;
  required_permissions?: ResourcePermissions;
  target_kind: "agent";
  impact: string;
};
export type ResourceBindingReadiness =
  | "ready"
  | "requires_configuration"
  | "design_only"
  | "unavailable"
  | "quarantined"
  | "unsupported"
  | "stale";
export type ResourceBindingPlan = {
  reference: string;
  name: string;
  bound_content_hash: string;
  catalog_content_hash: string;
  binding_status: "current" | "stale";
  readiness: ResourceBindingReadiness;
  availability: ResourceAvailability;
  runtime_status: ResourceRuntimeStatus;
  required_permissions: ResourcePermissions;
  blocking_reasons: Array<{ code: string; message: string }>;
  project_resource_changed: false;
  automatic_upgrade: false;
};
export type EditProposalChange = {
  path: string;
  operation: "add" | "remove" | "replace";
  before: JsonValue;
  after: JsonValue;
};
export type EditProposal = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  proposal_id: string;
  project_id: string;
  target_kind: EditTargetKind;
  target_id: string;
  instruction: string;
  created_at: string;
  base_revision: number;
  base_etag: string;
  candidate_source: StudioSource;
  changes: EditProposalChange[];
  permission_changes: EditProposalChange[];
  knowledge_binding?: KnowledgeBindingPlan;
  resource_binding?: ResourceBindingPlan;
  validation_repair?: ValidationRepairPlan;
  impact: {
    target_kind: EditTargetKind;
    target_id: string;
    scope: "single_draft";
    immutable_versions_changed: false;
    runs_started: false;
  };
  validation: Omit<ValidateResponse, "file_hash"> & {
    agent_calls?: { node_id: string; agent_id: string; version_id: string }[];
  };
  state: "review" | "applied" | "rejected" | "undone";
  stale: boolean;
  applied_revision: number | null;
};
export type ComponentProposalCommand = "apply" | "reject";
export type CustomComponentProposal = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  proposal_id: string;
  proposal_kind: "create_custom_component";
  project_id: string;
  target_kind: "custom_component";
  target_id: string;
  instruction: string;
  created_at: string;
  component_plan: {
    component_id: string;
    display_name: string;
    description: string;
    capability_requirement: string;
    agent_step?: string;
    agent_step_key?: string;
    inputs: TypedFields;
    outputs: TypedFields;
    implementation: JsonObject;
    dependencies: Array<{ reference: string; content_hash: string }>;
    required_permissions: ResourcePermissions;
    readiness_expectation: "ready" | "requires_configuration";
    why?: string;
  };
  continuation: "agent" | "direct_component";
  conversation_id: string;
  operation_id: string;
  factory_session_id: string | null;
  changes: EditProposalChange[];
  permission_changes: EditProposalChange[];
  impact: {
    target_kind: "custom_component";
    target_id: string;
    scope: "project_resource";
    immutable_versions_changed: false;
    runs_started: false;
    creates_component: true;
  };
  validation: {
    valid: boolean;
    readiness_expectation: "ready" | "requires_configuration";
    dependencies: Array<{ reference: string; content_hash: string }>;
  };
  state: "review" | "applied" | "rejected";
  stale: boolean;
  created_component: {
    component_id: string;
    display_name: string;
    version: string;
    reference: string;
    content_hash: string;
    readiness: "ready" | "requires_configuration" | "design_only" | "unavailable";
    implementation_kind: CustomComponentImplementationKind;
  } | null;
};
export type ComponentProposalCommandRequest = {
  command: ComponentProposalCommand;
  confirm: boolean;
  locale: "zh" | "en";
};
export type AgentCreationProposalCommandRequest = {
  command: "apply" | "reject";
  confirm: boolean;
  locale: "zh" | "en";
};
export type ListEditProposalsResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  proposals: EditProposal[];
};

export type AgentVersionSnapshot = {
  version_id: string;
  agent_id: string;
  source_hash: string;
  behavior_hash: string;
  created_at: string;
  source: AgentSource;
  committed?: boolean;
};
export type ListAgentVersionsResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  versions: AgentVersionSnapshot[];
};
export type WorkflowVersionSnapshot = {
  version_id: string;
  workflow_id: string;
  source_hash: string;
  behavior_hash: string;
  created_at: string;
  source: WorkflowSource;
  committed?: boolean;
};
export type ListWorkflowVersionsResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  versions: WorkflowVersionSnapshot[];
};

export type CatalogBinding = {
  kind: "skill" | "policy" | "template" | "mcp_tool" | "knowledge" | "tool";
  reference: string;
  x: number;
  y: number;
};

export type RuntimeApiProfileInput = {
  provider: string;
  base_url: string;
  model_id: string;
  api_key_env: string;
};

export type RuntimeApiProfileSummary = RuntimeApiProfileInput & {
  configured: boolean;
};

export type CommunityAgentOrigin = {
  owner_handle: string;
  slug: string;
  version: string;
  source_hash: string;
  imported_at: string;
};

export type ProjectAgentRecord = {
  agent_id: string;
  slug: string;
  name: string;
  description: string;
  version?: string;
  pinned: boolean;
  source_path: string;
  source_file_hash: string;
  parent_agent_id?: string | null;
  runtime_profile?: RuntimeApiProfileSummary | null;
  community_origin?: CommunityAgentOrigin;
};

export type ProjectWorkflowRecord = {
  workflow_id: string;
  slug: string;
  name: string;
  description: string;
  version?: string;
  source_path: string;
  source_file_hash: string;
};

export type KnowledgeProcessing = {
  origin: "upload" | "project_document";
  filename: string;
  media_type: "text/plain" | "text/markdown";
  uploaded_content_hash: string | null;
  content_hash: string;
  ingest_status: "ingested";
  parse_status: "parsed";
  index_status: "not_indexed" | "indexed" | "stale" | "failed";
  chunk_count?: number | null;
  failure_reason: string | null;
  updated_at: string;
};

export type KnowledgeCloudFileReference = {
  kind: "cloud_file";
  file_id: string;
};

export type ProjectKnowledgeRecord = {
  knowledge_id: string;
  processing?: KnowledgeProcessing;
  slug: string;
  name: string;
  description: string;
  version?: string;
  source_path: string;
  source_file_hash: string;
  source_ref?: KnowledgeCloudFileReference;
};

export type ProjectSummaryResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  origin?: ProjectOrigin;
  root_path: string;
  name: string;
  description: string;
  pinned: boolean;
  pinned_at: string | null;
  indexed_at: string;
  manifest_hash: string;
  default_agent_id: string | null;
  agent_count: number;
  agents: ProjectAgentRecord[];
  workflows?: ProjectWorkflowRecord[];
  workflow_count?: number;
  knowledge?: ProjectKnowledgeRecord[];
  knowledge_count?: number;
  runtime_profile?: RuntimeApiProfileSummary | null;
};

export type AgentTemplate = {
  template_id: string;
  name: string;
  description: string;
  default_slug: string;
};

export type ListAgentTemplatesResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  templates: AgentTemplate[];
};

export type TemplateSelection = {
  template_id: string;
  slug: string;
  name: string;
  description: string;
};

export type AgentDetailResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  agent_id: string;
  slug: string;
  name: string;
  description: string;
  source_path: string;
  source_file_hash: string;
  draft_id: string;
  revision: number;
  etag: string;
  source: AgentSource;
};

export type ListProjectsResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  projects: ProjectSummaryResponse[];
};

export type ProjectSyncState =
  | "local_only"
  | "pending_upload"
  | "synced"
  | "pending_push"
  | "pending_pull"
  | "conflict"
  | "error";

export type ProjectSyncOperation = "ensure" | "push" | "pull" | "archive";

export type ProjectSyncStateResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  sync_enabled: boolean;
  state: ProjectSyncState;
  cloud_revision: number | null;
  local_metadata_hash: string | null;
  last_synced_hash: string | null;
  last_synced_at: string | null;
  pending_operation: ProjectSyncOperation | null;
  remote_name: string | null;
  remote_description: string | null;
  error_code: string | null;
};

export type MarkProjectSyncPendingRequest = {
  operation: ProjectSyncOperation;
};

export type RecordProjectSyncRequest = {
  state: ProjectSyncState;
  cloud_revision?: number | null;
  last_synced_hash?: string | null;
  pending_operation?: ProjectSyncOperation | null;
  remote_name?: string | null;
  remote_description?: string | null;
  error_code?: string | null;
};

export type LocalArtifactSyncState =
  | "local_only"
  | "synced"
  | "pending_push"
  | "pending_pull"
  | "conflict"
  | "error";

export type LocalArtifactManifestItem = {
  artifact_kind: string;
  artifact_id: string;
  content_hash: string | null;
  revision: number;
  cloud_revision: number | null;
  deleted: boolean;
  state: LocalArtifactSyncState;
};

export type LocalArtifactManifestResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  artifacts: LocalArtifactManifestItem[];
};

export type LocalArtifactEnvelopeResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  artifact: Record<string, unknown>;
};

export type MaterializeArtifactRequest = {
  envelope: Record<string, unknown>;
};

export type RecordArtifactSyncRequest = {
  artifact_kind: string;
  artifact_id: string;
  state: Exclude<LocalArtifactSyncState, "local_only">;
  cloud_revision?: number | null;
  last_synced_hash?: string | null;
  error_code?: string | null;
};

export type ListAgentsResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  agents: ProjectAgentRecord[];
};

export type CreateProjectRequest = {
  /** Empty or omitted names are allocated by the local service. */
  name?: string;
  description: string;
  runtime_profile?: RuntimeApiProfileInput | null;
};

/** Mutable local Project presentation state. The manifest remains authoritative. */
export type UpdateProjectRequest = {
  name?: string;
  description?: string;
  pinned?: boolean;
  runtime_profile?: RuntimeApiProfileInput | null;
};

export type DeleteProjectResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  disposition: "trashed" | "unlinked";
  removed_at: string;
};

/** Agent presentation mutations are intentionally closed in V1. */
export type UpdateAgentRequest = {
  pinned?: true;
  runtime_profile?: RuntimeApiProfileInput | null;
};

export type DeleteAgentResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  agent_id: string;
  disposition: "trashed";
  removed_at: string;
  project: ProjectSummaryResponse;
};

export type CreateAgentRequest =
  | {
    mode: "blank";
    name?: string;
    description?: string;
    parent_agent_id?: string | null;
    runtime_profile?: RuntimeApiProfileInput | null;
  }
  | {
    mode: "template";
    template_id: string;
    name?: string;
    description?: string;
    parent_agent_id?: string | null;
    runtime_profile?: RuntimeApiProfileInput | null;
  };

/** The create and import endpoints return the created Agent's durable identity. */
export type CreatedAgentResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  agent_id: string;
  slug: string;
  name: string;
  description: string;
  source_path: string;
  source_file_hash: string;
  parent_agent_id?: string | null;
  runtime_profile?: RuntimeApiProfileSummary | null;
  community_origin?: CommunityAgentOrigin;
};

export type RuntimeProfileResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  agent_id: string | null;
  source: "project" | "agent";
  profile: RuntimeApiProfileSummary | null;
};

export type ProviderCredentialStatus = "unverified" | "active" | "invalid" | "disabled";
export type ProviderCredentialScope = "device" | "cloud";
export type ProviderCredentialSecretState = "available" | "missing" | "unavailable";
export type ProviderCredentialReadiness = "ready" | "needs_reentry" | "unavailable" | "disabled" | "invalid" | "unverified";
export const MODEL_CAPABILITY_NAMES = ["text_input", "image_input", "audio_input", "video_input", "text_generation", "image_generation", "image_editing", "audio_generation", "video_generation", "structured_output", "tool_calling", "reasoning", "speech_to_text", "text_to_speech", "embeddings", "reranking"] as const;
export type ModelCapabilityName = (typeof MODEL_CAPABILITY_NAMES)[number];
export type ModelCapabilityStatus = "supported" | "unsupported" | "unknown";
export type ModelCapabilityEvidenceSource = "provider_metadata" | "provider_adapter" | "active_probe" | "user_declared" | "inferred";
export type ModelCapabilityEvidence = { source: ModelCapabilityEvidenceSource; observed_at: string; detail?: string };
export type ModelCapabilityRecord = { status: ModelCapabilityStatus; evidence: ModelCapabilityEvidence | null };
export type ModelProfile = {
  model_profile_id: string;
  provider_connection_id: string;
  provider_type: string;
  provider_label: string;
  provider_model_id: string;
  display_name: string;
  enabled: boolean;
  listed: boolean;
  metadata: Record<string, JsonValue>;
  capabilities: Record<ModelCapabilityName, ModelCapabilityRecord>;
  verification: { state: "unknown" | "declared" | "verified" | "failed" | "stale"; source: ModelCapabilityEvidenceSource | null; verified_at: string | null; last_checked_at: string | null; stale_reason: string | null; error_code: string | null };
  capability_revision: number;
  capability_digest: string;
  discovered_at: string | null;
  created_at: string;
  updated_at: string;
  connection_readiness: ProviderCredentialReadiness;
  registry_ready: boolean;
};
export type ModelRegistryResponse = { schema_version: typeof LOCAL_API_SCHEMA_VERSION; models: ModelProfile[] };
export type ModelDiscoveryResponse = { schema_version: typeof LOCAL_API_SCHEMA_VERSION; discovery: { state: "ready" | "failed" | "stale"; discovered_at: string | null; models_found: number; error_code?: string }; models: ModelProfile[] };
export type ModelDefault = { role: string; model_profile_id: string; provider_connection_id: string; provider_model_id: string; capability_digest: string; capability_revision: number; updated_at: string };
export type ModelDefaultsResponse = { schema_version: typeof LOCAL_API_SCHEMA_VERSION; defaults: ModelDefault[] };
export type ModelCapabilityRequirement = { slot: string; actor_id?: string | null; required: ModelCapabilityName[]; optional: ModelCapabilityName[]; reason: string; source: string };
export type ModelResolutionStatus = "already_bound" | "will_bind" | "needs_setup" | "missing_capability" | "unsupported";
export type ModelResolution = ModelCapabilityRequirement & { status: ModelResolutionStatus; selected_model_profile_id?: string | null; selected_model_display_name?: string | null; selected_provider_label?: string | null; issue?: { code: string; message: string; missing: ModelCapabilityName[]; unknown: ModelCapabilityName[]; unsupported: ModelCapabilityName[] } | null };
export type ProviderCredential = {
  schema_version?: typeof LOCAL_API_SCHEMA_VERSION;
  credential_id: string;
  owner_id: string;
  provider_type: string;
  label: string;
  base_url: string;
  status: ProviderCredentialStatus;
  credential_scope: ProviderCredentialScope;
  masked_hint: string;
  capabilities: Record<string, JsonValue>;
  default_model_id: string | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
  validated_at: string | null;
  last_used_at: string | null;
  discovery_state?: "unknown" | "ready" | "failed" | "stale";
  discovery_checked_at?: string | null;
  discovered_at?: string | null;
  discovery_error_code?: string | null;
  secret_state: ProviderCredentialSecretState;
  readiness: ProviderCredentialReadiness;
};
export type ProviderCredentialListResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  credentials: ProviderCredential[];
};
export type ProviderCredentialValidationResponse = {
  valid: boolean;
  code: string;
  message: string;
  credential: ProviderCredential;
  discovery?: ModelDiscoveryResponse["discovery"];
  models?: ModelProfile[];
  model_selection?: {
    provider_model_id: string | null;
    state: "ready" | "needs_setup" | "unconfigured";
  };
};
export type CreateProviderCredentialRequest = {
  provider_type: string;
  label: string;
  api_key: string;
  base_url?: string;
  default_model_id?: string;
  make_default?: boolean;
};
export type RuntimeBinding = {
  project_id: string;
  agent_id: string | null;
  slot: string;
  credential_id: string;
  model_id: string;
  source: "explicit" | "project" | "user_default";
  updated_at: string;
};
export type RuntimeBindingResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  agent_id: string | null;
  slot: string;
  binding: RuntimeBinding | null;
  credential: ProviderCredential | null;
  explicit: RuntimeBinding | null;
};

export type OpenProjectRequest = {
  root_path: string;
};

export type ImportProjectPathRequest = {
  path: string;
};

export type ProjectFileKind =
  | "manifest"
  | "agent_source"
  | "readme"
  | "test"
  | "resource"
  | "resource_manifest"
  | "project_test"
  | "workflow"
  | "component"
  | "knowledge"
  | "asset"
  | "file";

export type ProjectFileRecord = {
  path: string;
  kind: ProjectFileKind;
  byte_length: number;
  agent_id?: string;
};

export type ProjectFilesResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  files: ProjectFileRecord[];
};

export type ProjectFileContentResponse = ProjectFileRecord & {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  text: string;
};

export type ProjectFileMaterializeResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  status: "materialized";
  relative_path: string;
  sha256: string;
  size_bytes: number;
};

export type RevealProjectRequest = {
  project_id: string;
};

export type RevealProjectResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  status: "revealed";
  root_path: string;
};

/** Result of a native desktop directory picker. Paths never come from typed UI input. */
export type SelectDirectoryResponse =
  | {
    schema_version: typeof LOCAL_API_SCHEMA_VERSION;
    status: "selected";
    root_path: string;
  }
  | {
    schema_version: typeof LOCAL_API_SCHEMA_VERSION;
    status: "cancelled";
    root_path: null;
  };

/** Result of a native desktop archive picker. Paths never come from typed UI input. */
export type SelectArchiveResponse =
  | {
    schema_version: typeof LOCAL_API_SCHEMA_VERSION;
    status: "selected";
    path: string;
  }
  | {
    schema_version: typeof LOCAL_API_SCHEMA_VERSION;
    status: "cancelled";
    path: null;
  };

export type DraftResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  draft_id: string;
  revision: number;
  etag: string;
  source_file_hash: string;
  source: AgentSource;
};

export type WorkflowDraftResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  draft_id: string;
  revision: number;
  etag: string;
  source_file_hash: string;
  source: WorkflowSource;
};

export type SaveDraftResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  revision: number;
  etag: string;
  source: AgentSource;
};

export type SaveWorkflowDraftResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  revision: number;
  etag: string;
  source: WorkflowSource;
};

export type SaveDraftRequest = {
  source: AgentSource;
  expected_revision: number;
};

export type SaveWorkflowDraftRequest = {
  source: WorkflowSource;
  expected_revision: number;
};

export type CreateWorkflowRequest = {
  name?: string;
  description?: string;
};

export type CreatedWorkflowResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  workflow_id: string;
  slug: string;
  name: string;
  description: string;
  version?: string;
  source_path: string;
  source_file_hash: string;
  node_count?: number;
  transition_count?: number;
};

export type CreateKnowledgeRequest = {
  name?: string;
  description?: string;
  text?: string;
};

export type UpdateKnowledgeRequest = {
  name?: string;
  description?: string;
  text?: string;
};

export type KnowledgeDocumentResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  processing?: KnowledgeProcessing;
  knowledge_id: string;
  slug: string;
  name: string;
  description: string;
  version?: string;
  source_path: string;
  source_file_hash: string;
  text: string;
  source_ref?: KnowledgeCloudFileReference;
};

export type DeleteKnowledgeResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  knowledge_id: string;
  disposition: "trashed";
  removed_at: string;
  project: ProjectSummaryResponse;
};

export type DeleteWorkflowResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  workflow_id: string;
  disposition: "trashed";
  removed_at: string;
  project: ProjectSummaryResponse;
};

export type AgentDependencyStatus =
  | "ready"
  | "missing"
  | "lock_missing"
  | "lock_mismatch"
  | "kind_mismatch"
  | "configuration_required"
  | "runtime_unavailable"
  | "review_required"
  | "permission_denied"
  | "secret_declaration_missing"
  | "context_not_declared"
  | "context_too_large"
  | "project_binding_stale"
  | "resource_unbound";

export type AgentDependencyCheck = {
  reference: string;
  kind: ResourceKind | "knowledge";
  name: string;
  status: AgentDependencyStatus;
  detail: string;
  locked_hash?: string;
  bound_content_hash?: string;
  blocking_reasons?: Array<{ code: string; message: string }>;
  content_hash?: string;
  version?: string;
  availability?: ResourceAvailability;
  runtime_status?: ResourceRuntimeStatus;
  runtime_mode?: "tool_adapter" | "model_context" | "source_policy" | "design_only" | "knowledge_context" | "catalog";
  required_permissions?: ResourcePermissions;
  byte_length?: number;
  used_by: string[];
  bound_by: string[];
  project_binding_status?: "current" | "stale" | "unbound" | "unknown";
};

export type AgentDependencySummary = {
  total: number;
  ready: number;
  attention: number;
};

export type ValidateResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  valid: boolean;
  source_hash: string;
  behavior_hash: string;
  lock_hash: string;
  file_hash: string;
  dependencies?: AgentDependencyCheck[];
  dependency_summary?: AgentDependencySummary;
  runtime_ready?: boolean;
  runtime_ready_scope?: "agent_dependencies";
};

export type CommitResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  version_id: string;
  agent_id?: string;
  workflow_id?: string;
  source_hash: string;
  behavior_hash: string;
  lock_hash: string;
  file_hash: string;
};

/** Compare-and-swap boundary for materializing an immutable Agent version. */
export type CommitRequest = {
  expected_revision: number;
};

export type StartAgentRunRequest = {
  inputs: Record<string, JsonValue>;
  conversation_id?: string | null;
  source?: "draft" | "committed";
  version_id?: string | null;
};

export type RunCommandRequest = {
  command: "approve" | "reject" | "stop" | "resume" | "retry" | "reply" | "extend_budget";
  checkpoint_id?: string;
  inputs?: Record<string, JsonValue>;
  expected_request_id?: string;
  additional_turns?: number;
};

export type EvaluationBaseline = { kind: "user" | "fixture" | "reference" | "model"; reference: string; revision: string };
export type EvaluationMethod = "equals" | "number_equals" | "set_equals" | "artifact_integrity" | "human_review";
export type EvaluationCheck = { id: string; label: string; required: boolean; path: string[]; method: EvaluationMethod; expected?: JsonValue; baseline?: EvaluationBaseline };
export type EvaluationSpec = { version: "1"; version_id: string; checks: EvaluationCheck[] };
export type EvaluationReviewDecision = { check_id: string; outcome: "pass" | "fail" | "unknown"; reason: string };
export type EvaluationReviewRequest = {
  expected_report_id: string; version_id: string; spec_hash: string; result_hash: string;
  decisions: EvaluationReviewDecision[];
};
export type EvaluationHumanReview = EvaluationReviewDecision & {
  review_id: string; source: "local_user"; created_at: string; base_evaluation_id: string;
};
export type EvaluationFinding = {
  id: string; label: string; required: boolean; path: string[]; method: EvaluationMethod;
  status: "pass" | "fail" | "unknown" | "not_evaluated" | "awaiting_human";
  code: string; baseline: EvaluationBaseline | null; actual_hash?: string; expected_hash?: string; actual_value?: JsonValue;
  evidence: { kind: "artifact"; artifact_id: string; sha256: string; size_bytes: number; source_run_id: string | null }[];
  human_review?: EvaluationHumanReview;
};
export type EvaluationReport = {
  schema_version: "1.0"; evaluator_version: "1" | "2"; scope: "declared_checks";
  evaluation_id: string; project_id: string; target_kind: "agent" | "workflow"; target_id: string;
  run_id: string; version_id: string; run_status: AgentRunResponse["status"];
  source_hash: string; behavior_hash: string; lock_hash: string; spec_hash: string;
  input_hash: string | null; input_evidence: "persisted" | "not_saved"; result_hash: string | null;
  created_at: string; spec: EvaluationSpec; decision: "accepted" | "rejected" | "inconclusive";
  checks: EvaluationFinding[]; output_contract: "pass" | "fail" | "not_evaluated";
  independent_scope: "baseline_comparison_and_artifact_integrity_only" | "baseline_comparison_artifact_integrity_and_user_review";
  root_evaluation_id?: string; parent_evaluation_id?: string;
  review?: { review_id: string; source: "local_user"; created_at: string; base_evaluation_id: string; supersedes_review_id: string | null; decisions: EvaluationReviewDecision[] };
};
export type RunEvaluationsResponse = { schema_version: "1.0"; reports: EvaluationReport[] };

export type ComponentRuntimeStatus =
  | "supported"
  | "runtime_not_configured"
  | "runtime_not_supported";

export type ComponentDefinition = {
  type: FlowNode["component_type"];
  fields: string[];
  output_ports: FlowTransition["port"][];
  runtime_status: ComponentRuntimeStatus;
};

export type ListComponentsResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  components: ComponentDefinition[];
};

/** Catalog identity is immutable; API availability/runtime_status are live host projections. */
export type ResourceKind =
  | "component"
  | "tool"
  | "mcp_tool"
  | "skill"
  | "policy"
  | "template";

export type ResourceAvailability =
  | "ready"
  | "requires_configuration"
  | "design_only"
  | "quarantined"
  | "disabled"
  | "unavailable";

export type ResourceRuntimeStatus =
  | "supported"
  | "runtime_not_configured"
  | "runtime_not_supported";

export type ResourceOrigin = "builtin" | "workshop" | "discovered" | "project";

export type ResourcePermissions = {
  network_hosts: string[];
  tools: string[];
  filesystem_read_roots: string[];
  filesystem_write_roots: string[];
  shell_workspace_only: boolean;
};

export type ResourceDescriptor = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  resource_id: string;
  kind: ResourceKind;
  component_class?: "primitive" | "composite";
  version: string;
  reference: string;
  name: string;
  description: string;
  origin: ResourceOrigin;
  content_hash: string;
  availability: ResourceAvailability;
  factory_selectable: boolean;
  runtime_status: ResourceRuntimeStatus;
  required_permissions: ResourcePermissions;
  tags: string[];
  spec: JsonObject;
  capabilities?: string[];
  configuration_requirements?: Array<{ code: string; message: string; satisfied: boolean }>;
  blocking_reasons?: Array<{ code: string; message: string }>;
  dependencies?: JsonValue[];
  compatibility?: { scope: string; execution: string; network_verified: boolean };
};

export type ResourceKindCount = {
  kind: ResourceKind;
  count: number;
};

export type ListResourcesResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  resources: ResourceDescriptor[];
  kinds: ResourceKindCount[];
};

export type ProjectResourceScope = "project" | "used_unbound" | "builtin";
export type ProjectResourceBindingStatus = "current" | "stale" | "unbound" | "builtin";

export type ProjectResourceUsage = {
  kind: "agent" | "workflow";
  resource_id: string;
  name: string;
};

export type ProjectResourceDescriptor = ResourceDescriptor & {
  scope: ProjectResourceScope;
  binding_status?: ProjectResourceBindingStatus;
  binding_source: "manual" | "factory" | "imported" | "reconciled" | null;
  bound_content_hash: string | null;
  used_by: ProjectResourceUsage[];
};

export type ProjectResourcesResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  resources: ProjectResourceDescriptor[];
  missing_references: string[];
  missing_bindings?: { reference: string; content_hash: string; source: string; used_by: ProjectResourceUsage[] }[];
  project_count: number;
  used_count: number;
  unbound_count: number;
  builtin_count: number;
  stale_count?: number;
};

export type CustomComponentImplementationKind =
  | "model_recipe"
  | "tool_wrapper"
  | "transform"
  | "composite_graph";
export type CustomComponentReadiness =
  | "ready"
  | "requires_configuration"
  | "design_only"
  | "unavailable";
export type CustomComponentDefinition = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  component_id: string;
  project_id: string;
  slug: string;
  display_name: string;
  description: string;
  version: string;
  reference: string;
  content_hash: string;
  inputs: TypedFields;
  outputs: TypedFields;
  implementation: JsonObject;
  metadata: Record<string, string>;
  dependencies: { reference: string; content_hash: string }[];
  required_permissions: ResourcePermissions;
  readiness: CustomComponentReadiness;
  provenance: "manual" | "builder" | "imported";
  lifecycle: "draft" | "active" | "deprecated";
  deprecated: boolean;
  created_at: string;
  updated_at: string;
};
export type CustomComponentVersionSummary = {
  version: string;
  reference: string;
  lifecycle: "active" | "deprecated";
  implementation_kind: CustomComponentImplementationKind;
  readiness: CustomComponentReadiness;
  content_hash: string;
};
export type CustomComponentSummary = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  component_id: string;
  project_id: string;
  slug: string;
  display_name: string;
  description: string;
  draft: CustomComponentDefinition | null;
  latest_version: string | null;
  versions: CustomComponentVersionSummary[];
};
export type ListCustomComponentsResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  components: CustomComponentSummary[];
};
export type CreateCustomComponentRequest = {
  display_name: string;
  description: string;
  inputs: TypedFields;
  outputs: TypedFields;
  implementation: JsonObject;
  metadata?: Record<string, string>;
  provenance?: "manual" | "builder" | "imported";
};
export type UpdateCustomComponentRequest = Partial<CreateCustomComponentRequest>;

export type AddProjectResourceRequest = {
  reference: string;
  content_hash?: string;
  source?: "manual" | "factory" | "imported" | "reconciled";
};

export type ListResourceFilters = {
  kind?: ResourceKind;
  availability?: ResourceAvailability;
};

export type FactorySessionState =
  | "collecting"
  | "ready"
  | "generating"
  | "review"
  | "missing_capability"
  | "completed"
  | "abandoned";

export type FactoryRunAvailability =
  | "ready"
  | "requires_configuration"
  | "design_only"
  | "unavailable";

export type FactoryMessage = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  message_id: string;
  sequence: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type FactoryResourceBindStatus =
  | "already_bound"
  | "will_bind"
  | "requires_configuration"
  | "needs_configuration"
  | "unavailable"
  | "missing";

export type FactoryResourcePlanKind = ResourceKind | "knowledge" | "capability";

export type FactoryResourcePlanItem = {
  reference: string;
  kind: FactoryResourcePlanKind;
  availability: ResourceAvailability;
  runtime_status: ResourceRuntimeStatus;
  name?: string;
  bind_status?: FactoryResourceBindStatus;
  capability?: string;
  reason?: string;
  source_count?: number;
  runtime_support?: "full" | "partial" | "none";
  factory_status?: "generatable" | "requires_user_configuration" | "requires_external_integration" | "unsupported";
  factory_strategy?: "skill_instruction" | "http_tool_wrapper" | "filesystem_tool_wrapper" | "none";
};

export type ResourceFactoryPlan = {
  capability: string;
  status: "generatable" | "requires_user_configuration" | "requires_external_integration" | "unsupported";
  strategy: "skill_instruction" | "http_tool_wrapper" | "filesystem_tool_wrapper" | "none";
  can_generate: boolean;
  reason: string;
  risk_level: "low" | "medium" | "high";
  resource_kind?: string | null;
  requirements: string[];
  draft?: JsonObject | null;
  validation?: JsonObject | null;
  published?: JsonObject | null;
  snapshot_hash?: string | null;
  proposal_id?: string | null;
  operation_id?: string | null;
};

export type FactoryMissingCapability = {
  kind: string;
  reference: string;
  reason: string;
  proposal: {
    action: "quarantined_resource_draft";
    executable: false;
  };
};

export type FactorySession = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  session_id: string;
  project_id: string;
  state: FactorySessionState;
  ready: boolean;
  next_prompt: string;
  resource_plan: FactoryResourcePlanItem[];
  blueprint: JsonObject | null;
  diagnostics: string[];
  missing_capabilities: FactoryMissingCapability[];
  candidate: { name: string; slug?: string } | null;
  target_kind?: "agent" | "workflow";
  execution_kind?: "loop" | "graph" | "workflow";
  run_availability: FactoryRunAvailability;
  executes_drafts: false;
  revision: number;
  created_at: string;
  updated_at: string;
  messages: FactoryMessage[];
  resource_factory_plans?: ResourceFactoryPlan[];
  product_shape?: string;
  proposal_preview?: JsonObject;
  blocked_reason?: string;
};

export type ProviderCapabilitySupport = "supported" | "unsupported" | "unknown";

export type ProviderCapabilityProfile = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  provider_id: string;
  provider_family: "moonshot" | "openai_compatible";
  model: string;
  endpoint_kind: "chat_completions" | "responses" | "compatible_chat";
  base_url_fingerprint: string;
  structured_output: "json_schema" | "json_object";
  schema_flavor: "moonshot_mfjs" | "none";
  schema_profile: "mfjs" | "openai_json_schema" | "unknown";
  strict_json_schema: boolean;
  json_object_fallback: boolean;
  reasoning_effort: boolean;
  supports_reasoning_effort: boolean;
  strict_json_schema_support: ProviderCapabilitySupport;
  json_object_support: ProviderCapabilitySupport;
  source: "static_known" | "probe" | "fallback";
  status: "known" | "unknown" | "stale" | "failed" | "inconclusive";
  checked_at: string | null;
  probe_version: string;
  probed: boolean;
  error_class: string | null;
  summary: {
    provider: string;
    model: string;
    structured_output: string;
    schema_profile: string;
    json_object_fallback: string;
    status: string;
    checked_at: string;
    error_class: string;
  };
};

export type FactoryStatus = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  configured: boolean;
  model_id: string;
  model_base_url: string;
  model_api_key_env: string;
  reasoning_effort: "low" | "high" | "max";
  repair_attempts: number | null;
  generation_max_requests?: number;
  generation_timeout_seconds?: number;
  executes_drafts: false;
  capability_profile: ProviderCapabilityProfile;
};

export type RuntimeStatus = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  configured: boolean;
  model_id: string;
  model_base_url: string;
  model_api_key_env: string;
  reasoning_effort: "low" | "high" | "max";
  allow_process_environment_key: boolean;
  user_provided_only: boolean;
  modalities?: RuntimeModelCapabilities;
};

export type RuntimeProfileValidation = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  valid: boolean;
  configured: boolean;
  model_available: boolean;
  provider: string;
  base_url: string;
  model_id: string;
  api_key_env: string;
  code: string;
  message: string;
};

export type RuntimeReadinessCheck = {
  id: "dependencies" | "model" | "modalities" | "tools" | "image_model";
  ready: boolean;
  code: string;
  detail: string;
};

export type RuntimeSetupIssue = {
  code: string;
  scope: string;
  resource_type: string;
  requirement: ModelCapabilityName[];
  message: string;
  action: "configure_model" | "verify_model" | "rebind_model";
  agent_id?: string;
  node_id?: string;
  model_profile_id?: string;
};

export type RuntimeToolReadiness = {
  node_id: string;
  reference: string;
  ready: boolean;
  code: string;
  detail: string;
};

export type RuntimeReadiness = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  agent_id: string;
  ready: boolean;
  profile_source: "agent" | "project" | "default";
  model: {
    required: boolean;
    configured: boolean;
    model_id: string;
    model_base_url: string;
    model_api_key_env: string;
    modalities?: RuntimeModelCapabilities;
  };
  dependency_summary: AgentDependencySummary;
  dependencies: AgentDependencyCheck[];
  tool_checks: RuntimeToolReadiness[];
  checks: RuntimeReadinessCheck[];
  setup_issues?: RuntimeSetupIssue[];
  version_id?: string;
};

export type WorkflowRuntimeReadinessCheck = {
  id: "agent_calls" | "permissions" | "limits" | "tools";
  ready: boolean;
  code: string;
  detail: string;
};

export type WorkflowRuntimePermissionGap = {
  field: string;
  missing: JsonValue[];
};

export type WorkflowRuntimeCallReadiness = {
  node_id: string;
  agent_id: string;
  version_id: string;
  source_hash: string;
  ready: boolean;
  detail: string;
  permission_gaps: WorkflowRuntimePermissionGap[];
  model: RuntimeReadiness["model"];
  dependency_summary: AgentDependencySummary;
  checks: RuntimeReadinessCheck[];
  tool_checks: RuntimeToolReadiness[];
  setup_issues?: RuntimeSetupIssue[];
};

export type WorkflowRuntimeReadiness = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  workflow_id: string;
  source_kind?: "draft" | "committed";
  version_id?: string | null;
  source_hash?: string;
  ready: boolean;
  calls: WorkflowRuntimeCallReadiness[];
  checks: WorkflowRuntimeReadinessCheck[];
  setup_issues?: RuntimeSetupIssue[];
};

export type SecretStatus = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  secret_ref: string;
  env_name: string;
  configured: boolean;
  source: "keychain" | "environment" | "missing";
};

export type ApplyFactoryDraftResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  session: FactorySession;
  agent: CreatedAgentResponse;
};

export type RuntimeRunStatus = "running" | "waiting" | "verified" | "unverified" | "failed" | "interrupted" | "cancelled";

export type RuntimeEventKind =
  | "run.created"
  | "run.state_changed"
  | "run.started"
  | "run.completed"
  | "run.interrupted"
  | "run.failed"
  | "run.cancelled"
  | "node.queued"
  | "node.state_changed"
  | "node.started"
  | "node.output"
  | "node.waiting"
  | "node.completed"
  | "node.failed"
  | "node.skipped"
  | "node.cancelled"
  | "tool.requested"
  | "tool.started"
  | "tool.completed"
  | "tool.failed"
  | "tool.input_rejected"
  | "model.output_rejected"
  | "agent.plan_updated"
  | "agent.budget_updated"
  | "agent.budget_insufficient"
  | "finalization.started"
  | "finalization.progress"
  | "finalization.completed"
  | "finalization.rejected"
  | "finalization.accepted"
  | "finalization.failed"
  | "image.response_received"
  | "model.delta"
  | "model.progress"
  | "approval.requested"
  | "approval.resolved"
  | "input.requested"
  | "input.resolved"
  | "artifact.created"
  | "checkpoint.created"
  | "verification.completed"
  | "evaluation.completed"
  | "evaluation.reviewed"
  | "verifier.result"
  | "skill.loaded"
  | "knowledge.retrieved"
  | "policy.partial"
  | "input.protected"
  | "input.output_created";

export type KnowledgeRetrievalHit = {
  reference: string;
  source_file_hash: string;
  chunk_id: string;
  chunk_index: number;
  line_start: number;
  line_end: number;
  rank: number;
  score: number;
};

export type KnowledgeRetrievalEvidence = {
  query_hash: string;
  hit_count: number;
  receipts: KnowledgeRetrievalHit[];
};

export type KnowledgeChunkResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  reference: string;
  source_file_hash: string;
  chunk_id: string;
  line_start: number;
  line_end: number;
  text: string;
};

export type RuntimeEvent = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  event_id: string;
  run_id: string;
  sequence: number;
  kind: RuntimeEventKind;
  node_id: string | null;
  payload: JsonObject;
  timestamp: string;
};

export type AgentRunResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  run_id: string;
  project_id: string;
  agent_id: string;
  version_id: string;
  conversation_id?: string | null;
  run_target_kind?: "agent" | "workflow";
  status: RuntimeRunStatus;
  result: JsonObject | null;
  error: { code: string; message: string } | null;
  created_at: string;
  finished_at: string | null;
  stream_text?: string;
  events?: RuntimeEvent[];
};

export type AgentConversationMessage = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  message_id: string;
  conversation_id: string;
  sequence: number;
  role: "user" | "assistant";
  content: string;
  run_id: string | null;
  created_at: string;
};

export type AgentConversationSummary = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  conversation_id: string;
  project_id: string;
  agent_id: string;
  agent_version_id?: string | null;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
};

export type AgentConversation = Omit<AgentConversationSummary, "message_count"> & {
  messages: AgentConversationMessage[];
  initial_inputs?: JsonObject;
};

export type ListAgentConversationsResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  conversations: AgentConversationSummary[];
};

export type CreateAgentConversationRequest = {
  title?: string;
  agent_version_id?: string;
};

export type ListAgentRunsResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  runs: AgentRunResponse[];
};

export type CommunityAgentPackageExport = {
  source_text: string;
  file_hash: string;
  source_hash: string;
  behavior_hash: string;
  lock_hash: string;
  dependencies: string[];
  version: string;
  slug: string;
  name: string;
  description: string;
};

export type ExportResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  agent_id: string;
  source: AgentSource;
  source_text: string;
  file_hash: string;
  community_package: CommunityAgentPackageExport;
  community_origin?: CommunityAgentOrigin;
};

export type LocalErrorEnvelope = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  code: string;
  message: string;
  request_id: string;
  details?: Record<string, string>;
};

export type ResourceDraftResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  draft_id: string;
  executable: false;
  resource: ResourceDescriptor;
};

export type PluginPackState = "quarantined" | "active" | "disabled" | "activation_failed";

export type PluginPackSkill = {
  path: string;
  reference: string;
  name: string;
  description: string;
  instruction: string;
};

export type PluginPackMcpServer = {
  name: string;
  command: string;
  args: string[];
  env_names: Record<string, string>;
  transport: "stdio" | "streamable_http";
  url: string | null;
  headers: Record<string, string>;
  enabled: boolean;
};

export type PluginPack = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  plugin_id: string;
  name: string;
  description: string;
  version: string;
  license: string | null;
  content_hash: string;
  state: PluginPackState;
  skills: PluginPackSkill[];
  mcp_servers: PluginPackMcpServer[];
  skill_resources: string[];
  mcp_server_ids: string[];
  activation_error: string | null;
};

export type ListPluginPacksResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  plugins: PluginPack[];
};

export type PluginPackResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  plugin: PluginPack;
};

export type PluginPackTrash = PluginPack & {
  trash_id: string;
};

export type ListPluginTrashResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  plugins: PluginPackTrash[];
};

export type PluginPackUninstallResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  plugin: PluginPackTrash & {
    disposition: "trashed";
  };
};

export type McpServer = {
  server_id: string;
  name: string;
  command: string;
  args: string[];
  env_names: Record<string, string>;
  transport: "stdio" | "streamable_http";
  url: string | null;
  headers: Record<string, string>;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type McpServerReadiness = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  server_id: string;
  ready: boolean;
  code: string;
  detail: string;
};

export type ListMcpServersResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  servers: McpServer[];
};

export type CreateMcpServerRequest = {
  name: string;
  command?: string;
  args?: string[];
  env_names?: Record<string, string>;
  transport?: "stdio" | "streamable_http";
  url?: string | null;
  headers?: Record<string, string>;
  enabled?: boolean;
};

export type ImportMcpServersRequest = {
  servers: CreateMcpServerRequest[];
};

export type ImportMcpServersResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  servers: McpServer[];
};

export type UpdateMcpServerRequest = {
  name?: string;
  command?: string;
  args?: string[];
  env_names?: Record<string, string>;
  transport?: "stdio" | "streamable_http";
  url?: string | null;
  headers?: Record<string, string>;
  enabled?: boolean;
};

export type WorkItemStatus =
  | "backlog"
  | "ready"
  | "running"
  | "waiting"
  | "cancelling"
  | "done"
  | "failed"
  | "cancelled";

export type WorkItem = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  work_item_id: string;
  project_id: string;
  title: string;
  description: string;
  agent_id: string;
  agent_version_id?: string | null;
  agent_source_hash?: string | null;
  binding_required?: boolean;
  depends_on: string[];
  inputs: JsonObject;
  status: WorkItemStatus;
  run_id: string | null;
  attempt_number?: number;
  lease_expires_at?: string | null;
  failure_class?: string | null;
  stale?: boolean;
  stale_for_seconds?: number;
  attempts?: WorkItemAttempt[];
  created_at: string;
  updated_at: string;
};

export type WorkItemAttempt = {
  attempt_id: string;
  attempt_number: number;
  operation?: "start" | "retry" | null;
  previous_run_id?: string | null;
  error_code?: string | null;
  run_id: string | null;
  status: string;
  failure_class: string | null;
  claimed_at: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
};

export type WorkItemCommandRequest = { expected_attempt_number: number };

export type ListWorkItemsResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  execution_plane: "local";
  work_items: WorkItem[];
};

export type OrchestratorStatus = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  execution_plane: "local";
  cloud_execution: false;
  counts: Record<WorkItemStatus, number>;
  active: WorkItem[];
  stale_count: number;
  limits: {
    global_concurrency: number;
    per_project_concurrency: number;
  };
};

export type WorkflowRunResponse = Omit<AgentRunResponse, "agent_id"> & {
  workflow_id: string;
  waiting: { kind: string; node_id: string; prompt: string; expected_fields?: string[]; agent_id?: string; child_run_id?: string; request_id?: string | null; input_schema?: TypedFields; context?: JsonValue; tool_reference?: string; approval_summary?: JsonObject } | null;
  children: { node_id: string; agent_id: string; version_id: string; child_run_id: string | null; status: RuntimeRunStatus | null }[];
};
