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
    | "Tool"
    | "Condition"
    | "Transform"
    | "HumanApproval"
    | "Verifier"
    | "Output";
  model_ref?: string;
  system_prompt?: string;
  uses?: string;
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
    };
  };
  ui: {
    positions: Record<string, { x: number; y: number }>;
  };
  lock: Record<string, string>;
};

export type ProjectAgentRecord = {
  agent_id: string;
  slug: string;
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
  agents: ProjectAgentRecord[];
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
  name: string;
  description: string;
};

/** Mutable local Project presentation state. The manifest remains authoritative. */
export type UpdateProjectRequest = {
  pinned: boolean;
};

export type CreateAgentRequest = TemplateSelection;

export type OpenProjectRequest = {
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

export type DraftResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  draft_id: string;
  revision: number;
  etag: string;
  source_file_hash: string;
  source: AgentSource;
};

export type SaveDraftResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  revision: number;
  etag: string;
  source: AgentSource;
};

export type SaveDraftRequest = {
  source: AgentSource;
  expected_revision: number;
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
  agent_id: string;
  source_hash: string;
  behavior_hash: string;
  lock_hash: string;
  file_hash: string;
};

export type ExportResponse = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  agent_id: string;
  source: AgentSource;
  source_text: string;
  file_hash: string;
};

export type LocalErrorEnvelope = {
  schema_version: typeof LOCAL_API_SCHEMA_VERSION;
  code: string;
  message: string;
  request_id: string;
  details?: Record<string, string>;
};
