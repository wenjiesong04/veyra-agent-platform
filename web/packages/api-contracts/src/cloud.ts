/** Shared Veyra Cloud Host contracts used by Web and Desktop clients. */

export const CLOUD_API_SCHEMA_VERSION = "1.0" as const;

export type ProjectOrigin = "local" | "cloud";
export type CloudProjectState = "active" | "archived";

export type CloudProject = {
  project_id: string;
  owner_user_id: string;
  origin: "cloud";
  name: string;
  description: string;
  schema_version: "cloud.project.v1";
  revision: number;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  state: CloudProjectState;
};

export type CloudProjectListResponse = {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  projects: CloudProject[];
};

export type CloudProjectResponse = {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  project: CloudProject;
};

export type CloudProjectCreateRequest = { project_id: string; name: string; description?: string };
export type CloudProjectUpdateRequest = { expected_revision: number; name?: string; description?: string };

export type CloudProjectArchiveResponse = {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  project_id: string;
  origin: "cloud";
  archived: true;
};

export type CloudArtifactKind =
  | "agent"
  | "agent_version"
  | "workflow"
  | "custom_component"
  | "knowledge_metadata";

export type CloudArtifactSyncState =
  | "synced"
  | "pending_push"
  | "pending_pull"
  | "conflict"
  | "error"
  | "local_only";

export type CloudArtifactManifestItem = {
  artifact_kind: CloudArtifactKind;
  artifact_id: string;
  content_hash: string;
  revision: number;
  deleted: boolean;
  immutable: boolean;
};

export type CloudArtifactManifestResponse = {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  project_id: string;
  artifacts: CloudArtifactManifestItem[];
};

export type CloudArtifactEnvelope = {
  project_id: string;
  artifact_kind: CloudArtifactKind;
  artifact_id: string;
  schema_version: string;
  content_hash: string;
  revision: number;
  deleted: boolean;
  immutable: boolean;
  payload: Record<string, unknown>;
};

export type CloudArtifactResponse = {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  artifact: CloudArtifactEnvelope;
};

export type CloudArtifactPutRequest = {
  expected_revision?: number | null;
  schema_version: string;
  content_hash: string;
  deleted?: boolean;
  immutable?: boolean;
  payload: Record<string, unknown>;
};

export type CloudFileState = "active" | "failed" | "deleting";

export type CloudFileSummary = {
  schema_version: "cloud.file.v1";
  file_id: string;
  display_name: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  state: CloudFileState;
  created_at: string;
  updated_at: string;
};

export type CloudFileListResponse = {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  files: CloudFileSummary[];
  next_cursor: string | null;
};

export type CloudFileResponse = {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  file: CloudFileSummary;
};

export type CloudFileUploadResponse = CloudFileResponse;

export type CloudProjectFileReference = {
  project_id: string;
  file_id: string;
  role: string;
  purpose: string;
  created_at: string;
  updated_at: string;
  file: CloudFileSummary;
};

export type CloudProjectFileListResponse = {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  project_id: string;
  files: CloudProjectFileReference[];
};

export type CloudProjectFileAttachRequest = {
  file_id: string;
  role?: string;
  purpose?: string;
};

export type CloudProjectFileReferenceResponse = {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  reference: CloudProjectFileReference;
};

export type ConversationAttachment = {
  cloud_file_id: string;
  display_name: string;
  content_type: string;
  size_bytes: number;
};

export type ConversationSummary = {
  conversation_id: string;
  project_id: string | null;
  agent_id: string | null;
  title: string;
  status: "active" | "archived";
  revision: number;
  created_at: string;
  updated_at: string;
  last_activity_at: string;
  last_operation_status: string | null;
  last_operation_kind: string | null;
};

export type ConversationMessage = {
  message_id: string;
  conversation_id: string;
  sequence: number;
  role: "user" | "assistant" | "system";
  kind: string;
  content: string;
  operation_id: string | null;
  payload: Record<string, unknown>;
  attachments: ConversationAttachment[];
  created_at: string;
};

export type ConversationOperationEvent = {
  event_id: string;
  operation_id: string;
  sequence: number;
  kind: string;
  label: string;
  summary: string;
  facts: Record<string, unknown>;
  created_at: string;
};

export type ConversationOperation = {
  operation_id: string;
  conversation_id: string;
  kind: string;
  status: string;
  retry_of: string | null;
  proposal_id: string | null;
  run_id: string | null;
  factory_session_id: string | null;
  diagnostic: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  events: ConversationOperationEvent[];
};

export type ConversationResponse = {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  conversation: ConversationSummary;
  messages: ConversationMessage[];
  operations: ConversationOperation[];
};

export type ConversationListResponse = {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  conversations: ConversationSummary[];
  next_cursor: string | null;
};

export type ConversationCreateRequest = {
  conversation_id?: string;
  project_id?: string | null;
  agent_id?: string | null;
  title?: string;
};

export type ConversationMessageRequest = {
  message_id?: string;
  role: "user" | "assistant" | "system";
  kind: string;
  content: string;
  operation_id?: string | null;
  payload?: Record<string, unknown>;
  attachments?: Array<{ cloud_file_id: string }>;
};

export type ConversationImportRequest = {
  conversation: ConversationSummary;
  messages: ConversationMessage[];
  operations: ConversationOperation[];
};

export type ConversationRenameRequest = {
  title: string;
  expected_revision: number;
};

export type CloudCredentialStatus = "unverified" | "active" | "invalid" | "disabled";

export type CloudCredential = {
  credential_id: string;
  owner_id: string;
  provider_type: string;
  label: string;
  base_url: string;
  status: CloudCredentialStatus;
  masked_hint: string;
  capabilities: Record<string, unknown>;
  default_model_id: string | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
  validated_at: string | null;
  last_used_at: string | null;
};

export type CloudCredentialListResponse = {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  credentials: CloudCredential[];
};

export type CloudCredentialResponse = {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  credential: CloudCredential;
};

export type CloudCredentialCreateRequest = {
  provider_type: string;
  label: string;
  api_key: string;
  base_url?: string;
  default_model_id?: string;
  make_default?: boolean;
  validate?: boolean;
};

export type CloudCredentialPatchRequest = {
  label?: string;
  base_url?: string;
  default_model_id?: string;
  make_default?: boolean;
};

export type CloudCredentialValidationResponse = {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  validation: {
    valid: boolean;
    code: string;
    message: string;
    credential: CloudCredential;
  };
};

export type CloudRuntimeBinding = {
  project_id: string;
  agent_id: string | null;
  slot: string;
  credential_id: string;
  model_id: string;
  source: "agent" | "project" | "user_default" | "explicit";
  updated_at: string;
};

export type CloudRuntimeBindingListResponse = {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  project_id: string;
  bindings: CloudRuntimeBinding[];
};

export type CloudRuntimeBindingRequest = {
  agent_id?: string | null;
  slot?: string;
  credential_id: string;
  model_id: string;
};

export type CloudRunStatus = "running" | "waiting" | "verified" | "unverified" | "failed" | "interrupted" | "cancelled";

export type CloudRunEvent = {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  event_id: string;
  run_id: string;
  sequence: number;
  kind: string;
  node_id: string | null;
  payload: Record<string, unknown>;
  timestamp: string;
};

export type CloudRun = {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  run_id: string;
  project_id: string;
  agent_id: string;
  version_id: string;
  execution_target: "cloud";
  binding_slot: string;
  conversation_id: string | null;
  retry_of_run_id: string | null;
  attempt_number: number;
  status: CloudRunStatus;
  result: Record<string, unknown> | null;
  error: { code: string; message: string } | null;
  created_at: string;
  finished_at: string | null;
  provider: string | null;
  model: string | null;
  credential_type: "user" | null;
  credential_alias: string | null;
  waiting: { kind: "approval"; node_id: string; prompt: string } | null;
  events?: CloudRunEvent[];
};

export type CloudRunResponse = CloudRun;

export type CloudRunListResponse = {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  runs: CloudRun[];
};

export type CloudRunCreateRequest = {
  project_id: string;
  agent_id: string;
  agent_version_id: string;
  inputs: Record<string, unknown>;
  execution_target?: "cloud";
  binding_slot?: string;
  conversation_id?: string | null;
};

export type CloudRunCommandRequest = {
  command: "approve" | "reject" | "stop" | "retry" | "resume";
  checkpoint_id?: string;
};
