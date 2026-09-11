/**
 * Wire contracts for the local desktop sidecar.
 *
 * The local API deliberately returns the resource object directly (rather
 * than wrapping it in a `data` envelope).  These types mirror the FastAPI
 * routes in `backend/src/veyra_agent_platform/local/api/projects/routes.py`.
 */

export const LOCAL_API_SCHEMA_VERSION = "1.0" as const;

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export type JsonObject = { [key: string]: JsonValue };

export type PermissionContract = {
  network_hosts: string[];
  tools: string[];
  filesystem_read_roots?: string[];
  filesystem_write_roots?: string[];
  shell_workspace_only?: boolean;
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
    | "Condition"
    | "Transform"
    | "HumanApproval"
    | "Verifier"
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
  checks?: string[];
  output_name?: string;
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
};

export type AgentSource = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  agentspec_version: "26.1";
  component_type: "Flow";
  agent_id: string;
  slug: string;
  name: string;
  description: string;
  inputs: Record<string, string>;
  outputs: Record<string, string>;
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
    };
  };
  ui: {
    positions: Record<string, { x: number; y: number }>;
    bindings?: Record<string, CatalogBinding>;
    notes?: Record<string, StudioNote>;
  };
  lock: Record<string, string>;
};

export type WorkflowSource = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  component_type: "Workflow";
  workflow_id: string;
  slug: string;
  name: string;
  description: string;
  version?: string;
  inputs: Record<string, string>;
  outputs: Record<string, string>;
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
  };
  lock: Record<string, string>;
};

export type StudioSource = AgentSource | WorkflowSource;

export type AgentVersionSnapshot = {
  version_id: string;
  agent_id: string;
  source_hash: string;
  behavior_hash: string;
  created_at: string;
  source: AgentSource;
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
};
export type ListWorkflowVersionsResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  versions: WorkflowVersionSnapshot[];
};

export type CatalogBinding = {
  kind: "skill" | "policy" | "template" | "mcp_tool" | "knowledge";
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

export type ProjectKnowledgeRecord = {
  knowledge_id: string;
  slug: string;
  name: string;
  description: string;
  version?: string;
  source_path: string;
  source_file_hash: string;
};

export type ProjectSummaryResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
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
  knowledge_id: string;
  slug: string;
  name: string;
  description: string;
  version?: string;
  source_path: string;
  source_file_hash: string;
  text: string;
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

export type ValidateResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  valid: true;
  source_hash: string;
  behavior_hash: string;
  lock_hash: string;
  file_hash: string;
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
};

export type RunCommandRequest = {
  command: "approve" | "reject" | "stop" | "resume" | "retry";
};

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

/** Server-owned, immutable capability descriptor exposed by the Resource Catalog. */
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

export type ResourceOrigin = "builtin" | "workshop" | "discovered";

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

export type ProjectResourceUsage = {
  kind: "agent" | "workflow";
  resource_id: string;
  name: string;
};

export type ProjectResourceDescriptor = ResourceDescriptor & {
  scope: ProjectResourceScope;
  binding_source: "manual" | "factory" | "imported" | "reconciled" | null;
  bound_content_hash: string | null;
  used_by: ProjectResourceUsage[];
};

export type ProjectResourcesResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  project_id: string;
  resources: ProjectResourceDescriptor[];
  missing_references: string[];
  project_count: number;
  used_count: number;
  unbound_count: number;
  builtin_count: number;
};

export type AddProjectResourceRequest = {
  reference: string;
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

export type FactoryResourcePlanItem = {
  reference: string;
  kind: ResourceKind;
  availability: ResourceAvailability;
  runtime_status: ResourceRuntimeStatus;
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
  run_availability: FactoryRunAvailability;
  executes_drafts: false;
  revision: number;
  created_at: string;
  updated_at: string;
  messages: FactoryMessage[];
};

export type FactoryStatus = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  configured: boolean;
  model_id: string;
  model_base_url: string;
  model_api_key_env: string;
  reasoning_effort: "low" | "high" | "max";
  repair_attempts: number;
  executes_drafts: false;
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
  | "model.delta"
  | "approval.requested"
  | "approval.resolved"
  | "input.requested"
  | "input.resolved"
  | "artifact.created"
  | "checkpoint.created"
  | "verification.completed"
  | "verifier.result";

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
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
};

export type AgentConversation = Omit<AgentConversationSummary, "message_count"> & {
  messages: AgentConversationMessage[];
};

export type ListAgentConversationsResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  conversations: AgentConversationSummary[];
};

export type CreateAgentConversationRequest = {
  title?: string;
};

export type ListAgentRunsResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  runs: AgentRunResponse[];
};

export type ExportResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  agent_id: string;
  source: AgentSource;
  source_text: string;
  file_hash: string;
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

export type McpServer = {
  server_id: string;
  name: string;
  command: string;
  args: string[];
  env_names: Record<string, string>;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type ListMcpServersResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  servers: McpServer[];
};

export type CreateMcpServerRequest = {
  name: string;
  command: string;
  args?: string[];
  env_names?: Record<string, string>;
  enabled?: boolean;
};

export type UpdateMcpServerRequest = {
  name?: string;
  command?: string;
  args?: string[];
  env_names?: Record<string, string>;
  enabled?: boolean;
};

export type WorkItemStatus =
  | "backlog"
  | "ready"
  | "running"
  | "waiting"
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
  run_id: string | null;
  status: string;
  failure_class: string | null;
  claimed_at: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
};

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
  waiting: { kind: string; node_id: string; prompt: string; agent_id?: string; child_run_id?: string } | null;
  children: { node_id: string; agent_id: string; version_id: string; child_run_id: string | null; status: RuntimeRunStatus | null }[];
};
