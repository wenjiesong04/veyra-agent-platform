import type { WorkflowRunResponse, ListAgentVersionsResponse, ListWorkflowVersionsResponse } from "@veyra/api-contracts";
import {
  LOCAL_API_SCHEMA_VERSION,
  isTypedFieldSpec,
  type AgentSource,
  type CreateEditProposalRequest,
  type CreateKnowledgeBindingRequest,
  type CreateResourceBindingRequest,
  type CreateValidationRepairRequest,
  type KnowledgeBindingPlan,
  type ResourceBindingPlan,
  type ValidationRepairPlan,
  type BuilderResolveRequest,
  type BuilderResolution,
  type BuilderTurnRequest,
  type BuilderConversationSnapshot,
  type BuilderConversationRecordRequest,
  type BuilderConversationRenameRequest,
  type BuilderConversationDeleted,
  type ListWorkspaceTrashResponse,
  type WorkspaceTrashKind,
  type WorkspaceTrashMutationResponse,
  type WorkspaceTrashItem,
  type BuilderActivityResponse,
  type BuilderConversationMessage,
  type BuilderConversationOperation,
  type BuilderHarnessReceipt,
  type BuilderRunObservation,
  type BuilderTestRepairRequest,
  type BuilderTestRunCommandRequest,
  type BuilderTestRunRequest,
  type BuilderConversationSummary,
  type BuilderMessageKind,
  type BuilderOperationEvent,
  type BuilderOperationEventKind,
  type BuilderOperationStatus,
  type BuilderTargetKind,
  type BuilderActivityItem,
  type EditProposal,
  type EditProposalChange,
  type EditProposalCommand,
  type EditTargetKind,
  type ListEditProposalsResponse,
  type AgentImportApplyRequest,
  type AgentImportApplyResponse,
  type AgentImportRecord,
  type AgentRunResponse,
  type AgentConversation,
  type AgentConversationSummary,
  type CreateAgentConversationRequest,
  type AgentTemplate,
  type ComponentDefinition,
  type CommunityAgentOrigin,
  type CommitResponse,
  type CreateAgentRequest,
  type CreatedAgentResponse,
  type CreateKnowledgeRequest,
  type CreateProjectRequest,
  type CreateWorkflowRequest,
  type CreatedWorkflowResponse,
  type DeleteProjectResponse,
  type DeleteAgentResponse,
  type DeleteKnowledgeResponse,
  type DeleteWorkflowResponse,
  type DraftResponse,
  type ExportResponse,
  type FactoryMissingCapability,
  type FactoryResourcePlanItem,
  type FactoryRunAvailability,
  type FactorySession,
  type FactorySessionState,
  type FactoryStatus,
  type ProviderCapabilityProfile,
  type ArtifactRecord,
  type RuntimeModelCapabilities,
  type RuntimeStatus,
  type SecretStatus,
  type RuntimeApiProfileInput,
  type RuntimeApiProfileSummary,
  type RuntimeProfileResponse,
  type RuntimeProfileValidation,
  type RuntimeReadiness,
  type RuntimeReadinessCheck,
  type RuntimeToolReadiness,
  type WorkflowRuntimeReadiness,
  type WorkflowRuntimeReadinessCheck,
  type ApplyFactoryDraftResponse,
  type FactoryMessage,
  type JsonObject,
  type JsonValue,
  type TypedFields,
  type KnowledgeDocumentResponse,
  type KnowledgeChunkResponse,
  type KnowledgeProcessing,
  type ListAgentRunsResponse,
  type ListAgentConversationsResponse,
  type ListAgentsResponse,
  type ListAgentTemplatesResponse,
  type ListComponentsResponse,
  type ListMcpServersResponse,
  type ListPluginPacksResponse,
  type ListPluginTrashResponse,
  type ListResourceFilters,
  type ListResourcesResponse,
  type ListProjectsResponse,
  type ListWorkItemsResponse,
  type CreateMcpServerRequest,
  type ImportMcpServersRequest,
  type ImportMcpServersResponse,
  type UpdateMcpServerRequest,
  type McpServer,
  type McpServerReadiness,
  type AgentDependencyCheck,
  type AgentDependencyStatus,
  type AgentDependencySummary,
  type ImportProjectPathRequest,
  type AddProjectResourceRequest,
  type OpenProjectRequest,
  type ProjectAgentRecord,
  type ProjectFileContentResponse,
  type ProjectFileKind,
  type ProjectFileRecord,
  type ProjectFilesResponse,
  type ProjectKnowledgeRecord,
  type ProjectSummaryResponse,
  type ProjectResourceDescriptor,
  type ProjectResourceBindingStatus,
  type ProjectResourcesResponse,
  type ProjectWorkflowRecord,
  type RevealProjectResponse,
  type SaveDraftRequest,
  type SaveDraftResponse,
  type SaveWorkflowDraftRequest,
  type SaveWorkflowDraftResponse,
  type SelectArchiveResponse,
  type SelectDirectoryResponse,
  type StartAgentRunRequest,
  type RunCommandRequest,
  type ResourceDescriptor,
  type ResourceAvailability,
  type ResourceDraftResponse,
  type PluginPack,
  type PluginPackResponse,
  type PluginPackTrash,
  type PluginPackUninstallResponse,
  type PluginPackState,
  type ResourceKind,
  type ResourceOrigin,
  type ResourceRuntimeStatus,
  type RuntimeEvent,
  type UpdateProjectRequest,
  type UpdateAgentRequest,
  type UpdateKnowledgeRequest,
  type ValidateResponse,
  type WorkflowDraftResponse,
  type WorkflowSource,
  type OrchestratorStatus,
  type WorkItem,
  type WorkItemAttempt,
} from "@veyra/api-contracts";
import { newUuidV7 } from "./uuid";

export const DEFAULT_LOCAL_API_BASE_URL = "/api/v1";

type ViteImportMeta = ImportMeta & {
  env?: Record<string, string | undefined>;
};

export class LocalApiClientError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;
  readonly details?: Record<string, string>;

  constructor(
    message: string,
    options: {
      status: number;
      code: string;
      requestId?: string;
      details?: Record<string, string>;
    },
  ) {
    super(message);
    this.name = "LocalApiClientError";
    this.status = options.status;
    this.code = options.code;
    this.requestId = options.requestId;
    this.details = options.details;
  }
}

export type LocalApiClientOptions = {
  baseUrl?: string;
  fetcher?: typeof fetch;
};

/** The Project slice only needs these sidecar operations. Keep the UI injectable. */
export type LocalProjectApi = {
  listProjects(): Promise<ListProjectsResponse>;
  createProject(input: CreateProjectRequest): Promise<ProjectSummaryResponse>;
  openProject(input: OpenProjectRequest): Promise<ProjectSummaryResponse>;
  getProject(projectId: string): Promise<ProjectSummaryResponse>;
  updateProject(projectId: string, input: UpdateProjectRequest): Promise<ProjectSummaryResponse>;
  deleteProject(projectId: string): Promise<DeleteProjectResponse>;
  updateAgent(projectId: string, agentId: string, input: UpdateAgentRequest): Promise<ProjectSummaryResponse>;
  deleteAgent(projectId: string, agentId: string): Promise<DeleteAgentResponse>;
  listAgentTemplates(projectId: string): Promise<ListAgentTemplatesResponse>;
  createAgent(projectId: string, input: CreateAgentRequest): Promise<CreatedAgentResponse>;
  createWorkflow?(projectId: string, input?: CreateWorkflowRequest): Promise<CreatedWorkflowResponse>;
  deleteWorkflow?(projectId: string, workflowId: string): Promise<DeleteWorkflowResponse>;
  createKnowledge?(projectId: string, input?: CreateKnowledgeRequest): Promise<KnowledgeDocumentResponse>;
  ingestKnowledge?(projectId: string, file: File): Promise<KnowledgeDocumentResponse>;
  buildKnowledgeIndex?(projectId: string, knowledgeId: string): Promise<KnowledgeDocumentResponse>;
  getKnowledge?(projectId: string, knowledgeId: string): Promise<KnowledgeDocumentResponse>;
  getKnowledgeChunk?(projectId: string, knowledgeId: string, chunkId: string, sourceFileHash: string): Promise<KnowledgeChunkResponse>;
  updateKnowledge?(projectId: string, knowledgeId: string, input: UpdateKnowledgeRequest): Promise<KnowledgeDocumentResponse>;
  deleteKnowledge?(projectId: string, knowledgeId: string): Promise<DeleteKnowledgeResponse>;
  importAgent(projectId: string, input: { file: File; name?: string; description?: string; parent_agent_id?: string; community_origin?: CommunityAgentOrigin }): Promise<CreatedAgentResponse>;
  analyzeAgentImport?(file: File): Promise<AgentImportRecord>;
  analyzeAgentImportFolder?(path: string): Promise<AgentImportRecord>;
  getAgentImport?(importId: string): Promise<AgentImportRecord>;
  applyAgentImport?(importId: string, input: AgentImportApplyRequest): Promise<AgentImportApplyResponse>;
  importProject?(file: File): Promise<ProjectSummaryResponse>;
  importProjectFromPath?(input: ImportProjectPathRequest): Promise<ProjectSummaryResponse>;
  listProjectResources?(projectId: string): Promise<ProjectResourcesResponse>;
  addProjectResource?(projectId: string, input: AddProjectResourceRequest): Promise<ProjectResourcesResponse>;
  removeProjectResource?(projectId: string, resourceId: string, version: string): Promise<ProjectResourcesResponse>;
  revealProject?(projectId: string): Promise<RevealProjectResponse>;
  exportProject?(projectId: string): Promise<Blob>;
  exportAgent?(projectId: string, agentId: string): Promise<ExportResponse>;
  listProjectFiles?(projectId: string): Promise<ProjectFilesResponse>;
  getProjectFile?(projectId: string, path: string): Promise<ProjectFileContentResponse>;
  listAgentVersions?(projectId: string, agentId: string): Promise<ListAgentVersionsResponse>;
  listWorkflowVersions?(projectId: string, workflowId: string): Promise<ListWorkflowVersionsResponse>;
  getDraft(projectId: string, agentId: string): Promise<DraftResponse>;
  /** Studio mutations are optional so narrow consumers can still supply read-only APIs. */
  saveDraft?(projectId: string, agentId: string, input: SaveDraftRequest, options: { etag: string; idempotencyKey?: string }): Promise<SaveDraftResponse>;
  reloadDraft?(projectId: string, agentId: string): Promise<DraftResponse>;
  getWorkflowDraft?(projectId: string, workflowId: string): Promise<WorkflowDraftResponse>;
  saveWorkflowDraft?(projectId: string, workflowId: string, input: SaveWorkflowDraftRequest, options: { etag: string; idempotencyKey?: string }): Promise<SaveWorkflowDraftResponse>;
  reloadWorkflowDraft?(projectId: string, workflowId: string): Promise<WorkflowDraftResponse>;
  validateWorkflow?(projectId: string, workflowId: string): Promise<ValidateResponse>;
  workflowRuntimeReadiness?(projectId: string, workflowId: string): Promise<WorkflowRuntimeReadiness>;
  commitWorkflow?(projectId: string, workflowId: string, options: { expectedRevision: number; etag: string; idempotencyKey?: string }): Promise<CommitResponse>;
  validate?(projectId: string, agentId: string): Promise<ValidateResponse>;
  commit?(projectId: string, agentId: string, options: { expectedRevision: number; etag: string; idempotencyKey?: string }): Promise<CommitResponse>;
  listComponents?(): Promise<ListComponentsResponse>;
  listResources?(filters?: ListResourceFilters): Promise<ListResourcesResponse>;
  getResource?(resourceId: string, version: string): Promise<ResourceDescriptor>;
  factoryStatus?(): Promise<FactoryStatus>;
  probeFactoryCapabilities?(): Promise<FactoryStatus>;
  runtimeStatus?(): Promise<RuntimeStatus>;
  validateRuntimeProfile?(profile: RuntimeApiProfileInput): Promise<RuntimeProfileValidation>;
  runtimeReadiness?(projectId: string, agentId: string): Promise<RuntimeReadiness>;
  uploadArtifact?(projectId: string, file: File): Promise<ArtifactRecord>;
  getArtifact?(projectId: string, artifactId: string): Promise<ArtifactRecord>;
  artifactContent?(projectId: string, artifactId: string): Promise<Blob>;
  getSecretStatus?(secretRef: string): Promise<SecretStatus>;
  setSecret?(secretRef: string, value: string): Promise<SecretStatus>;
  deleteSecret?(secretRef: string): Promise<SecretStatus>;
  getProjectRuntimeProfile?(projectId: string): Promise<RuntimeProfileResponse>;
  setProjectRuntimeProfile?(projectId: string, profile: RuntimeApiProfileInput | null): Promise<RuntimeProfileResponse>;
  getAgentRuntimeProfile?(projectId: string, agentId: string): Promise<RuntimeProfileResponse>;
  setAgentRuntimeProfile?(projectId: string, agentId: string, profile: RuntimeApiProfileInput | null): Promise<RuntimeProfileResponse>;
  resolveBuilderIntent?(projectId: string, input: BuilderResolveRequest): Promise<BuilderResolution>;
  submitBuilderTurn?(projectId: string, input: BuilderTurnRequest, options?: { onEvent?: (event: BuilderOperationEvent) => void }): Promise<BuilderConversationSnapshot>;
  getBuilderConversation?(projectId: string, conversationId: string): Promise<BuilderConversationSnapshot>;
  recordBuilderConversation?(projectId: string, conversationId: string, input: BuilderConversationRecordRequest): Promise<BuilderConversationSnapshot>;
  renameBuilderConversation?(projectId: string, conversationId: string, input: BuilderConversationRenameRequest): Promise<BuilderConversationSnapshot>;
  deleteBuilderConversation?(projectId: string, conversationId: string): Promise<BuilderConversationDeleted>;
  listBuilderActivity?(projectId?: string, limit?: number): Promise<BuilderActivityResponse>;
  listWorkspaceTrash?(): Promise<ListWorkspaceTrashResponse>;
  restoreWorkspaceTrash?(kind: WorkspaceTrashKind, itemId: string, confirm?: boolean): Promise<WorkspaceTrashMutationResponse>;
  purgeWorkspaceTrash?(kind: WorkspaceTrashKind, itemId: string, confirm?: boolean): Promise<WorkspaceTrashMutationResponse>;
  startBuilderTestRun?(projectId: string, conversationId: string, input: BuilderTestRunRequest): Promise<BuilderConversationSnapshot>;
  commandBuilderTestRun?(projectId: string, conversationId: string, operationId: string, input: BuilderTestRunCommandRequest): Promise<BuilderConversationSnapshot>;
  proposeBuilderTestRepair?(projectId: string, conversationId: string, operationId: string, input?: BuilderTestRepairRequest): Promise<BuilderConversationSnapshot>;
  createEditProposal?(projectId: string, input: CreateEditProposalRequest): Promise<EditProposal>;
  createKnowledgeBindingProposal?(projectId: string, input: CreateKnowledgeBindingRequest): Promise<EditProposal>;
  createResourceBindingProposal?(projectId: string, input: CreateResourceBindingRequest): Promise<EditProposal>;
  createValidationRepairProposal?(projectId: string, input: CreateValidationRepairRequest): Promise<EditProposal>;
  listEditProposals?(projectId: string, kind: EditTargetKind, targetId: string): Promise<ListEditProposalsResponse>;
  commandEditProposal?(projectId: string, proposalId: string, input: { command: EditProposalCommand; confirm: boolean }): Promise<EditProposal>;
  createFactorySession?(projectId: string, input?: { goal?: string }): Promise<FactorySession>;
  getFactorySession?(projectId: string, sessionId: string): Promise<FactorySession>;
  addFactoryMessage?(projectId: string, sessionId: string, content: string): Promise<FactorySession>;
  generateFactoryBlueprint?(projectId: string, sessionId: string): Promise<FactorySession>;
  applyFactoryDraft?(projectId: string, sessionId: string, input: { confirm: boolean; name?: string; description?: string; parent_agent_id?: string }): Promise<ApplyFactoryDraftResponse>;
  createResourceDraft?(input: { confirm: boolean; kind: string; requested_reference: string; name?: string; description?: string; instruction?: string }): Promise<ResourceDraftResponse>;
  approveResourceDraft?(resourceId: string, version: string, instruction: string): Promise<{ schema_version: "1.0"; resource: ResourceDescriptor }>;
  listMcpServers?(): Promise<ListMcpServersResponse>;
  listPluginPacks?(): Promise<ListPluginPacksResponse>;
  listPluginTrash?(): Promise<ListPluginTrashResponse>;
  importPluginPack?(file: File): Promise<PluginPackResponse>;
  activatePluginPack?(pluginId: string, version: string, confirm?: boolean): Promise<PluginPackResponse>;
  disablePluginPack?(pluginId: string, version: string, confirm?: boolean): Promise<PluginPackResponse>;
  uninstallPluginPack?(pluginId: string, version: string, confirm?: boolean): Promise<PluginPackUninstallResponse>;
  restorePluginPack?(trashId: string, confirm?: boolean): Promise<PluginPackResponse>;
  downloadPluginPack?(pluginId: string, version: string): Promise<Blob>;
  createMcpServer?(input: CreateMcpServerRequest): Promise<{ schema_version: "1.0"; server: McpServer }>;
  importMcpServers?(input: ImportMcpServersRequest): Promise<ImportMcpServersResponse>;
  updateMcpServer?(serverId: string, input: UpdateMcpServerRequest): Promise<{ schema_version: "1.0"; server: McpServer }>;
  discoverMcpServer?(serverId: string): Promise<{ schema_version: "1.0"; server_id: string; tools: ResourceDescriptor[] }>;
  mcpServerReadiness?(serverId: string): Promise<McpServerReadiness>;
  approveMcpTool?(serverId: string, resourceId: string, version: string): Promise<{ schema_version: "1.0"; server_id: string; resource: ResourceDescriptor }>;
  deleteMcpServer?(serverId: string): Promise<{ schema_version: "1.0"; server_id: string; deleted: boolean }>;
  orchestratorStatus?(): Promise<OrchestratorStatus>;
  listWorkItems?(projectId: string): Promise<ListWorkItemsResponse>;
  createWorkItem?(projectId: string, input: { title: string; agent_id: string; description?: string; depends_on?: string[]; inputs?: JsonObject }): Promise<WorkItem>;
  dispatchWorkItem?(workItemId: string): Promise<WorkItem>;
  retryWorkItem?(workItemId: string): Promise<WorkItem>;
  cancelWorkItem?(workItemId: string): Promise<WorkItem>;
  recoverWorkItem?(workItemId: string): Promise<WorkItem>;
  runWorkflow?(projectId: string, workflowId: string, input: StartAgentRunRequest): Promise<WorkflowRunResponse>;
  getWorkflowRun?(projectId: string, workflowId: string, runId: string): Promise<WorkflowRunResponse>;
  listWorkflowRuns?(projectId: string, workflowId: string): Promise<{ schema_version: "1.0"; runs: WorkflowRunResponse[] }>;
  commandWorkflowRun?(projectId: string, workflowId: string, runId: string, input: { command: "approve" | "reject" | "stop" }): Promise<WorkflowRunResponse>;
  runAgent?(projectId: string, agentId: string, input: StartAgentRunRequest, options?: { idempotencyKey?: string }): Promise<AgentRunResponse>;
  commandAgentRun?(projectId: string, agentId: string, runId: string, input: RunCommandRequest, options?: { idempotencyKey?: string }): Promise<AgentRunResponse>;
  listAgentRuns?(projectId: string, agentId: string): Promise<ListAgentRunsResponse>;
  getAgentRun?(projectId: string, agentId: string, runId: string): Promise<AgentRunResponse>;
  listAgentConversations?(projectId: string, agentId: string): Promise<ListAgentConversationsResponse>;
  createAgentConversation?(projectId: string, agentId: string, input?: CreateAgentConversationRequest): Promise<AgentConversation>;
  getAgentConversation?(projectId: string, agentId: string, conversationId: string): Promise<AgentConversation>;
  watchAgentRunEvents?(
    projectId: string,
    agentId: string,
    runId: string,
    handlers: {
      onEvent: (event: RuntimeEvent) => void;
      onDone?: (status: AgentRunResponse["status"]) => void;
      onError?: (error: Error) => void;
    },
    options?: { after?: number },
  ): () => void;
  selectDirectory(): Promise<SelectDirectoryResponse>;
  selectArchive?(): Promise<SelectArchiveResponse>;
};

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: object;
  formData?: FormData;
  ifMatch?: string;
  idempotencyKey?: string;
  requireIdempotencyKey?: boolean;
  headers?: Record<string, string>;
};

function configuredBaseUrl(): string {
  const viteEnv = (import.meta as ViteImportMeta).env;
  return viteEnv?.VITE_LOCAL_API_BASE_URL?.trim() || DEFAULT_LOCAL_API_BASE_URL;
}

function apiUrl(baseUrl: string, path: string): string {
  const base = baseUrl.trim().replace(/\/+$/, "");
  const suffix = path.replace(/^\/+/, "");
  if (/^[a-z][a-z\d+.-]*:\/\//i.test(base)) return `${base}/${suffix}`;
  return `${base.startsWith("/") ? base : `/${base}`}/${suffix}`;
}

function asRecord(value: unknown, status = 502): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new LocalApiClientError("The local service returned an invalid response.", {
      status,
      code: "invalid_response",
    });
  }
  return value as Record<string, unknown>;
}

function typedFields(value: unknown, field: string, status = 502): TypedFields {
  const record = asRecord(value, status);
  const parsed: TypedFields = {};
  for (const [key, item] of Object.entries(record)) {
    if (!isTypedFieldSpec(item)) {
      throw new LocalApiClientError(`The local service returned an invalid ${field}.${key}.`, {
        status,
        code: "invalid_response",
      });
    }
    parsed[key] = item;
  }
  return parsed;
}

function asString(value: unknown, field: string, status = 502): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new LocalApiClientError(`The local service returned an invalid ${field}.`, {
      status,
      code: "invalid_response",
    });
  }
  return value;
}

function asText(value: unknown, field: string, status = 502): string {
  if (typeof value !== "string") {
    throw new LocalApiClientError(`The local service returned an invalid ${field}.`, {
      status,
      code: "invalid_response",
    });
  }
  return value;
}

function asArray(value: unknown, field: string, status = 502): unknown[] {
  if (!Array.isArray(value)) {
    throw new LocalApiClientError(`The local service returned an invalid ${field}.`, {
      status,
      code: "invalid_response",
    });
  }
  return value;
}

function asNumber(value: unknown, field: string, status = 502): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new LocalApiClientError(`The local service returned an invalid ${field}.`, {
      status,
      code: "invalid_response",
    });
  }
  return value;
}

function asOptionalNumber(value: unknown, field: string, status = 502): number | null {
  if (value === null || value === undefined) return null;
  return asNumber(value, field, status);
}

function asJsonValue(value: unknown, field: string, status = 502): JsonValue {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (Array.isArray(value)) return value.map((item) => asJsonValue(item, field, status));
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, asJsonValue(item, `${field}.${key}`, status)]),
    );
  }
  throw new LocalApiClientError(`The local service returned an invalid ${field}.`, {
    status,
    code: "invalid_response",
  });
}

function asBoolean(value: unknown, field: string, status = 502): boolean {
  if (typeof value !== "boolean") {
    throw new LocalApiClientError(`The local service returned an invalid ${field}.`, {
      status,
      code: "invalid_response",
    });
  }
  return value;
}

function runtimeProfile(value: unknown, status = 502): RuntimeApiProfileSummary {
  const record = asRecord(value, status);
  return {
    provider: asString(record.provider, "runtime_profile.provider", status),
    base_url: asString(record.base_url, "runtime_profile.base_url", status),
    model_id: asString(record.model_id, "runtime_profile.model_id", status),
    api_key_env: asString(record.api_key_env, "runtime_profile.api_key_env", status),
    configured: asBoolean(record.configured, "runtime_profile.configured", status),
  };
}

function runtimeProfileResponse(value: unknown, status = 502): RuntimeProfileResponse {
  const record = schemaRecord(value, status);
  const agentId = record.agent_id === null ? null : asString(record.agent_id, "runtime_profile.agent_id", status);
  if (record.source !== "project" && record.source !== "agent") {
    throw new LocalApiClientError("The local service returned an invalid Runtime profile.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    project_id: asString(record.project_id, "runtime_profile.project_id", status),
    agent_id: agentId,
    source: record.source,
    profile: record.profile === null ? null : runtimeProfile(record.profile, status),
  };
}

function schemaRecord(value: unknown, status = 502): Record<string, unknown> {
  const record = asRecord(value, status);
  if (record.schema_version !== LOCAL_API_SCHEMA_VERSION) {
    throw new LocalApiClientError(
      "The local service returned an incompatible schema version.",
      { status, code: "schema_mismatch" },
    );
  }
  return record;
}

function source(value: unknown, status = 502): AgentSource {
  const record = schemaRecord(value, status);
  for (const field of [
    "agentspec_version",
    "component_type",
    "agent_id",
    "slug",
    "name",
    "description",
    "extensions",
    "ui",
    "lock",
  ]) {
    if (!(field in record)) {
      throw new LocalApiClientError(`The local service returned an invalid source (${field}).`, {
        status,
        code: "invalid_response",
      });
    }
  }
  asRecord(record.inputs, status);
  asRecord(record.outputs, status);
  asArray(record.nodes, "source.nodes", status);
  asArray(record.transitions, "source.transitions", status);
  asRecord(record.extensions, status);
  asRecord(record.ui, status);
  asRecord(record.lock, status);
  return record as unknown as AgentSource;
}

function projectAgent(value: unknown, status = 502): ProjectAgentRecord {
  const record = asRecord(value, status);
  return {
    agent_id: asString(record.agent_id, "agent_id", status),
    slug: asString(record.slug, "slug", status),
    name: asString(record.name, "name", status),
    description: asText(record.description, "description", status),
    pinned: record.pinned === true,
    source_path: asString(record.source_path, "source_path", status),
    source_file_hash: asString(record.source_file_hash, "source_file_hash", status),
    ...(record.parent_agent_id === undefined ? {} : {
      parent_agent_id: record.parent_agent_id === null
        ? null
        : asString(record.parent_agent_id, "parent_agent_id", status),
    }),
    ...(record.version === undefined ? {} : { version: asString(record.version, "version", status) }),
    ...(record.runtime_profile === undefined ? {} : {
      runtime_profile: record.runtime_profile === null
        ? null
        : runtimeProfile(record.runtime_profile, status),
    }),
    ...(record.community_origin === undefined ? {} : {
      community_origin: communityAgentOrigin(record.community_origin, status),
    }),
  };
}

function communityAgentOrigin(value: unknown, status = 502): CommunityAgentOrigin {
  const record = asRecord(value, status);
  return {
    owner_handle: asString(record.owner_handle, "community_origin.owner_handle", status),
    slug: asString(record.slug, "community_origin.slug", status),
    version: asString(record.version, "community_origin.version", status),
    source_hash: asString(record.source_hash, "community_origin.source_hash", status),
    imported_at: asString(record.imported_at, "community_origin.imported_at", status),
  };
}

function projectWorkflow(value: unknown, status = 502): ProjectWorkflowRecord {
  const record = asRecord(value, status);
  return {
    workflow_id: asString(record.workflow_id, "workflow_id", status),
    slug: asString(record.slug, "slug", status),
    name: asString(record.name, "name", status),
    description: asText(record.description, "description", status),
    source_path: asString(record.source_path, "source_path", status),
    source_file_hash: asString(record.source_file_hash, "source_file_hash", status),
    ...(record.version === undefined ? {} : { version: asString(record.version, "version", status) }),
  };
}

function knowledgeProcessing(value: unknown, status: number): KnowledgeProcessing {
  const record = asRecord(value, status);
  if (!(record.origin === "upload" || record.origin === "project_document") ||
      !(record.media_type === "text/plain" || record.media_type === "text/markdown") ||
      record.ingest_status !== "ingested" || record.parse_status !== "parsed" ||
      !(record.index_status === "not_indexed" || record.index_status === "indexed" || record.index_status === "stale" || record.index_status === "failed") ||
      (record.chunk_count != null && !(typeof record.chunk_count === "number" && Number.isSafeInteger(record.chunk_count) && record.chunk_count >= 0))) {
    throw new LocalApiClientError("Invalid Knowledge processing state", { status, code: "invalid_response" });
  }
  return {
    origin: record.origin, media_type: record.media_type,
    filename: asString(record.filename, "filename", status),
    content_hash: asString(record.content_hash, "content_hash", status),
    uploaded_content_hash: record.uploaded_content_hash === null ? null : asString(record.uploaded_content_hash, "uploaded_content_hash", status),
    ingest_status: record.ingest_status, parse_status: record.parse_status, index_status: record.index_status,
    ...(record.chunk_count === undefined ? {} : { chunk_count: record.chunk_count === null ? null : asNumber(record.chunk_count, "chunk_count", status) }),
    failure_reason: record.failure_reason === null ? null : asString(record.failure_reason, "failure_reason", status),
    updated_at: asString(record.updated_at, "updated_at", status),
  };
}

function projectKnowledge(value: unknown, status = 502): ProjectKnowledgeRecord {
  const record = asRecord(value, status);
  return {
    knowledge_id: asString(record.knowledge_id, "knowledge_id", status),
    ...(record.processing === undefined ? {} : { processing: knowledgeProcessing(record.processing, status) }),
    slug: asString(record.slug, "slug", status),
    name: asString(record.name, "name", status),
    description: asText(record.description, "description", status),
    source_path: asString(record.source_path, "source_path", status),
    source_file_hash: asString(record.source_file_hash, "source_file_hash", status),
    ...(record.version === undefined ? {} : { version: asString(record.version, "version", status) }),
  };
}

function projectSummary(value: unknown, status = 502): ProjectSummaryResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    project_id: asString(record.project_id, "project_id", status),
    root_path: asString(record.root_path, "root_path", status),
    name: asString(record.name, "name", status),
    description: asText(record.description, "description", status),
    pinned: record.pinned === true,
    pinned_at: record.pinned_at === null ? null : asString(record.pinned_at, "pinned_at", status),
    indexed_at: asString(record.indexed_at, "indexed_at", status),
    manifest_hash: asString(record.manifest_hash, "manifest_hash", status),
    default_agent_id: record.default_agent_id === null ? null : asString(record.default_agent_id, "default_agent_id", status),
    agent_count: asNumber(record.agent_count, "agent_count", status),
    agents: asArray(record.agents, "agents", status).map((item) => projectAgent(item, status)),
    ...(record.workflows === undefined ? {} : {
      workflows: asArray(record.workflows, "workflows", status).map((item) => projectWorkflow(item, status)),
    }),
    ...(record.workflow_count === undefined ? {} : {
      workflow_count: asNumber(record.workflow_count, "workflow_count", status),
    }),
    ...(record.knowledge === undefined ? {} : {
      knowledge: asArray(record.knowledge, "knowledge", status).map((item) => projectKnowledge(item, status)),
    }),
    ...(record.knowledge_count === undefined ? {} : {
      knowledge_count: asNumber(record.knowledge_count, "knowledge_count", status),
    }),
    ...(record.runtime_profile === undefined ? {} : {
      runtime_profile: record.runtime_profile === null
        ? null
        : runtimeProfile(record.runtime_profile, status),
    }),
  };
}

function listProjects(value: unknown, status = 502): ListProjectsResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    projects: asArray(record.projects, "projects", status).map((item) => projectSummary(item, status)),
  };
}

function revealedProject(value: unknown, status = 502): RevealProjectResponse {
  const record = schemaRecord(value, status);
  if (record.status !== "revealed") {
    throw new LocalApiClientError("The local service returned an invalid Project reveal.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    status: "revealed",
    root_path: asString(record.root_path, "root_path", status),
  };
}

function selectedDirectory(value: unknown, status = 502): SelectDirectoryResponse {
  const record = schemaRecord(value, status);
  if (record.status === "selected") return { schema_version: LOCAL_API_SCHEMA_VERSION, status: "selected", root_path: asString(record.root_path, "root_path", status) };
  if (record.status === "cancelled" && record.root_path === null) return { schema_version: LOCAL_API_SCHEMA_VERSION, status: "cancelled", root_path: null };
  throw new LocalApiClientError("The local service returned an invalid directory selection.", { status, code: "invalid_response" });
}

function selectedArchive(value: unknown, status = 502): SelectArchiveResponse {
  const record = schemaRecord(value, status);
  if (record.status === "selected") return { schema_version: LOCAL_API_SCHEMA_VERSION, status: "selected", path: asString(record.path, "path", status) };
  if (record.status === "cancelled" && record.path === null) return { schema_version: LOCAL_API_SCHEMA_VERSION, status: "cancelled", path: null };
  throw new LocalApiClientError("The local service returned an invalid archive selection.", { status, code: "invalid_response" });
}

function listAgents(value: unknown, status = 502): ListAgentsResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    agents: asArray(record.agents, "agents", status).map((item) => projectAgent(item, status)),
  };
}

const PROJECT_FILE_KINDS = new Set<ProjectFileKind>([
  "manifest",
  "agent_source",
  "readme",
  "test",
  "resource",
  "resource_manifest",
  "project_test",
  "workflow",
  "component",
  "knowledge",
  "asset",
  "file",
]);

function projectFile(value: unknown, status = 502): ProjectFileRecord {
  const record = asRecord(value, status);
  const kind = asString(record.kind, "kind", status);
  if (!PROJECT_FILE_KINDS.has(kind as ProjectFileKind)) {
    throw new LocalApiClientError("The local service returned an invalid file kind.", {
      status,
      code: "invalid_response",
    });
  }
  return {
    path: asString(record.path, "path", status),
    kind: kind as ProjectFileKind,
    byte_length: asNumber(record.byte_length, "byte_length", status),
    ...(record.agent_id === undefined ? {} : { agent_id: asString(record.agent_id, "agent_id", status) }),
  };
}

function projectFiles(value: unknown, status = 502): ProjectFilesResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    project_id: asString(record.project_id, "project_id", status),
    files: asArray(record.files, "files", status).map((item) => projectFile(item, status)),
  };
}

function projectFileContent(value: unknown, status = 502): ProjectFileContentResponse {
  const record = schemaRecord(value, status);
  return {
    ...projectFile(record, status),
    schema_version: LOCAL_API_SCHEMA_VERSION,
    project_id: asString(record.project_id, "project_id", status),
    text: asText(record.text, "text", status),
  };
}

function agentTemplate(value: unknown, status = 502): AgentTemplate {
  const record = asRecord(value, status);
  return {
    template_id: asString(record.template_id, "template_id", status),
    name: asString(record.name, "name", status),
    description: asText(record.description, "description", status),
    default_slug: asString(record.default_slug, "default_slug", status),
  };
}

function agentTemplates(value: unknown, status = 502): ListAgentTemplatesResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    templates: asArray(record.templates, "templates", status).map((item) => agentTemplate(item, status)),
  };
}

function createdAgent(value: unknown, status = 502): CreatedAgentResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    project_id: asString(record.project_id, "project_id", status),
    agent_id: asString(record.agent_id, "agent_id", status),
    slug: asString(record.slug, "slug", status),
    name: asString(record.name, "name", status),
    description: asText(record.description, "description", status),
    source_path: asString(record.source_path, "source_path", status),
    source_file_hash: asString(record.source_file_hash, "source_file_hash", status),
    ...(record.parent_agent_id === undefined ? {} : {
      parent_agent_id: record.parent_agent_id === null
        ? null
        : asString(record.parent_agent_id, "parent_agent_id", status),
    }),
    ...(record.runtime_profile === undefined ? {} : {
      runtime_profile: record.runtime_profile === null
        ? null
        : runtimeProfile(record.runtime_profile, status),
    }),
    ...(record.community_origin === undefined ? {} : {
      community_origin: communityAgentOrigin(record.community_origin, status),
    }),
  };
}

function deletedProject(value: unknown, status = 502): DeleteProjectResponse {
  const record = schemaRecord(value, status);
  const disposition = record.disposition;
  if (disposition !== "trashed" && disposition !== "unlinked") {
    throw new LocalApiClientError("The local service returned an invalid project deletion result.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    project_id: asString(record.project_id, "project_id", status),
    disposition,
    removed_at: asString(record.removed_at, "removed_at", status),
  };
}

function deletedAgent(value: unknown, status = 502): DeleteAgentResponse {
  const record = schemaRecord(value, status);
  if (record.disposition !== "trashed") {
    throw new LocalApiClientError("The local service returned an invalid Agent deletion result.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    project_id: asString(record.project_id, "project_id", status),
    agent_id: asString(record.agent_id, "agent_id", status),
    disposition: "trashed",
    removed_at: asString(record.removed_at, "removed_at", status),
    project: projectSummary(record.project, status),
  };
}

function draft(value: unknown, status = 502): DraftResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    draft_id: asString(record.draft_id, "draft_id", status),
    revision: asNumber(record.revision, "revision", status),
    etag: asString(record.etag, "etag", status),
    source_file_hash: asString(record.source_file_hash, "source_file_hash", status),
    source: source(record.source, status),
  };
}

function savedDraft(value: unknown, status = 502): SaveDraftResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    revision: asNumber(record.revision, "revision", status),
    etag: asString(record.etag, "etag", status),
    source: source(record.source, status),
  };
}

function versionIdentity(value: unknown, status: number) {
  const record = asRecord(value, status);
  const versionId = asString(record.version_id, "version_id", status);
  const sourceHash = asString(record.source_hash, "source_hash", status);
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(versionId) || !/^[0-9a-f]{64}$/.test(sourceHash)) {
    throw new LocalApiClientError("Invalid immutable version identity.", { status, code: "invalid_response" });
  }
  return { record, version_id: versionId, source_hash: sourceHash, behavior_hash: asString(record.behavior_hash, "behavior_hash", status), created_at: asString(record.created_at, "created_at", status) };
}

function agentVersions(value: unknown, status = 502): ListAgentVersionsResponse {
  const response = schemaRecord(value, status);
  return { schema_version: LOCAL_API_SCHEMA_VERSION, versions: asArray(response.versions, "versions", status).map((value) => {
    const { record, ...identity } = versionIdentity(value, status);
    const agentId = asString(record.agent_id, "agent_id", status);
    const snapshot = source(record.source, status);
    if (snapshot.agent_id !== agentId) throw new LocalApiClientError("Agent version identity mismatch.", { status, code: "invalid_response" });
    return { ...identity, agent_id: agentId, source: snapshot };
  }) };
}

function workflowVersions(value: unknown, status = 502): ListWorkflowVersionsResponse {
  const response = schemaRecord(value, status);
  return { schema_version: LOCAL_API_SCHEMA_VERSION, versions: asArray(response.versions, "versions", status).map((value) => {
    const { record, ...identity } = versionIdentity(value, status);
    const workflowId = asString(record.workflow_id, "workflow_id", status);
    const snapshot = workflowSource(record.source, status);
    if (snapshot.workflow_id !== workflowId) throw new LocalApiClientError("Workflow version identity mismatch.", { status, code: "invalid_response" });
    return { ...identity, workflow_id: workflowId, source: snapshot };
  }) };
}

function validated(value: unknown, status = 502): ValidateResponse {
  const record = schemaRecord(value, status);
  return { ...sourceValidation(record, status), file_hash: asString(record.file_hash, "file_hash", status) };
}

function sourceValidation(value: unknown, status = 502): Omit<ValidateResponse, "file_hash"> {
  const record = schemaRecord(value, status);
  const valid = asBoolean(record.valid, "validation.valid", status);
  const dependencies = record.dependencies === undefined
    ? undefined
    : asArray(record.dependencies, "validation.dependencies", status).map((item) => validationDependency(item, status));
  const dependencySummary = record.dependency_summary === undefined
    ? undefined
    : validationDependencySummary(record.dependency_summary, status);
  const runtimeReadyScope = record.runtime_ready_scope === undefined
    ? undefined
    : asString(record.runtime_ready_scope, "validation.runtime_ready_scope", status);
  if (runtimeReadyScope !== undefined && runtimeReadyScope !== "agent_dependencies") {
    throw new LocalApiClientError("The local service returned an invalid validation scope.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    valid,
    source_hash: asString(record.source_hash, "source_hash", status),
    behavior_hash: asString(record.behavior_hash, "behavior_hash", status),
    lock_hash: asString(record.lock_hash, "lock_hash", status),
    ...(dependencies === undefined ? {} : { dependencies }),
    ...(dependencySummary === undefined ? {} : { dependency_summary: dependencySummary }),
    ...(record.runtime_ready === undefined ? {} : { runtime_ready: asBoolean(record.runtime_ready, "validation.runtime_ready", status) }),
    ...(runtimeReadyScope === undefined ? {} : { runtime_ready_scope: "agent_dependencies" as const }),
  };
}

function builderResolution(value: unknown, status = 502): BuilderResolution {
  const record = schemaRecord(value, status);
  if (!["create", "edit", "discuss", "clarify"].includes(String(record.intent)) || !["resolved", "clarification", "unsupported"].includes(String(record.status)) || ![null, "agent", "workflow", "resource"].includes(record.create_kind as string | null)) {
    throw new LocalApiClientError("Invalid Builder resolution", { status, code: "invalid_response" });
  }
  const targets = asArray(record.targets, "targets", status).map((value): BuilderResolution["targets"][number] => {
    const target = asRecord(value, status);
    if (target.kind !== "agent" && target.kind !== "workflow") throw new LocalApiClientError("Invalid Builder target", { status, code: "invalid_response" });
    return { kind: target.kind, target_id: asString(target.target_id, "target_id", status), name: asString(target.name, "name", status), ...(target.revision === undefined ? {} : { revision: asNumber(target.revision, "revision", status), etag: asString(target.etag, "etag", status) }) };
  });
  if (record.status === "resolved" && record.intent === "edit" && (targets.length !== 1 || targets[0].revision === undefined)) throw new LocalApiClientError("Missing Builder edit baseline", { status, code: "invalid_response" });
  return { schema_version: LOCAL_API_SCHEMA_VERSION, intent: record.intent as BuilderResolution["intent"], create_kind: record.create_kind as BuilderResolution["create_kind"], status: record.status as BuilderResolution["status"], message: asString(record.message, "message", status), instruction: asText(record.instruction, "instruction", status), plan: asArray(record.plan, "plan", status).map((item) => asString(item, "plan item", status)), targets };
}

const builderMessageKinds = new Set<BuilderMessageKind>(["user", "assistant", "plan", "clarification", "failure", "proposal_reference", "reject", "confirm", "apply_summary", "validation_summary", "result"]);
const builderOperationStatuses = new Set<BuilderOperationStatus>(["in_progress", "waiting", "succeeded", "failed", "rejected"]);
const builderEventKinds = new Set<BuilderOperationEventKind>([
  "builder.operation.started",
  "builder.intent.started",
  "builder.intent.resolved",
  "builder.semantic_plan.started",
  "builder.semantic_plan.completed",
  "builder.capabilities.started",
  "builder.capabilities.resolved",
  "builder.compile.started",
  "builder.compile.completed",
  "builder.validation.started",
  "builder.validation.completed",
  "builder.proposal.ready",
  "builder.proposal.confirmed",
  "builder.proposal.rejected",
  "builder.apply.started",
  "builder.apply.completed",
  "builder.test_run.started",
  "builder.test_run.waiting_approval",
  "builder.test_run.completed",
  "builder.test_run.failed",
  "builder.test_run.stopped",
  "builder.operation.completed",
  "builder.operation.failed",
]);
const builderHarnessInvocationKinds = new Set(["resolve_intent", "interview", "semantic_plan", "semantic_plan_repair"]);
const builderHarnessReceiptStatuses = new Set(["prepared", "success", "failed"]);
const builderHarnessStructuredModes = new Set(["strict_json_schema", "json_object", "none"]);

function optionalId(value: unknown, field: string, status: number): string | null {
  if (value === null || value === undefined) return null;
  return asString(value, field, status);
}

function stringFacts(value: unknown, field: string, status: number): Record<string, string> {
  const record = asRecord(value, status);
  return Object.fromEntries(Object.entries(record).map(([key, item]) => [key, asText(item, `${field}.${key}`, status)]));
}

function builderConversationMessage(value: unknown, status: number): BuilderConversationMessage {
  const record = asRecord(value, status);
  const kind = asString(record.kind, "builder.message.kind", status) as BuilderMessageKind;
  const role = asString(record.role, "builder.message.role", status);
  if (!builderMessageKinds.has(kind) || (role !== "user" && role !== "assistant" && role !== "system")) {
    throw new LocalApiClientError("Invalid Builder conversation message", { status, code: "invalid_response" });
  }
  return {
    message_id: asString(record.message_id, "builder.message_id", status),
    conversation_id: asString(record.conversation_id, "builder.conversation_id", status),
    sequence: asNumber(record.sequence, "builder.sequence", status),
    role,
    kind,
    content: asText(record.content, "builder.content", status),
    operation_id: optionalId(record.operation_id, "builder.operation_id", status),
    payload: stringFacts(record.payload, "builder.payload", status),
    created_at: asString(record.created_at, "builder.created_at", status),
  };
}

function builderOperationEvent(value: unknown, status: number): BuilderOperationEvent {
  const record = asRecord(value, status);
  const kind = asString(record.kind, "builder.event.kind", status) as BuilderOperationEventKind;
  if (!builderEventKinds.has(kind)) {
    throw new LocalApiClientError("Invalid Builder operation event", { status, code: "invalid_response" });
  }
  return {
    event_id: asString(record.event_id, "builder.event_id", status),
    operation_id: asString(record.operation_id, "builder.event.operation_id", status),
    sequence: asNumber(record.sequence, "builder.event.sequence", status),
    kind,
    label: asText(record.label, "builder.event.label", status),
    summary: asText(record.summary, "builder.event.summary", status),
    facts: stringFacts(record.facts, "builder.event.facts", status),
    created_at: asString(record.created_at, "builder.event.created_at", status),
  };
}

function builderHarnessReceipt(value: unknown, status: number): BuilderHarnessReceipt {
  const record = asRecord(value, status);
  const invocation = asString(record.invocation_kind, "builder.receipt.invocation_kind", status) as BuilderHarnessReceipt["invocation_kind"];
  if (!builderHarnessInvocationKinds.has(invocation)) {
    throw new LocalApiClientError("Invalid Builder harness receipt", { status, code: "invalid_response" });
  }
  const receiptStatus = asString(record.status, "builder.receipt.status", status) as BuilderHarnessReceipt["status"];
  if (!builderHarnessReceiptStatuses.has(receiptStatus)) {
    throw new LocalApiClientError("Invalid Builder harness receipt status", { status, code: "invalid_response" });
  }
  const structured = asString(record.structured_mode, "builder.receipt.structured_mode", status) as BuilderHarnessReceipt["structured_mode"];
  if (!builderHarnessStructuredModes.has(structured)) {
    throw new LocalApiClientError("Invalid Builder harness structured mode", { status, code: "invalid_response" });
  }
  return {
    receipt_id: asString(record.receipt_id, "builder.receipt_id", status),
    operation_id: asString(record.operation_id, "builder.receipt.operation_id", status),
    conversation_id: asString(record.conversation_id, "builder.receipt.conversation_id", status),
    project_id: asString(record.project_id, "builder.receipt.project_id", status),
    invocation_kind: invocation,
    sequence: asNumber(record.sequence, "builder.receipt.sequence", status),
    status: receiptStatus,
    started_at: asString(record.started_at, "builder.receipt.started_at", status),
    completed_at: optionalId(record.completed_at, "builder.receipt.completed_at", status),
    harness_mode: asString(record.harness_mode, "builder.receipt.harness_mode", status),
    policy_version: asString(record.policy_version, "builder.receipt.policy_version", status),
    policy_hash: asString(record.policy_hash, "builder.receipt.policy_hash", status),
    output_contract: asString(record.output_contract, "builder.receipt.output_contract", status),
    schema_version: asString(record.schema_version, "builder.receipt.schema_version", status),
    schema_hash: asString(record.schema_hash, "builder.receipt.schema_hash", status),
    structured_mode: structured,
    project_snapshot_hash: asString(record.project_snapshot_hash, "builder.receipt.project_snapshot_hash", status),
    catalog_snapshot_hash: asString(record.catalog_snapshot_hash, "builder.receipt.catalog_snapshot_hash", status),
    included_categories: asArray(record.included_categories, "builder.receipt.included_categories", status).map((item) => asString(item, "builder.receipt.included", status)) as BuilderHarnessReceipt["included_categories"],
    excluded_categories: asArray(record.excluded_categories, "builder.receipt.excluded_categories", status).map((item) => asString(item, "builder.receipt.excluded", status)) as BuilderHarnessReceipt["excluded_categories"],
    history_message_count: asNumber(record.history_message_count, "builder.receipt.history_message_count", status),
    context_size_bytes: asNumber(record.context_size_bytes, "builder.receipt.context_size_bytes", status),
    request_size_bytes: asNumber(record.request_size_bytes, "builder.receipt.request_size_bytes", status),
    provider_id: asString(record.provider_id, "builder.receipt.provider_id", status),
    model: asString(record.model, "builder.receipt.model", status),
    endpoint_kind: asString(record.endpoint_kind, "builder.receipt.endpoint_kind", status),
    provider_profile_status: asString(record.provider_profile_status, "builder.receipt.provider_profile_status", status),
    provider_profile_source: asString(record.provider_profile_source, "builder.receipt.provider_profile_source", status),
    schema_profile: asString(record.schema_profile, "builder.receipt.schema_profile", status),
    failure_stage: optionalId(record.failure_stage, "builder.receipt.failure_stage", status),
    error_code: optionalId(record.error_code, "builder.receipt.error_code", status),
    safe_provider_error_type: optionalId(record.safe_provider_error_type, "builder.receipt.safe_provider_error_type", status),
    safe_provider_error_param: optionalId(record.safe_provider_error_param, "builder.receipt.safe_provider_error_param", status),
    provider_request_id: optionalId(record.provider_request_id, "builder.receipt.provider_request_id", status),
    fallback_from: optionalId(record.fallback_from, "builder.receipt.fallback_from", status),
    fallback_to: optionalId(record.fallback_to, "builder.receipt.fallback_to", status),
  };
}

function builderConversationOperation(value: unknown, status: number): BuilderConversationOperation {
  const record = asRecord(value, status);
  const opStatus = asString(record.status, "builder.operation.status", status) as BuilderOperationStatus;
  if (!builderOperationStatuses.has(opStatus)) throw new LocalApiClientError("Invalid Builder operation", { status, code: "invalid_response" });
  const targetKind = record.target_kind;
  let target: BuilderTargetKind | null = null;
  if (targetKind !== null && targetKind !== undefined && targetKind !== "") {
    if (targetKind !== "agent" && targetKind !== "workflow") {
      throw new LocalApiClientError("Invalid Builder operation target", { status, code: "invalid_response" });
    }
    target = targetKind;
  }
  return {
    operation_id: asString(record.operation_id, "builder.operation_id", status),
    conversation_id: asString(record.conversation_id, "builder.conversation_id", status),
    kind: asString(record.kind, "builder.operation.kind", status),
    target_kind: target,
    status: opStatus,
    retry_of: optionalId(record.retry_of, "builder.retry_of", status),
    error_code: optionalId(record.error_code, "builder.error_code", status),
    proposal_id: optionalId(record.proposal_id, "builder.proposal_id", status),
    run_id: optionalId(record.run_id, "builder.run_id", status),
    factory_session_id: optionalId(record.factory_session_id, "builder.factory_session_id", status),
    created_at: asString(record.created_at, "builder.operation.created_at", status),
    updated_at: asString(record.updated_at, "builder.operation.updated_at", status),
    diagnostic: stringFacts(record.diagnostic, "builder.diagnostic", status),
    has_request: asBoolean(record.has_request, "builder.has_request", status),
    events: asArray(record.events ?? [], "builder.operation.events", status).map((item) => builderOperationEvent(item, status)),
    receipts: asArray(record.receipts ?? [], "builder.operation.receipts", status).map((item) => builderHarnessReceipt(item, status)),
    run_observation: record.run_observation === undefined || record.run_observation === null
      ? null
      : builderRunObservation(record.run_observation, status),
  };
}

const builderRunClassifications = new Set(["none", "repairable", "user_action", "environment", "semantic"]);

function builderRunObservation(value: unknown, status: number): BuilderRunObservation {
  const record = asRecord(value, status);
  const classification = asString(record.classification, "builder.observation.classification", status) as BuilderRunObservation["classification"];
  if (!builderRunClassifications.has(classification)) {
    throw new LocalApiClientError("Invalid Builder run observation", { status, code: "invalid_response" });
  }
  const output = record.output_summary;
  if (output !== null && output !== undefined && typeof output !== "string") {
    throw new LocalApiClientError("Invalid Builder run observation output", { status, code: "invalid_response" });
  }
  return {
    run_id: optionalId(record.run_id, "builder.observation.run_id", status),
    agent_id: asString(record.agent_id, "builder.observation.agent_id", status),
    version_id: optionalId(record.version_id, "builder.observation.version_id", status),
    status: asString(record.status, "builder.observation.status", status),
    runtime_model_id: asText(record.runtime_model_id ?? "", "builder.observation.runtime_model_id", status),
    runtime_model_source: asText(record.runtime_model_source ?? "", "builder.observation.runtime_model_source", status),
    output_summary: output === undefined ? null : output,
    failure_code: optionalId(record.failure_code, "builder.observation.failure_code", status),
    failed_node: optionalId(record.failed_node, "builder.observation.failed_node", status),
    tool_failure: optionalId(record.tool_failure, "builder.observation.tool_failure", status),
    knowledge_failure: optionalId(record.knowledge_failure, "builder.observation.knowledge_failure", status),
    approval_required: asBoolean(record.approval_required, "builder.observation.approval_required", status),
    duration_ms: asOptionalNumber(record.duration_ms, "builder.observation.duration_ms", status),
    evidence_count: asNumber(record.evidence_count, "builder.observation.evidence_count", status),
    classification,
    explanation: asText(record.explanation ?? "", "builder.observation.explanation", status),
    repair_proposal_id: optionalId(record.repair_proposal_id, "builder.observation.repair_proposal_id", status),
    repair_code: optionalId(record.repair_code, "builder.observation.repair_code", status),
    next_action: optionalId(record.next_action, "builder.observation.next_action", status),
  };
}

function builderConversationSummary(value: unknown, status: number): BuilderConversationSummary {
  const record = asRecord(value, status);
  const last = record.last_operation_status;
  if (last !== null && last !== undefined && !builderOperationStatuses.has(last as BuilderOperationStatus)) {
    throw new LocalApiClientError("Invalid Builder conversation status", { status, code: "invalid_response" });
  }
  return {
    conversation_id: asString(record.conversation_id, "builder.conversation_id", status),
    project_id: asString(record.project_id, "builder.project_id", status),
    title: asText(record.title, "builder.title", status),
    status: asString(record.status, "builder.status", status),
    created_at: asString(record.created_at, "builder.created_at", status),
    updated_at: asString(record.updated_at, "builder.updated_at", status),
    last_activity_at: asString(record.last_activity_at, "builder.last_activity_at", status),
    last_operation_status: last === null || last === undefined ? null : last as BuilderOperationStatus,
  };
}

function builderConversationSnapshot(value: unknown, status = 502): BuilderConversationSnapshot {
  const record = schemaRecord(value, status);
  let factorySessionValue: FactorySession | null = null;
  if (record.factory_session !== null && record.factory_session !== undefined) {
    try {
      factorySessionValue = factorySession(record.factory_session, status);
    } catch (cause) {
      if (!(cause instanceof LocalApiClientError) || cause.code !== "invalid_response") throw cause;
    }
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    conversation: builderConversationSummary(record.conversation, status),
    messages: asArray(record.messages, "builder.messages", status).map((item) => builderConversationMessage(item, status)),
    operations: asArray(record.operations, "builder.operations", status).map((item) => builderConversationOperation(item, status)),
    resolution: record.resolution === null || record.resolution === undefined ? null : builderResolution(record.resolution, status),
    factory_session: factorySessionValue,
  };
}

function builderConversationDeleted(value: unknown, status = 502): BuilderConversationDeleted {
  const record = schemaRecord(value, status);
  if (record.deleted !== true) {
    throw new LocalApiClientError("Invalid Builder conversation delete", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    conversation_id: asString(record.conversation_id, "builder.conversation_id", status),
    deleted: true,
  };
}

function builderActivityItem(value: unknown, status: number): BuilderActivityItem | null {
  const record = asRecord(value, status);
  if (record.kind === "run") return null;
  if (record.kind !== "conversation") {
    throw new LocalApiClientError("Invalid Builder activity item", { status, code: "invalid_response" });
  }
  return {
    kind: "conversation",
    id: asString(record.id, "activity.id", status),
    conversation_id: asString(record.conversation_id, "activity.conversation_id", status),
    ...(typeof record.project_id === "string" && record.project_id ? { project_id: record.project_id } : {}),
    title: asText(record.title, "activity.title", status),
    status: asString(record.status, "activity.status", status),
    operation_kind: asString(record.operation_kind, "activity.operation_kind", status),
    occurred_at: asString(record.occurred_at, "activity.occurred_at", status),
  };
}

function builderActivityResponse(value: unknown, status = 502): BuilderActivityResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    project_id: asText(record.project_id, "activity.project_id", status),
    items: asArray(record.items, "activity.items", status).flatMap((item) => {
      const parsed = builderActivityItem(item, status);
      return parsed ? [parsed] : [];
    }),
  };
}

function knowledgeBindingPlan(value: unknown, status: number): KnowledgeBindingPlan {
  const record = asRecord(value, status);
  const indexStatus = record.index_status;
  const action = record.required_action;
  if (!["not_indexed", "indexed", "stale", "failed"].includes(String(indexStatus))
    || typeof record.runnable !== "boolean"
    || record.runnable !== (indexStatus === "indexed")
    || !(action === null || action === "build_index" || action === "rebuild_index")) {
    throw new LocalApiClientError("The local service returned an invalid Knowledge binding plan.", { status, code: "invalid_response" });
  }
  return {
    reference: asString(record.reference, "knowledge_binding.reference", status),
    name: asText(record.name, "knowledge_binding.name", status),
    source_file_hash: asString(record.source_file_hash, "knowledge_binding.source_file_hash", status),
    index_status: indexStatus as KnowledgeProcessing["index_status"],
    ...(record.chunk_count === undefined || record.chunk_count === null ? {} : { chunk_count: asNumber(record.chunk_count, "knowledge_binding.chunk_count", status) }),
    failure_reason: record.failure_reason === null ? null : asString(record.failure_reason, "knowledge_binding.failure_reason", status),
    runnable: record.runnable,
    required_action: action,
  };
}

function resourceBindingPlan(value: unknown, status: number): ResourceBindingPlan {
  const record = asRecord(value, status);
  const bindingStatus = record.binding_status;
  const readiness = record.readiness;
  const availability = record.availability;
  const runtimeStatus = record.runtime_status;
  const boundHash = asString(record.bound_content_hash, "resource_binding.bound_content_hash", status);
  const catalogHash = asString(record.catalog_content_hash, "resource_binding.catalog_content_hash", status);
  const hashPattern = /^[0-9a-f]{64}$/;
  const validReadiness = new Set(["ready", "requires_configuration", "design_only", "unavailable", "quarantined", "unsupported", "stale"]);
  const stale = bindingStatus === "stale";
  if ((bindingStatus !== "current" && !stale)
    || !validReadiness.has(String(readiness))
    || !resourceAvailability.has(availability as ResourceAvailability)
    || !resourceRuntimeStatuses.has(runtimeStatus as ResourceRuntimeStatus)
    || !hashPattern.test(boundHash)
    || !hashPattern.test(catalogHash)
    || stale !== (boundHash !== catalogHash)
    || stale !== (readiness === "stale")
    || (readiness === "ready" && (stale || availability !== "ready" || runtimeStatus !== "supported"))
    || record.project_resource_changed !== false
    || record.automatic_upgrade !== false) {
    throw new LocalApiClientError("The local service returned an invalid Resource binding plan.", { status, code: "invalid_response" });
  }
  return {
    reference: asString(record.reference, "resource_binding.reference", status),
    name: asText(record.name, "resource_binding.name", status),
    bound_content_hash: boundHash,
    catalog_content_hash: catalogHash,
    binding_status: bindingStatus,
    readiness: readiness as ResourceBindingPlan["readiness"],
    availability: availability as ResourceAvailability,
    runtime_status: runtimeStatus as ResourceRuntimeStatus,
    required_permissions: resourcePermissions(record.required_permissions, status),
    blocking_reasons: asArray(record.blocking_reasons, "resource_binding.blocking_reasons", status).map((value) => {
      const reason = asRecord(value, status);
      return { code: asString(reason.code, "blocking_reason.code", status), message: asString(reason.message, "blocking_reason.message", status) };
    }),
    project_resource_changed: false,
    automatic_upgrade: false,
  };
}

function validationRepairPlan(value: unknown, status: number): ValidationRepairPlan {
  const record = asRecord(value, status);
  if (record.repairable !== true || record.automatic_upgrade !== false || record.project_resource_changed !== false || record.target_kind !== "agent") {
    throw new LocalApiClientError("The local service returned an invalid validation repair plan.", { status, code: "invalid_response" });
  }
  const hash = (field: "locked_hash" | "bound_content_hash" | "content_hash") => {
    if (record[field] === undefined || record[field] === null) return {};
    const digest = asString(record[field], `validation_repair.${field}`, status);
    if (!/^[0-9a-f]{64}$/.test(digest)) {
      throw new LocalApiClientError("The local service returned an invalid validation repair plan.", { status, code: "invalid_response" });
    }
    return { [field]: digest };
  };
  return {
    code: asString(record.code, "validation_repair.code", status),
    kind: asString(record.kind, "validation_repair.kind", status),
    reference: asString(record.reference, "validation_repair.reference", status),
    name: asText(record.name, "validation_repair.name", status),
    repairable: true,
    automatic_upgrade: false,
    project_resource_changed: false,
    ...hash("locked_hash"),
    ...hash("bound_content_hash"),
    ...hash("content_hash"),
    ...(record.required_permissions === undefined ? {} : { required_permissions: resourcePermissions(record.required_permissions, status) }),
    target_kind: "agent",
    impact: asText(record.impact, "validation_repair.impact", status),
  };
}

function editProposal(value: unknown, status = 502): EditProposal {
  const record = schemaRecord(value, status);
  const impact = asRecord(record.impact, status);
  const validation = schemaRecord(record.validation, status);
  const kind = record.target_kind;
  const state = record.state;
  const candidate = kind === "workflow" ? workflowSource(record.candidate_source, status) : source(record.candidate_source, status);
  if ((kind !== "agent" && kind !== "workflow") || !["review", "applied", "rejected", "undone"].includes(String(state))
    || impact.scope !== "single_draft" || impact.immutable_versions_changed !== false || impact.runs_started !== false
    || impact.target_kind !== kind || impact.target_id !== record.target_id
    || (kind === "agent" ? candidate.component_type !== "Flow" || candidate.agent_id !== record.target_id : candidate.component_type !== "Workflow" || candidate.workflow_id !== record.target_id)) {
    throw new LocalApiClientError("The local service returned an invalid edit proposal.", { status, code: "invalid_response" });
  }
  const changes = (value: unknown): EditProposalChange[] => asArray(value, "proposal changes", status).map((item) => {
    const change = asRecord(item, status);
    if (!["add", "remove", "replace"].includes(String(change.operation)) || !("before" in change) || !("after" in change)) {
      throw new LocalApiClientError("The local service returned an invalid proposal change.", { status, code: "invalid_response" });
    }
    return { path: asText(change.path, "change.path", status), operation: change.operation as EditProposalChange["operation"], before: change.before as JsonValue, after: change.after as JsonValue };
  });
  const checks = sourceValidation(validation, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    proposal_id: asString(record.proposal_id, "proposal_id", status),
    project_id: asString(record.project_id, "project_id", status),
    target_kind: kind, target_id: asString(record.target_id, "target_id", status),
    instruction: asString(record.instruction, "instruction", status), created_at: asString(record.created_at, "created_at", status),
    base_revision: asNumber(record.base_revision, "base_revision", status), base_etag: asString(record.base_etag, "base_etag", status),
    candidate_source: candidate, changes: changes(record.changes), permission_changes: changes(record.permission_changes),
    ...(record.knowledge_binding === undefined ? {} : { knowledge_binding: knowledgeBindingPlan(record.knowledge_binding, status) }),
    ...(record.resource_binding === undefined ? {} : { resource_binding: resourceBindingPlan(record.resource_binding, status) }),
    ...(record.validation_repair === undefined ? {} : { validation_repair: validationRepairPlan(record.validation_repair, status) }),
    impact: { target_kind: kind, target_id: asString(impact.target_id, "impact.target_id", status), scope: "single_draft", immutable_versions_changed: false, runs_started: false },
    validation: { ...checks, ...(validation.agent_calls === undefined ? {} : { agent_calls: asArray(validation.agent_calls, "agent_calls", status).map((item) => {
      const call = asRecord(item, status);
      return { node_id: asString(call.node_id, "node_id", status), agent_id: asString(call.agent_id, "agent_id", status), version_id: asString(call.version_id, "version_id", status) };
    }) }) },
    state: state as EditProposal["state"], stale: asBoolean(record.stale, "stale", status),
    applied_revision: record.applied_revision === null ? null : asNumber(record.applied_revision, "applied_revision", status),
  };
}

function validationDependency(value: unknown, status = 502): AgentDependencyCheck {
  const record = asRecord(value, status);
  const kind = asString(record.kind, "validation dependency kind", status);
  const dependencyStatus = asString(record.status, "validation dependency status", status);
  const kinds = new Set(["component", "tool", "mcp_tool", "skill", "policy", "template", "knowledge"]);
  const statuses = new Set<AgentDependencyStatus>(["ready", "missing", "lock_missing", "lock_mismatch", "kind_mismatch", "configuration_required", "runtime_unavailable", "review_required", "permission_denied", "secret_declaration_missing", "context_not_declared", "context_too_large", "project_binding_stale", "resource_unbound"]);
  if (!kinds.has(kind) || !statuses.has(dependencyStatus as AgentDependencyStatus)) {
    throw new LocalApiClientError("The local service returned an invalid Agent dependency check.", { status, code: "invalid_response" });
  }
  const runtimeMode = record.runtime_mode === undefined ? undefined : asString(record.runtime_mode, "validation dependency runtime_mode", status);
  if (runtimeMode !== undefined && !new Set(["tool_adapter", "model_context", "source_policy", "design_only", "knowledge_context", "catalog"]).has(runtimeMode)) {
    throw new LocalApiClientError("The local service returned an invalid Agent dependency runtime mode.", { status, code: "invalid_response" });
  }
  const availability = record.availability === undefined ? undefined : asString(record.availability, "validation dependency availability", status) as ResourceAvailability;
  const runtimeStatus = record.runtime_status === undefined ? undefined : asString(record.runtime_status, "validation dependency runtime_status", status) as ResourceRuntimeStatus;
  const projectBindingStatus = record.project_binding_status === undefined ? undefined : asString(record.project_binding_status, "validation dependency project_binding_status", status) as AgentDependencyCheck["project_binding_status"];
  if (projectBindingStatus !== undefined && !new Set(["current", "stale", "unbound", "unknown"]).has(projectBindingStatus)) {
    throw new LocalApiClientError("The local service returned an invalid Agent dependency project binding status.", { status, code: "invalid_response" });
  }
  if (availability !== undefined && !resourceAvailability.has(availability)) {
    throw new LocalApiClientError("The local service returned an invalid Agent dependency availability.", { status, code: "invalid_response" });
  }
  if (runtimeStatus !== undefined && !resourceRuntimeStatuses.has(runtimeStatus)) {
    throw new LocalApiClientError("The local service returned an invalid Agent dependency runtime status.", { status, code: "invalid_response" });
  }
  return {
    reference: asString(record.reference, "validation dependency reference", status),
    kind: kind as AgentDependencyCheck["kind"],
    name: asString(record.name, "validation dependency name", status),
    status: dependencyStatus as AgentDependencyStatus,
    detail: asText(record.detail, "validation dependency detail", status),
    ...(record.locked_hash === undefined ? {} : { locked_hash: asString(record.locked_hash, "validation dependency locked_hash", status) }),
    ...(record.bound_content_hash === undefined ? {} : { bound_content_hash: asString(record.bound_content_hash, "validation dependency bound_content_hash", status) }),
    ...(record.blocking_reasons === undefined ? {} : { blocking_reasons: asArray(record.blocking_reasons, "validation dependency blocking_reasons", status).map((value) => { const reason = asRecord(value, status); return { code: asString(reason.code, "blocking reason code", status), message: asString(reason.message, "blocking reason message", status) }; }) }),
    ...(record.content_hash === undefined ? {} : { content_hash: asString(record.content_hash, "validation dependency content_hash", status) }),
    ...(record.version === undefined ? {} : { version: asString(record.version, "validation dependency version", status) }),
    ...(availability === undefined ? {} : { availability }),
    ...(runtimeStatus === undefined ? {} : { runtime_status: runtimeStatus }),
    ...(runtimeMode === undefined ? {} : { runtime_mode: runtimeMode as AgentDependencyCheck["runtime_mode"] }),
    ...(record.required_permissions === undefined ? {} : { required_permissions: resourcePermissions(record.required_permissions, status) }),
    ...(record.byte_length === undefined ? {} : { byte_length: asNumber(record.byte_length, "validation dependency byte_length", status) }),
    used_by: asArray(record.used_by, "validation dependency used_by", status).map((item) => asString(item, "validation dependency node", status)),
    bound_by: asArray(record.bound_by, "validation dependency bound_by", status).map((item) => asString(item, "validation dependency binding", status)),
    ...(projectBindingStatus === undefined ? {} : { project_binding_status: projectBindingStatus }),
  };
}

function validationDependencySummary(value: unknown, status = 502): AgentDependencySummary {
  const record = asRecord(value, status);
  return {
    total: asNumber(record.total, "validation dependency total", status),
    ready: asNumber(record.ready, "validation dependency ready", status),
    attention: asNumber(record.attention, "validation dependency attention", status),
  };
}

function committed(value: unknown, status = 502): CommitResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    version_id: asString(record.version_id, "version_id", status),
    ...(record.agent_id === undefined ? {} : { agent_id: asString(record.agent_id, "agent_id", status) }),
    ...(record.workflow_id === undefined ? {} : { workflow_id: asString(record.workflow_id, "workflow_id", status) }),
    source_hash: asString(record.source_hash, "source_hash", status),
    behavior_hash: asString(record.behavior_hash, "behavior_hash", status),
    lock_hash: asString(record.lock_hash, "lock_hash", status),
    file_hash: asString(record.file_hash, "file_hash", status),
  };
}

function workflowSource(value: unknown, status = 502): WorkflowSource {
  const record = schemaRecord(value, status);
  for (const field of [
    "component_type",
    "workflow_id",
    "slug",
    "name",
    "description",
    "extensions",
    "ui",
    "lock",
  ]) {
    if (!(field in record)) {
      throw new LocalApiClientError(`The local service returned an invalid workflow source (${field}).`, {
        status,
        code: "invalid_response",
      });
    }
  }
  asRecord(record.inputs, status);
  asRecord(record.outputs, status);
  asArray(record.nodes, "source.nodes", status);
  asArray(record.transitions, "source.transitions", status);
  asRecord(record.extensions, status);
  asRecord(record.ui, status);
  asRecord(record.lock, status);
  return record as unknown as WorkflowSource;
}

function workflowDraft(value: unknown, status = 502): WorkflowDraftResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    draft_id: asString(record.draft_id, "draft_id", status),
    revision: asNumber(record.revision, "revision", status),
    etag: asString(record.etag, "etag", status),
    source_file_hash: asString(record.source_file_hash, "source_file_hash", status),
    source: workflowSource(record.source, status),
  };
}

function savedWorkflowDraft(value: unknown, status = 502): SaveWorkflowDraftResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    revision: asNumber(record.revision, "revision", status),
    etag: asString(record.etag, "etag", status),
    source: workflowSource(record.source, status),
  };
}

function createdWorkflow(value: unknown, status = 502): CreatedWorkflowResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    project_id: asString(record.project_id, "project_id", status),
    workflow_id: asString(record.workflow_id, "workflow_id", status),
    slug: asString(record.slug, "slug", status),
    name: asString(record.name, "name", status),
    description: asText(record.description, "description", status),
    source_path: asString(record.source_path, "source_path", status),
    source_file_hash: asString(record.source_file_hash, "source_file_hash", status),
    ...(record.version === undefined ? {} : { version: asString(record.version, "version", status) }),
    ...(record.node_count === undefined ? {} : { node_count: asNumber(record.node_count, "node_count", status) }),
    ...(record.transition_count === undefined ? {} : { transition_count: asNumber(record.transition_count, "transition_count", status) }),
  };
}

function deletedWorkflow(value: unknown, status = 502): DeleteWorkflowResponse {
  const record = schemaRecord(value, status);
  if (record.disposition !== "trashed") {
    throw new LocalApiClientError("The local service returned an invalid Workflow deletion result.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    project_id: asString(record.project_id, "project_id", status),
    workflow_id: asString(record.workflow_id, "workflow_id", status),
    disposition: "trashed",
    removed_at: asString(record.removed_at, "removed_at", status),
    project: projectSummary(record.project, status),
  };
}

function knowledgeDocument(value: unknown, status = 502): KnowledgeDocumentResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    ...(record.processing === undefined ? {} : { processing: knowledgeProcessing(record.processing, status) }),
    project_id: asString(record.project_id, "project_id", status),
    knowledge_id: asString(record.knowledge_id, "knowledge_id", status),
    slug: asString(record.slug, "slug", status),
    name: asString(record.name, "name", status),
    description: asText(record.description, "description", status),
    source_path: asString(record.source_path, "source_path", status),
    source_file_hash: asString(record.source_file_hash, "source_file_hash", status),
    text: asText(record.text, "text", status),
    ...(record.version === undefined ? {} : { version: asString(record.version, "version", status) }),
  };
}

function deletedKnowledge(value: unknown, status = 502): DeleteKnowledgeResponse {
  const record = schemaRecord(value, status);
  if (record.disposition !== "trashed") {
    throw new LocalApiClientError("The local service returned an invalid Knowledge deletion result.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    project_id: asString(record.project_id, "project_id", status),
    knowledge_id: asString(record.knowledge_id, "knowledge_id", status),
    disposition: "trashed",
    removed_at: asString(record.removed_at, "removed_at", status),
    project: projectSummary(record.project, status),
  };
}

const componentTypes = new Set<ComponentDefinition["type"]>([
  "Start",
  "Agent",
  "Model",
  "AgentCall",
  "Tool",
  "Condition",
  "Transform",
  "HumanApproval",
  "Verifier",
  "Output",
]);
const transitionPorts = new Set<ComponentDefinition["output_ports"][number]>([
  "next",
  "true",
  "false",
  "approved",
  "rejected",
  "passed",
  "failed",
]);
const runtimeStatuses = new Set<ComponentDefinition["runtime_status"]>([
  "supported",
  "runtime_not_configured",
  "runtime_not_supported",
]);
const runtimeEventKinds = new Set<NonNullable<AgentRunResponse["events"]>[number]["kind"]>([
  "run.created", "run.state_changed", "run.started", "run.completed", "run.interrupted", "run.failed", "run.cancelled",
  "node.queued", "node.state_changed", "node.started", "node.output", "node.waiting", "node.completed", "node.failed", "node.skipped", "node.cancelled",
  "tool.requested", "tool.started", "tool.completed", "tool.failed", "model.delta", "approval.requested", "approval.resolved", "input.requested", "input.resolved",
  "artifact.created", "checkpoint.created", "verification.completed", "verifier.result",
]);

function componentDefinition(value: unknown, status = 502): ComponentDefinition {
  const record = asRecord(value, status);
  const type = asString(record.type, "component.type", status) as ComponentDefinition["type"];
  const runtimeStatus = asString(record.runtime_status, "component.runtime_status", status) as ComponentDefinition["runtime_status"];
  const fields = asArray(record.fields, "component.fields", status).map((item) => asString(item, "component field", status));
  const outputPorts = asArray(record.output_ports, "component.output_ports", status).map((item) => asString(item, "component output port", status) as ComponentDefinition["output_ports"][number]);
  if (!componentTypes.has(type) || !runtimeStatuses.has(runtimeStatus) || outputPorts.some((port) => !transitionPorts.has(port))) {
    throw new LocalApiClientError("The local service returned an unknown Component definition.", { status, code: "invalid_response" });
  }
  return { type, fields, output_ports: outputPorts, runtime_status: runtimeStatus };
}

function listedComponents(value: unknown, status = 502): ListComponentsResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    components: asArray(record.components, "components", status).map((item) => componentDefinition(item, status)),
  };
}

const resourceKinds = new Set<ResourceKind>(["component", "tool", "mcp_tool", "skill", "policy", "template"]);
const resourceAvailability = new Set<ResourceAvailability>(["ready", "requires_configuration", "design_only", "quarantined", "disabled", "unavailable"]);
const resourceRuntimeStatuses = new Set<ResourceRuntimeStatus>(["supported", "runtime_not_configured", "runtime_not_supported"]);
const resourceOrigins = new Set<ResourceOrigin>(["builtin", "workshop", "discovered"]);

function resourcePermissions(value: unknown, status = 502): ResourceDescriptor["required_permissions"] {
  const record = asRecord(value, status);
  const list = (field: string) => asArray(record[field], `resource.required_permissions.${field}`, status).map((item) => asString(item, `resource.required_permissions.${field}`, status));
  if (typeof record.shell_workspace_only !== "boolean") throw new LocalApiClientError("The local service returned invalid resource permissions.", { status, code: "invalid_response" });
  return {
    network_hosts: list("network_hosts"),
    tools: list("tools"),
    filesystem_read_roots: list("filesystem_read_roots"),
    filesystem_write_roots: list("filesystem_write_roots"),
    shell_workspace_only: record.shell_workspace_only,
  };
}

function resource(value: unknown, status = 502): ResourceDescriptor {
  const record = schemaRecord(value, status);
  const kind = asString(record.kind, "resource.kind", status) as ResourceKind;
  const availability = asString(record.availability, "resource.availability", status) as ResourceAvailability;
  const runtimeStatus = asString(record.runtime_status, "resource.runtime_status", status) as ResourceRuntimeStatus;
  if (!resourceKinds.has(kind) || !resourceAvailability.has(availability) || !resourceRuntimeStatuses.has(runtimeStatus) || !resourceOrigins.has(record.origin as ResourceOrigin) || typeof record.factory_selectable !== "boolean") {
    throw new LocalApiClientError("The local service returned an invalid Resource descriptor.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    resource_id: asString(record.resource_id, "resource.resource_id", status),
    kind,
    ...(record.component_class === undefined ? {} : { component_class: record.component_class === "composite" ? "composite" as const : "primitive" as const }),
    version: asString(record.version, "resource.version", status),
    reference: asString(record.reference, "resource.reference", status),
    name: asString(record.name, "resource.name", status),
    description: asText(record.description, "resource.description", status),
    origin: record.origin as ResourceOrigin,
    content_hash: asString(record.content_hash, "resource.content_hash", status),
    availability,
    factory_selectable: record.factory_selectable,
    runtime_status: runtimeStatus,
    required_permissions: resourcePermissions(record.required_permissions, status),
    tags: asArray(record.tags, "resource.tags", status).map((item) => asString(item, "resource tag", status)),
    spec: asRecord(record.spec, status) as ResourceDescriptor["spec"],
    ...(record.configuration_requirements === undefined ? {} : { configuration_requirements: asArray(record.configuration_requirements, "resource.configuration_requirements", status).map((value) => {
      const item = asRecord(value, status);
      if (typeof item.satisfied !== "boolean") throw new LocalApiClientError("Invalid resource requirement.", { status, code: "invalid_response" });
      return { code: asString(item.code, "requirement.code", status), message: asString(item.message, "requirement.message", status), satisfied: item.satisfied };
    }) }),
    ...(record.blocking_reasons === undefined ? {} : { blocking_reasons: asArray(record.blocking_reasons, "resource.blocking_reasons", status).map((value) => {
      const item = asRecord(value, status);
      return { code: asString(item.code, "reason.code", status), message: asString(item.message, "reason.message", status) };
    }) }),
    ...(record.dependencies === undefined ? {} : { dependencies: asArray(record.dependencies, "resource.dependencies", status) as NonNullable<ResourceDescriptor["dependencies"]> }),
    ...(record.compatibility === undefined ? {} : { compatibility: resourceCompatibility(record.compatibility, status) }),
  };
}

function resourceCompatibility(value: unknown, status: number): NonNullable<ResourceDescriptor["compatibility"]> {
  const item = asRecord(value, status);
  if (typeof item.network_verified !== "boolean") throw new LocalApiClientError("Invalid resource compatibility.", { status, code: "invalid_response" });
  return { scope: asString(item.scope, "compatibility.scope", status), execution: asString(item.execution, "compatibility.execution", status), network_verified: item.network_verified };
}

function listedResources(value: unknown, status = 502): ListResourcesResponse {
  const record = schemaRecord(value, status);
  const kinds = asArray(record.kinds, "resource.kinds", status).map((item) => {
    const kindRecord = asRecord(item, status);
    const kind = asString(kindRecord.kind, "resource kind", status) as ResourceKind;
    if (!resourceKinds.has(kind)) throw new LocalApiClientError("The local service returned an unknown Resource kind.", { status, code: "invalid_response" });
    return { kind, count: asNumber(kindRecord.count, `resource kind ${kind} count`, status) };
  });
  return { schema_version: LOCAL_API_SCHEMA_VERSION, resources: asArray(record.resources, "resources", status).map((item) => resource(item, status)), kinds };
}

const projectResourceScopes = new Set(["project", "used_unbound", "builtin"]);

function projectResource(value: unknown, status = 502): ProjectResourceDescriptor {
  const record = asRecord(value, status);
  const scope = asString(record.scope, "project_resource.scope", status);
  if (!projectResourceScopes.has(scope)) {
    throw new LocalApiClientError("The local service returned an invalid Project resource scope.", { status, code: "invalid_response" });
  }
  const bindingStatus = record.binding_status === undefined ? undefined : asString(record.binding_status, "project_resource.binding_status", status) as ProjectResourceBindingStatus;
  if (bindingStatus !== undefined && !new Set<ProjectResourceBindingStatus>(["current", "stale", "unbound", "builtin"]).has(bindingStatus)) {
    throw new LocalApiClientError("The local service returned an invalid Project resource binding status.", { status, code: "invalid_response" });
  }
  const bindingSource = record.binding_source === null ? null : asString(record.binding_source, "project_resource.binding_source", status);
  return {
    ...resource(record, status),
    scope: scope as ProjectResourceDescriptor["scope"],
    ...(bindingStatus === undefined ? {} : { binding_status: bindingStatus }),
    binding_source: bindingSource as ProjectResourceDescriptor["binding_source"],
    bound_content_hash: record.bound_content_hash === null ? null : asString(record.bound_content_hash, "project_resource.bound_content_hash", status),
    used_by: asArray(record.used_by, "project_resource.used_by", status).map((item) => {
      const usage = asRecord(item, status);
      const kind = asString(usage.kind, "project_resource.used_by.kind", status);
      if (kind !== "agent" && kind !== "workflow") throw new LocalApiClientError("The local service returned an invalid Project resource usage kind.", { status, code: "invalid_response" });
      return { kind, resource_id: asString(usage.resource_id, "project_resource.used_by.resource_id", status), name: asString(usage.name, "project_resource.used_by.name", status) };
    }),
  };
}

function projectResources(value: unknown, status = 502): ProjectResourcesResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    project_id: asString(record.project_id, "project_resources.project_id", status),
    resources: asArray(record.resources, "project_resources.resources", status).map((item) => projectResource(item, status)),
    missing_references: asArray(record.missing_references, "project_resources.missing_references", status).map((item) => asString(item, "project resource reference", status)),
    missing_bindings: record.missing_bindings === undefined ? [] : asArray(record.missing_bindings, "missing_bindings", status).map((item) => {
      const binding = asRecord(item, status);
      return {
        reference: asString(binding.reference, "binding.reference", status),
        content_hash: asString(binding.content_hash, "binding.content_hash", status),
        source: asString(binding.source, "binding.source", status),
        used_by: asArray(binding.used_by, "binding.used_by", status).map((usage) => {
          const value = asRecord(usage, status);
          const kind = asString(value.kind, "usage.kind", status);
          if (kind !== "agent" && kind !== "workflow") throw new LocalApiClientError("Invalid resource usage kind", { status, code: "invalid_response" });
          return { kind, resource_id: asString(value.resource_id, "usage.resource_id", status), name: asString(value.name, "usage.name", status) };
        }),
      };
    }),
    project_count: asNumber(record.project_count, "project_resources.project_count", status),
    used_count: asNumber(record.used_count, "project_resources.used_count", status),
    unbound_count: asNumber(record.unbound_count, "project_resources.unbound_count", status),
    builtin_count: asNumber(record.builtin_count, "project_resources.builtin_count", status),
    ...(record.stale_count === undefined ? {} : { stale_count: asNumber(record.stale_count, "project_resources.stale_count", status) }),
  };
}

function resourceDraft(value: unknown, status = 502): ResourceDraftResponse {
  const record = schemaRecord(value, status);
  if (record.executable !== false) {
    throw new LocalApiClientError("The local service returned an executable Resource Draft.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    draft_id: asString(record.draft_id, "resource_draft.draft_id", status),
    executable: false,
    resource: resource(record.resource, status),
  };
}

function approvedResourceDraft(value: unknown, status = 502): { schema_version: "1.0"; resource: ResourceDescriptor } {
  const record = schemaRecord(value, status);
  return { schema_version: LOCAL_API_SCHEMA_VERSION, resource: resource(record.resource, status) };
}

const pluginPackStates = new Set<PluginPackState>(["quarantined", "active", "disabled", "activation_failed"]);

function pluginPackSkill(value: unknown, status = 502): PluginPack["skills"][number] {
  const record = asRecord(value, status);
  return {
    path: asString(record.path, "plugin.skill.path", status),
    reference: asString(record.reference, "plugin.skill.reference", status),
    name: asString(record.name, "plugin.skill.name", status),
    description: asText(record.description, "plugin.skill.description", status),
    instruction: asText(record.instruction, "plugin.skill.instruction", status),
  };
}

function pluginPackMcpServer(value: unknown, status = 502): PluginPack["mcp_servers"][number] {
  const record = asRecord(value, status);
  const transport = asString(record.transport, "plugin.mcp.transport", status);
  if (transport !== "stdio" && transport !== "streamable_http") {
    throw new LocalApiClientError("The local service returned an invalid Plugin Pack MCP transport.", { status, code: "invalid_response" });
  }
  return {
    name: asString(record.name, "plugin.mcp.name", status),
    command: asText(record.command, "plugin.mcp.command", status),
    args: asArray(record.args, "plugin.mcp.args", status).map((item) => asString(item, "plugin.mcp.args", status)),
    env_names: Object.fromEntries(Object.entries(asRecord(record.env_names, status)).map(([key, item]) => [key, asString(item, "plugin.mcp.env_names", status)])),
    transport,
    url: record.url === null ? null : asString(record.url, "plugin.mcp.url", status),
    headers: Object.fromEntries(Object.entries(asRecord(record.headers, status)).map(([key, item]) => [key, asString(item, "plugin.mcp.headers", status)])),
    enabled: asBoolean(record.enabled, "plugin.mcp.enabled", status),
  };
}

function pluginPack(value: unknown, status = 502): PluginPack {
  const record = schemaRecord(value, status);
  const state = asString(record.state, "plugin.state", status) as PluginPackState;
  if (!pluginPackStates.has(state)) {
    throw new LocalApiClientError("The local service returned an invalid Plugin Pack state.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    plugin_id: asString(record.plugin_id, "plugin.plugin_id", status),
    name: asString(record.name, "plugin.name", status),
    description: asText(record.description, "plugin.description", status),
    version: asString(record.version, "plugin.version", status),
    license: record.license === null ? null : asString(record.license, "plugin.license", status),
    content_hash: asString(record.content_hash, "plugin.content_hash", status),
    state,
    skills: asArray(record.skills, "plugin.skills", status).map((item) => pluginPackSkill(item, status)),
    mcp_servers: asArray(record.mcp_servers, "plugin.mcp_servers", status).map((item) => pluginPackMcpServer(item, status)),
    skill_resources: asArray(record.skill_resources, "plugin.skill_resources", status).map((item) => asString(item, "plugin.skill_resources", status)),
    mcp_server_ids: asArray(record.mcp_server_ids, "plugin.mcp_server_ids", status).map((item) => asString(item, "plugin.mcp_server_ids", status)),
    activation_error: record.activation_error === null ? null : asText(record.activation_error, "plugin.activation_error", status),
  };
}

function listedPluginPacks(value: unknown, status = 502): ListPluginPacksResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    plugins: asArray(record.plugins, "plugins", status).map((item) => pluginPack(item, status)),
  };
}

function pluginTrash(value: unknown, status = 502): PluginPackTrash {
  const record = asRecord(value, status);
  return { ...pluginPack(record, status), trash_id: asString(record.trash_id, "plugin.trash_id", status) };
}

function listedPluginTrash(value: unknown, status = 502): ListPluginTrashResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    plugins: asArray(record.plugins, "plugin trash", status).map((item) => pluginTrash(item, status)),
  };
}

const workspaceTrashKinds = new Set<WorkspaceTrashKind>(["project", "agent", "workflow", "knowledge", "conversation", "plugin"]);

function workspaceTrashItem(value: unknown, status = 502): WorkspaceTrashItem {
  const record = asRecord(value, status);
  const kind = asString(record.kind, "trash.kind", status) as WorkspaceTrashKind;
  if (!workspaceTrashKinds.has(kind)) {
    throw new LocalApiClientError("The local service returned an invalid trash kind.", { status, code: "invalid_response" });
  }
  return {
    kind,
    id: asString(record.id, "trash.id", status),
    name: asString(record.name, "trash.name", status),
    project_id: record.project_id === null || record.project_id === undefined ? null : asString(record.project_id, "trash.project_id", status),
    project_name: record.project_name === null || record.project_name === undefined ? null : asString(record.project_name, "trash.project_name", status),
    removed_at: asString(record.removed_at, "trash.removed_at", status),
    expires_at: asString(record.expires_at, "trash.expires_at", status),
    restorable: asBoolean(record.restorable, "trash.restorable", status),
  };
}

function listedWorkspaceTrash(value: unknown, status = 502): ListWorkspaceTrashResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    retention_days: asNumber(record.retention_days, "trash.retention_days", status),
    items: asArray(record.items, "trash.items", status).map((item) => workspaceTrashItem(item, status)),
  };
}

function workspaceTrashMutation(value: unknown, status = 502): WorkspaceTrashMutationResponse {
  const record = schemaRecord(value, status);
  const kind = asString(record.kind, "trash.kind", status) as WorkspaceTrashKind;
  if (!workspaceTrashKinds.has(kind)) {
    throw new LocalApiClientError("The local service returned an invalid trash mutation kind.", { status, code: "invalid_response" });
  }
  const restored = record.restored === true;
  const deleted = record.deleted === true;
  if (!restored && !deleted) {
    throw new LocalApiClientError("The local service returned an invalid trash mutation.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    kind,
    id: asString(record.id, "trash.id", status),
    ...(restored ? { restored: true as const } : {}),
    ...(deleted ? { deleted: true as const } : {}),
  };
}

function uninstalledPluginPack(value: unknown, status = 502): PluginPackUninstallResponse {
  const record = schemaRecord(value, status);
  const plugin = pluginTrash(record.plugin, status);
  if (record.plugin && typeof record.plugin === "object" && (record.plugin as Record<string, unknown>).disposition !== "trashed") {
    throw new LocalApiClientError("The local service returned an invalid Plugin Pack uninstall result.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    plugin: { ...plugin, disposition: "trashed" },
  };
}

function pluginPackResponse(value: unknown, status = 502): PluginPackResponse {
  const record = schemaRecord(value, status);
  return { schema_version: LOCAL_API_SCHEMA_VERSION, plugin: pluginPack(record.plugin, status) };
}

const agentImportStates = new Set<AgentImportRecord["state"]>(["analyzed", "applied"]);
const agentImportKinds = new Set<AgentImportRecord["source_kind"]>(["yaml", "zip", "folder"]);
const agentImportFormats = new Set<AgentImportRecord["detected_format"]>(["generic_yaml", "veyra_agent_yaml"]);
const agentImportCapabilityStates = new Set<AgentImportRecord["capabilities"][number]["status"]>(["supported", "partial", "unsupported"]);

function agentImportCapability(value: unknown, status = 502): AgentImportRecord["capabilities"][number] {
  const record = asRecord(value, status);
  const capabilityStatus = asString(record.status, "agent_import.capability.status", status) as AgentImportRecord["capabilities"][number]["status"];
  if (!agentImportCapabilityStates.has(capabilityStatus)) {
    throw new LocalApiClientError("The local service returned an invalid Agent Import capability.", { status, code: "invalid_response" });
  }
  return {
    kind: asString(record.kind, "agent_import.capability.kind", status),
    original: asString(record.original, "agent_import.capability.original", status),
    status: capabilityStatus,
    reason: asText(record.reason, "agent_import.capability.reason", status),
    ...(record.reference === undefined ? {} : { reference: asString(record.reference, "agent_import.capability.reference", status) }),
    ...(record.included === undefined ? {} : { included: asBoolean(record.included, "agent_import.capability.included", status) }),
  };
}

function agentImportWarning(value: unknown, status = 502): AgentImportRecord["warnings"][number] {
  const record = asRecord(value, status);
  return {
    code: asString(record.code, "agent_import.warning.code", status),
    message: asText(record.message, "agent_import.warning.message", status),
    ...(record.path === undefined ? {} : { path: asString(record.path, "agent_import.warning.path", status) }),
  };
}

function agentImportPreview(value: unknown, status = 502): AgentImportRecord["preview"] {
  const record = asRecord(value, status);
  return {
    name: asString(record.name, "agent_import.preview.name", status),
    description: asText(record.description, "agent_import.preview.description", status),
    instructions: asText(record.instructions, "agent_import.preview.instructions", status),
    model: Object.fromEntries(Object.entries(asRecord(record.model, status)).map(([key, item]) => [key, asString(item, `agent_import.preview.model.${key}`, status)])),
    inputs: typedFields(record.inputs, "agent_import.preview.inputs", status),
    outputs: typedFields(record.outputs, "agent_import.preview.outputs", status),
    tools: asArray(record.tools, "agent_import.preview.tools", status).map((item) => asString(item, "agent_import.preview.tools", status)),
    skills: asArray(record.skills, "agent_import.preview.skills", status).map((item) => asString(item, "agent_import.preview.skills", status)),
    knowledge_files: asArray(record.knowledge_files, "agent_import.preview.knowledge_files", status).map((item) => asString(item, "agent_import.preview.knowledge_files", status)),
    workflow_present: asBoolean(record.workflow_present, "agent_import.preview.workflow_present", status),
    ...(record.source_path === undefined ? {} : { source_path: asString(record.source_path, "agent_import.preview.source_path", status) }),
  };
}

function agentImportRecord(value: unknown, status = 502): AgentImportRecord {
  const record = asRecord(value, status);
  if (record.schema_version !== "agent.import.v1") {
    throw new LocalApiClientError("The local service returned an incompatible Agent Import schema.", { status, code: "schema_mismatch" });
  }
  const state = asString(record.state, "agent_import.state", status) as AgentImportRecord["state"];
  const sourceKind = asString(record.source_kind, "agent_import.source_kind", status) as AgentImportRecord["source_kind"];
  const detectedFormat = asString(record.detected_format, "agent_import.detected_format", status) as AgentImportRecord["detected_format"];
  if (!agentImportStates.has(state) || !agentImportKinds.has(sourceKind) || !agentImportFormats.has(detectedFormat)) {
    throw new LocalApiClientError("The local service returned an invalid Agent Import state.", { status, code: "invalid_response" });
  }
  return {
    schema_version: "agent.import.v1",
    import_id: asString(record.import_id, "agent_import.import_id", status),
    state,
    source_kind: sourceKind,
    source_name: asString(record.source_name, "agent_import.source_name", status),
    source_path: asString(record.source_path, "agent_import.source_path", status),
    detected_format: detectedFormat,
    compatibility: asNumber(record.compatibility, "agent_import.compatibility", status),
    preview: agentImportPreview(record.preview, status),
    capabilities: asArray(record.capabilities, "agent_import.capabilities", status).map((item) => agentImportCapability(item, status)),
    warnings: asArray(record.warnings, "agent_import.warnings", status).map((item) => agentImportWarning(item, status)),
    generated_source: source(record.generated_source, status),
    manifest: asRecord(record.manifest, status) as AgentImportRecord["manifest"],
    ...(record.applied_agent === undefined ? {} : { applied_agent: createdAgent(record.applied_agent, status) }),
  };
}

function agentImportApplyResponse(value: unknown, status = 502): AgentImportApplyResponse {
  const record = asRecord(value, status);
  if (record.schema_version !== "agent.import.v1") {
    throw new LocalApiClientError("The local service returned an incompatible Agent Import schema.", { status, code: "schema_mismatch" });
  }
  return {
    schema_version: "agent.import.v1",
    import: agentImportRecord(record.import, status),
    agent: createdAgent(record.agent, status),
  };
}

function mcpServer(value: unknown, status = 502): McpServer {
  const record = asRecord(value, status);
  const transport = record.transport === undefined ? "stdio" : asString(record.transport, "mcp.transport", status);
  if (transport !== "stdio" && transport !== "streamable_http") {
    throw new LocalApiClientError("The local service returned an invalid MCP transport.", { status, code: "invalid_response" });
  }
  return {
    server_id: asString(record.server_id, "mcp.server_id", status),
    name: asString(record.name, "mcp.name", status),
    command: asString(record.command, "mcp.command", status),
    args: asArray(record.args, "mcp.args", status).map((item) => asString(item, "mcp.args", status)),
    env_names: Object.fromEntries(
      Object.entries(asRecord(record.env_names, status)).map(([key, item]) => [key, asString(item, "mcp.env_names", status)]),
    ),
    transport,
    url: record.url === undefined || record.url === null ? null : asString(record.url, "mcp.url", status),
    headers: Object.fromEntries(
      Object.entries(record.headers === undefined ? {} : asRecord(record.headers, status)).map(([key, item]) => [key, asString(item, "mcp.headers", status)]),
    ),
    enabled: asBoolean(record.enabled, "mcp.enabled", status),
    created_at: asString(record.created_at, "mcp.created_at", status),
    updated_at: asString(record.updated_at, "mcp.updated_at", status),
  };
}

function mcpServerReadiness(value: unknown, status = 502): McpServerReadiness {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    server_id: asString(record.server_id, "mcp readiness.server_id", status),
    ready: asBoolean(record.ready, "mcp readiness.ready", status),
    code: asString(record.code, "mcp readiness.code", status),
    detail: asText(record.detail, "mcp readiness.detail", status),
  };
}

function listedMcpServers(value: unknown, status = 502): ListMcpServersResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    servers: asArray(record.servers, "mcp.servers", status).map((item) => mcpServer(item, status)),
  };
}

function createdMcpServer(value: unknown, status = 502): { schema_version: "1.0"; server: McpServer } {
  const record = schemaRecord(value, status);
  return { schema_version: LOCAL_API_SCHEMA_VERSION, server: mcpServer(record.server, status) };
}

function discoveredMcpTools(value: unknown, status = 502): { schema_version: "1.0"; server_id: string; tools: ResourceDescriptor[] } {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    server_id: asString(record.server_id, "mcp.server_id", status),
    tools: asArray(record.tools, "mcp.tools", status).map((item) => resource(item, status)),
  };
}

function approvedMcpTool(value: unknown, status = 502): { schema_version: "1.0"; server_id: string; resource: ResourceDescriptor } {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    server_id: asString(record.server_id, "mcp.server_id", status),
    resource: resource(record.resource, status),
  };
}

function deletedMcpServer(value: unknown, status = 502): { schema_version: "1.0"; server_id: string; deleted: boolean } {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    server_id: asString(record.server_id, "mcp.server_id", status),
    deleted: asBoolean(record.deleted, "mcp.deleted", status),
  };
}

const workItemStatuses = new Set(["backlog", "ready", "running", "waiting", "done", "failed", "cancelled"]);

function workItem(value: unknown, status = 502): WorkItem {
  const record = schemaRecord(value, status);
  const itemStatus = asString(record.status, "work_item.status", status);
  if (!workItemStatuses.has(itemStatus)) {
    throw new LocalApiClientError("The local service returned an invalid work item status.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    work_item_id: asString(record.work_item_id, "work_item.work_item_id", status),
    project_id: asString(record.project_id, "work_item.project_id", status),
    title: asString(record.title, "work_item.title", status),
    description: asText(record.description, "work_item.description", status),
    agent_id: asString(record.agent_id, "work_item.agent_id", status),
    depends_on: asArray(record.depends_on, "work_item.depends_on", status).map((item) => asString(item, "work_item.depends_on", status)),
    inputs: asRecord(record.inputs, status) as JsonObject,
    status: itemStatus as WorkItem["status"],
    run_id: record.run_id === null ? null : asString(record.run_id, "work_item.run_id", status),
    ...(record.attempt_number === undefined ? {} : { attempt_number: asNumber(record.attempt_number, "work_item.attempt_number", status) }),
    ...(record.lease_expires_at === undefined ? {} : { lease_expires_at: record.lease_expires_at === null ? null : asString(record.lease_expires_at, "work_item.lease_expires_at", status) }),
    ...(record.failure_class === undefined ? {} : { failure_class: record.failure_class === null ? null : asString(record.failure_class, "work_item.failure_class", status) }),
    ...(record.stale === undefined ? {} : { stale: asBoolean(record.stale, "work_item.stale", status) }),
    ...(record.stale_for_seconds === undefined ? {} : { stale_for_seconds: asNumber(record.stale_for_seconds, "work_item.stale_for_seconds", status) }),
    ...(record.attempts === undefined ? {} : { attempts: asArray(record.attempts, "work_item.attempts", status).map((item) => workItemAttempt(item, status)) }),
    created_at: asString(record.created_at, "work_item.created_at", status),
    updated_at: asString(record.updated_at, "work_item.updated_at", status),
  };
}

function workItemAttempt(value: unknown, status = 502): WorkItemAttempt {
  const record = asRecord(value, status);
  return {
    attempt_id: asString(record.attempt_id, "work_item.attempt_id", status),
    attempt_number: asNumber(record.attempt_number, "work_item.attempt_number", status),
    run_id: record.run_id === null ? null : asString(record.run_id, "work_item.run_id", status),
    status: asString(record.status, "work_item.attempt_status", status),
    failure_class: record.failure_class === null ? null : asString(record.failure_class, "work_item.attempt_failure_class", status),
    claimed_at: asString(record.claimed_at, "work_item.claimed_at", status),
    started_at: record.started_at === null ? null : asString(record.started_at, "work_item.started_at", status),
    finished_at: record.finished_at === null ? null : asString(record.finished_at, "work_item.finished_at", status),
    created_at: asString(record.created_at, "work_item.attempt_created_at", status),
  };
}

function listedWorkItems(value: unknown, status = 502): ListWorkItemsResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    project_id: asString(record.project_id, "work_items.project_id", status),
    execution_plane: "local",
    work_items: asArray(record.work_items, "work_items", status).map((item) => workItem(item, status)),
  };
}

function parsedOrchestratorStatus(value: unknown, status = 502): OrchestratorStatus {
  const record = schemaRecord(value, status);
  if (record.execution_plane !== "local" || record.cloud_execution !== false) {
    throw new LocalApiClientError("The local service returned an invalid orchestrator plane.", { status, code: "invalid_response" });
  }
  const countsRecord = asRecord(record.counts, status);
  const counts = Object.fromEntries(
    [...workItemStatuses].map((key) => [key, asNumber(countsRecord[key] ?? 0, `orchestrator.counts.${key}`, status)]),
  ) as OrchestratorStatus["counts"];
  const limits = asRecord(record.limits, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    execution_plane: "local",
    cloud_execution: false,
    counts,
    active: asArray(record.active, "orchestrator.active", status).map((item) => workItem(item, status)),
    stale_count: asNumber(record.stale_count, "orchestrator.stale_count", status),
    limits: {
      global_concurrency: asNumber(limits.global_concurrency, "orchestrator.limits.global_concurrency", status),
      per_project_concurrency: asNumber(limits.per_project_concurrency, "orchestrator.limits.per_project_concurrency", status),
    },
  };
}

const factoryStates = new Set<FactorySessionState>(["collecting", "ready", "generating", "review", "missing_capability", "completed", "abandoned"]);
const factoryRunAvailability = new Set<FactoryRunAvailability>(["ready", "requires_configuration", "design_only", "unavailable"]);

function factoryMessage(value: unknown, status = 502): FactoryMessage {
  const record = schemaRecord(value, status);
  const role = asString(record.role, "factory.message.role", status);
  if (role !== "user" && role !== "assistant") {
    throw new LocalApiClientError("The local service returned an unknown Factory message role.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    message_id: asString(record.message_id, "factory.message_id", status),
    sequence: asNumber(record.sequence, "factory.message.sequence", status),
    role,
    content: asText(record.content, "factory.message.content", status),
    created_at: asString(record.created_at, "factory.message.created_at", status),
  };
}

function factoryPlanItem(value: unknown, status = 502): FactoryResourcePlanItem {
  const record = asRecord(value, status);
  const kind = asString(record.kind, "factory.plan.kind", status) as ResourceKind;
  const availability = asString(record.availability, "factory.plan.availability", status) as ResourceAvailability;
  const runtimeStatus = asString(record.runtime_status, "factory.plan.runtime_status", status) as ResourceRuntimeStatus;
  if (!resourceKinds.has(kind) || !resourceAvailability.has(availability) || !resourceRuntimeStatuses.has(runtimeStatus)) {
    throw new LocalApiClientError("The local service returned an invalid Factory resource plan item.", { status, code: "invalid_response" });
  }
  return { reference: asString(record.reference, "factory.plan.reference", status), kind, availability, runtime_status: runtimeStatus };
}

function factoryMissing(value: unknown, status = 502): FactoryMissingCapability {
  const record = asRecord(value, status);
  const proposal = asRecord(record.proposal, status);
  const action = asString(proposal.action, "factory.missing.proposal.action", status);
  if (proposal.executable !== false) {
    throw new LocalApiClientError("The local service returned an invalid missing-capability proposal.", { status, code: "invalid_response" });
  }
  if (action !== "quarantined_resource_draft" && action !== "missing_capability") {
    throw new LocalApiClientError("The local service returned an invalid missing-capability proposal.", { status, code: "invalid_response" });
  }
  return {
    kind: asString(record.kind, "factory.missing.kind", status),
    reference: asString(record.reference, "factory.missing.reference", status),
    reason: asString(record.reason, "factory.missing.reason", status),
    proposal: { action: "quarantined_resource_draft", executable: false },
  };
}

function factoryCandidate(value: unknown, status: number): FactorySession["candidate"] {
  if (value === null || value === undefined) return null;
  const record = asRecord(value, status);
  const name = asText(record.name, "factory.candidate.name", status).trim();
  if (!name) return null;
  const slug = record.slug === undefined || record.slug === null ? undefined : asText(record.slug, "factory.candidate.slug", status);
  return slug ? { name, slug } : { name };
}

function factorySession(value: unknown, status = 502): FactorySession {
  const record = schemaRecord(value, status);
  const state = asString(record.state, "factory.state", status) as FactorySessionState;
  const runAvailability = asString(record.run_availability, "factory.run_availability", status) as FactoryRunAvailability;
  if (!factoryStates.has(state) || !factoryRunAvailability.has(runAvailability) || record.executes_drafts !== false) {
    throw new LocalApiClientError("The local service returned an invalid Factory session.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    session_id: asString(record.session_id, "factory.session_id", status),
    project_id: asString(record.project_id, "factory.project_id", status),
    state,
    ready: asBoolean(record.ready, "factory.ready", status),
    next_prompt: asText(record.next_prompt, "factory.next_prompt", status),
    resource_plan: asArray(record.resource_plan, "factory.resource_plan", status).map((item) => factoryPlanItem(item, status)),
    blueprint: record.blueprint === null ? null : asJsonValue(asRecord(record.blueprint, status), "factory.blueprint", status) as JsonObject,
    diagnostics: asArray(record.diagnostics, "factory.diagnostics", status).map((item) => asString(item, "factory.diagnostic", status)),
    missing_capabilities: asArray(record.missing_capabilities, "factory.missing_capabilities", status).map((item) => factoryMissing(item, status)),
    candidate: factoryCandidate(record.candidate, status),
    run_availability: runAvailability,
    executes_drafts: false,
    revision: asNumber(record.revision, "factory.revision", status),
    created_at: asString(record.created_at, "factory.created_at", status),
    updated_at: asString(record.updated_at, "factory.updated_at", status),
    messages: asArray(record.messages, "factory.messages", status).map((item) => factoryMessage(item, status)),
  };
}

function factoryStatus(value: unknown, status = 502): FactoryStatus {
  const record = schemaRecord(value, status);
  const effort = asString(record.reasoning_effort, "factory.reasoning_effort", status);
  if ((effort !== "low" && effort !== "high" && effort !== "max") || record.executes_drafts !== false) {
    throw new LocalApiClientError("The local service returned an invalid Factory status.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    configured: asBoolean(record.configured, "factory.configured", status),
    model_id: asString(record.model_id, "factory.model_id", status),
    model_base_url: asString(record.model_base_url, "factory.model_base_url", status),
    model_api_key_env: asString(record.model_api_key_env, "factory.model_api_key_env", status),
    reasoning_effort: effort,
    repair_attempts: asNumber(record.repair_attempts, "factory.repair_attempts", status),
    executes_drafts: false,
    capability_profile: providerCapabilityProfile(record.capability_profile, status),
  };
}

const providerFamilies = new Set<ProviderCapabilityProfile["provider_family"]>(["moonshot", "openai_compatible"]);
const structuredOutputs = new Set<ProviderCapabilityProfile["structured_output"]>(["json_schema", "json_object"]);
const schemaFlavors = new Set<ProviderCapabilityProfile["schema_flavor"]>(["moonshot_mfjs", "none"]);
const schemaProfiles = new Set<ProviderCapabilityProfile["schema_profile"]>(["mfjs", "openai_json_schema", "unknown"]);
const endpointKinds = new Set<ProviderCapabilityProfile["endpoint_kind"]>(["chat_completions", "responses", "compatible_chat"]);
const profileSources = new Set<ProviderCapabilityProfile["source"]>(["static_known", "probe", "fallback"]);
const profileStatuses = new Set<ProviderCapabilityProfile["status"]>(["known", "unknown", "stale", "failed", "inconclusive"]);
const capabilitySupports = new Set<ProviderCapabilityProfile["strict_json_schema_support"]>(["supported", "unsupported", "unknown"]);

function optionalProfileText(value: unknown, field: string, status = 502): string | null {
  if (value === null) return null;
  return asString(value, field, status);
}

function providerCapabilitySummary(value: unknown, status = 502): ProviderCapabilityProfile["summary"] {
  const record = asRecord(value, status);
  return {
    provider: asString(record.provider, "factory.capability_profile.summary.provider", status),
    model: asString(record.model, "factory.capability_profile.summary.model", status),
    structured_output: asString(record.structured_output, "factory.capability_profile.summary.structured_output", status),
    schema_profile: asString(record.schema_profile, "factory.capability_profile.summary.schema_profile", status),
    json_object_fallback: asString(record.json_object_fallback, "factory.capability_profile.summary.json_object_fallback", status),
    status: asString(record.status, "factory.capability_profile.summary.status", status),
    checked_at: asText(record.checked_at, "factory.capability_profile.summary.checked_at", status),
    error_class: asText(record.error_class, "factory.capability_profile.summary.error_class", status),
  };
}

function providerCapabilityProfile(value: unknown, status = 502): ProviderCapabilityProfile {
  const record = schemaRecord(value, status);
  const family = asString(record.provider_family, "factory.capability_profile.provider_family", status);
  const output = asString(record.structured_output, "factory.capability_profile.structured_output", status);
  const flavor = asString(record.schema_flavor, "factory.capability_profile.schema_flavor", status);
  const schemaProfile = asString(record.schema_profile, "factory.capability_profile.schema_profile", status);
  const endpointKind = asString(record.endpoint_kind, "factory.capability_profile.endpoint_kind", status);
  const source = asString(record.source, "factory.capability_profile.source", status);
  const profileStatus = asString(record.status, "factory.capability_profile.status", status);
  const strictSupport = asString(record.strict_json_schema_support, "factory.capability_profile.strict_json_schema_support", status);
  const jsonObjectSupport = asString(record.json_object_support, "factory.capability_profile.json_object_support", status);
  if (
    !providerFamilies.has(family as ProviderCapabilityProfile["provider_family"])
    || !structuredOutputs.has(output as ProviderCapabilityProfile["structured_output"])
    || !schemaFlavors.has(flavor as ProviderCapabilityProfile["schema_flavor"])
    || !schemaProfiles.has(schemaProfile as ProviderCapabilityProfile["schema_profile"])
    || !endpointKinds.has(endpointKind as ProviderCapabilityProfile["endpoint_kind"])
    || !profileSources.has(source as ProviderCapabilityProfile["source"])
    || !profileStatuses.has(profileStatus as ProviderCapabilityProfile["status"])
    || !capabilitySupports.has(strictSupport as ProviderCapabilityProfile["strict_json_schema_support"])
    || !capabilitySupports.has(jsonObjectSupport as ProviderCapabilityProfile["json_object_support"])
  ) {
    throw new LocalApiClientError("The local service returned an invalid Factory capability profile.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    provider_id: asString(record.provider_id, "factory.capability_profile.provider_id", status),
    provider_family: family as ProviderCapabilityProfile["provider_family"],
    model: asString(record.model, "factory.capability_profile.model", status),
    endpoint_kind: endpointKind as ProviderCapabilityProfile["endpoint_kind"],
    base_url_fingerprint: asString(record.base_url_fingerprint, "factory.capability_profile.base_url_fingerprint", status),
    structured_output: output as ProviderCapabilityProfile["structured_output"],
    schema_flavor: flavor as ProviderCapabilityProfile["schema_flavor"],
    schema_profile: schemaProfile as ProviderCapabilityProfile["schema_profile"],
    strict_json_schema: asBoolean(record.strict_json_schema, "factory.capability_profile.strict_json_schema", status),
    json_object_fallback: asBoolean(record.json_object_fallback, "factory.capability_profile.json_object_fallback", status),
    reasoning_effort: asBoolean(record.reasoning_effort, "factory.capability_profile.reasoning_effort", status),
    supports_reasoning_effort: asBoolean(record.supports_reasoning_effort, "factory.capability_profile.supports_reasoning_effort", status),
    strict_json_schema_support: strictSupport as ProviderCapabilityProfile["strict_json_schema_support"],
    json_object_support: jsonObjectSupport as ProviderCapabilityProfile["json_object_support"],
    source: source as ProviderCapabilityProfile["source"],
    status: profileStatus as ProviderCapabilityProfile["status"],
    checked_at: optionalProfileText(record.checked_at, "factory.capability_profile.checked_at", status),
    probe_version: asString(record.probe_version, "factory.capability_profile.probe_version", status),
    probed: asBoolean(record.probed, "factory.capability_profile.probed", status),
    error_class: optionalProfileText(record.error_class, "factory.capability_profile.error_class", status),
    summary: providerCapabilitySummary(record.summary, status),
  };
}

function runtimeStatus(value: unknown, status = 502): RuntimeStatus {
  const record = schemaRecord(value, status);
  const effort = asString(record.reasoning_effort, "runtime.reasoning_effort", status);
  if (effort !== "low" && effort !== "high" && effort !== "max") {
    throw new LocalApiClientError("The local service returned an invalid Runtime status.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    configured: asBoolean(record.configured, "runtime.configured", status),
    model_id: asString(record.model_id, "runtime.model_id", status),
    model_base_url: asString(record.model_base_url, "runtime.model_base_url", status),
    model_api_key_env: asString(record.model_api_key_env, "runtime.model_api_key_env", status),
    reasoning_effort: effort,
    allow_process_environment_key: asBoolean(record.allow_process_environment_key, "runtime.allow_process_environment_key", status),
    user_provided_only: asBoolean(record.user_provided_only, "runtime.user_provided_only", status),
    ...(record.modalities === undefined ? {} : { modalities: runtimeModelCapabilities(record.modalities, status) }),
  };
}

function runtimeProfileValidation(value: unknown, status = 502): RuntimeProfileValidation {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    valid: asBoolean(record.valid, "runtime profile validation.valid", status),
    configured: asBoolean(record.configured, "runtime profile validation.configured", status),
    model_available: asBoolean(record.model_available, "runtime profile validation.model_available", status),
    provider: asString(record.provider, "runtime profile validation.provider", status),
    base_url: asString(record.base_url, "runtime profile validation.base_url", status),
    model_id: asString(record.model_id, "runtime profile validation.model_id", status),
    api_key_env: asString(record.api_key_env, "runtime profile validation.api_key_env", status),
    code: asString(record.code, "runtime profile validation.code", status),
    message: asText(record.message, "runtime profile validation.message", status),
  };
}

function runtimeReadiness(value: unknown, status = 502): RuntimeReadiness {
  const record = schemaRecord(value, status);
  const profileSource = asString(record.profile_source, "runtime readiness profile_source", status);
  if (profileSource !== "agent" && profileSource !== "project" && profileSource !== "default") {
    throw new LocalApiClientError("The local service returned an invalid Runtime profile source.", { status, code: "invalid_response" });
  }
  const model = asRecord(record.model, status);
  const modelRequired = asBoolean(model.required, "runtime readiness model.required", status);
  const modelConfigured = asBoolean(model.configured, "runtime readiness model.configured", status);
  const checks = asArray(record.checks, "runtime readiness checks", status).map((item) => runtimeReadinessCheck(item, status));
  const toolChecks = asArray(record.tool_checks, "runtime readiness tool_checks", status).map((item) => runtimeToolReadiness(item, status));
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    project_id: asString(record.project_id, "runtime readiness project_id", status),
    agent_id: asString(record.agent_id, "runtime readiness agent_id", status),
    ready: asBoolean(record.ready, "runtime readiness ready", status),
    profile_source: profileSource,
    model: {
      required: modelRequired,
      configured: modelConfigured,
      model_id: asString(model.model_id, "runtime readiness model_id", status),
      model_base_url: asString(model.model_base_url, "runtime readiness model_base_url", status),
      model_api_key_env: asString(model.model_api_key_env, "runtime readiness model_api_key_env", status),
      ...(model.modalities === undefined ? {} : { modalities: runtimeModelCapabilities(model.modalities, status) }),
    },
    dependency_summary: validationDependencySummary(record.dependency_summary, status),
    dependencies: asArray(record.dependencies, "runtime readiness dependencies", status).map((item) => validationDependency(item, status)),
    tool_checks: toolChecks,
    checks,
  };
}

function runtimeReadinessCheck(value: unknown, status = 502): RuntimeReadinessCheck {
  const record = asRecord(value, status);
  const id = asString(record.id, "runtime readiness check id", status);
  if (id !== "dependencies" && id !== "model" && id !== "modalities" && id !== "tools") {
    throw new LocalApiClientError("The local service returned an invalid Runtime readiness check.", { status, code: "invalid_response" });
  }
  return {
    id,
    ready: asBoolean(record.ready, "runtime readiness check ready", status),
    code: asString(record.code, "runtime readiness check code", status),
    detail: asText(record.detail, "runtime readiness check detail", status),
  };
}

function workflowRuntimeReadiness(value: unknown, status = 502): WorkflowRuntimeReadiness {
  const record = schemaRecord(value, status);
  const checks = asArray(record.checks, "workflow runtime readiness checks", status).map((item) => workflowRuntimeReadinessCheck(item, status));
  const calls = asArray(record.calls, "workflow runtime readiness calls", status).map((value) => {
    const call = asRecord(value, status);
    const model = asRecord(call.model, status);
    const gaps = asArray(call.permission_gaps, "workflow runtime permission gaps", status).map((value) => {
      const gap = asRecord(value, status);
      return {
        field: asString(gap.field, "workflow runtime permission field", status),
        missing: asArray(gap.missing, "workflow runtime permission values", status).map((item, index) => asJsonValue(item, `workflow runtime permission value ${index}`, status)),
      };
    });
    return {
      node_id: asString(call.node_id, "workflow runtime call node_id", status),
      agent_id: asString(call.agent_id, "workflow runtime call agent_id", status),
      version_id: asString(call.version_id, "workflow runtime call version_id", status),
      source_hash: asString(call.source_hash, "workflow runtime call source_hash", status),
      ready: asBoolean(call.ready, "workflow runtime call ready", status),
      detail: asText(call.detail, "workflow runtime call detail", status),
      permission_gaps: gaps,
      model: {
        required: asBoolean(model.required, "workflow runtime call model.required", status),
        configured: asBoolean(model.configured, "workflow runtime call model.configured", status),
        model_id: asString(model.model_id, "workflow runtime call model_id", status),
        model_base_url: asString(model.model_base_url, "workflow runtime call model_base_url", status),
        model_api_key_env: asString(model.model_api_key_env, "workflow runtime call model_api_key_env", status),
      },
      dependency_summary: validationDependencySummary(call.dependency_summary, status),
      checks: asArray(call.checks, "workflow runtime call checks", status).map((item) => runtimeReadinessCheck(item, status)),
      tool_checks: asArray(call.tool_checks, "workflow runtime call tool_checks", status).map((item) => runtimeToolReadiness(item, status)),
    };
  });
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    project_id: asString(record.project_id, "workflow runtime readiness project_id", status),
    workflow_id: asString(record.workflow_id, "workflow runtime readiness workflow_id", status),
    ready: asBoolean(record.ready, "workflow runtime readiness ready", status),
    calls,
    checks,
  };
}

function workflowRuntimeReadinessCheck(value: unknown, status = 502): WorkflowRuntimeReadinessCheck {
  const record = asRecord(value, status);
  const id = asString(record.id, "workflow runtime readiness check id", status);
  if (id !== "agent_calls" && id !== "permissions" && id !== "limits") {
    throw new LocalApiClientError("The local service returned an invalid Workflow Runtime readiness check.", { status, code: "invalid_response" });
  }
  return {
    id,
    ready: asBoolean(record.ready, "workflow runtime readiness check ready", status),
    code: asString(record.code, "workflow runtime readiness check code", status),
    detail: asText(record.detail, "workflow runtime readiness check detail", status),
  };
}

function runtimeToolReadiness(value: unknown, status = 502): RuntimeToolReadiness {
  const record = asRecord(value, status);
  return {
    node_id: asString(record.node_id, "runtime readiness tool node_id", status),
    reference: asString(record.reference, "runtime readiness tool reference", status),
    ready: asBoolean(record.ready, "runtime readiness tool ready", status),
    code: asString(record.code, "runtime readiness tool code", status),
    detail: asText(record.detail, "runtime readiness tool detail", status),
  };
}

function capabilityState(value: unknown, field: string, status = 502): "supported" | "unsupported" | "unknown" {
  const state = asString(value, field, status);
  if (state !== "supported" && state !== "unsupported" && state !== "unknown") {
    throw new LocalApiClientError(`The local service returned an invalid ${field}.`, { status, code: "invalid_response" });
  }
  return state;
}

function runtimeModelCapabilities(value: unknown, status = 502): RuntimeModelCapabilities {
  const record = asRecord(value, status);
  const source = asString(record.source, "runtime.modalities.source", status);
  if (source !== "static_profile" && source !== "unknown") {
    throw new LocalApiClientError("The local service returned an invalid Runtime modality source.", { status, code: "invalid_response" });
  }
  return {
    provider: asString(record.provider, "runtime.modalities.provider", status),
    model_id: asString(record.model_id, "runtime.modalities.model_id", status),
    text_input: capabilityState(record.text_input, "runtime.modalities.text_input", status),
    image_input: capabilityState(record.image_input, "runtime.modalities.image_input", status),
    structured_json_output: capabilityState(record.structured_json_output, "runtime.modalities.structured_json_output", status),
    source,
  };
}

function artifactRecord(value: unknown, status = 502): ArtifactRecord {
  const record = asRecord(value, status);
  const sourceKind = asString(record.source_kind, "artifact.source_kind", status);
  if (sourceKind !== "upload" && sourceKind !== "runtime_output" && sourceKind !== "project_file_import") {
    throw new LocalApiClientError("The local service returned an invalid artifact source.", { status, code: "invalid_response" });
  }
  const payload: ArtifactRecord = {
    kind: "artifact",
    artifact_id: asString(record.artifact_id, "artifact.artifact_id", status),
    project_id: asString(record.project_id, "artifact.project_id", status),
    sha256: asString(record.sha256, "artifact.sha256", status),
    filename: asString(record.filename, "artifact.filename", status),
    media_type: asString(record.media_type, "artifact.media_type", status),
    size_bytes: asNumber(record.size_bytes, "artifact.size_bytes", status),
    storage_ref: asString(record.storage_ref, "artifact.storage_ref", status),
    source_kind: sourceKind,
    created_at: asString(record.created_at, "artifact.created_at", status),
  };
  if (record.run_id !== undefined && record.run_id !== null) {
    payload.run_id = asString(record.run_id, "artifact.run_id", status);
  }
  return payload;
}

function secretStatus(value: unknown, status = 502): SecretStatus {
  const record = schemaRecord(value, status);
  const source = asString(record.source, "secret.source", status);
  if (source !== "keychain" && source !== "environment" && source !== "missing") {
    throw new LocalApiClientError("The local service returned an invalid Secret status.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    secret_ref: asString(record.secret_ref, "secret.secret_ref", status),
    env_name: asString(record.env_name, "secret.env_name", status),
    configured: asBoolean(record.configured, "secret.configured", status),
    source,
  };
}

function appliedFactoryDraft(value: unknown, status = 502): ApplyFactoryDraftResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    session: factorySession(record.session, status),
    agent: createdAgent(record.agent, status),
  };
}

function runtimeEvent(value: unknown, status = 502): NonNullable<AgentRunResponse["events"]>[number] {
  const record = schemaRecord(value, status);
  const kind = asString(record.kind, "event.kind", status) as NonNullable<AgentRunResponse["events"]>[number]["kind"];
  if (!runtimeEventKinds.has(kind)) {
    throw new LocalApiClientError("The local service returned an unknown runtime event.", { status, code: "invalid_response" });
  }
  const payload = asJsonValue(asRecord(record.payload, status), "event.payload", status) as JsonObject;
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    event_id: asString(record.event_id, "event_id", status),
    run_id: asString(record.run_id, "run_id", status),
    sequence: asNumber(record.sequence, "event.sequence", status),
    kind,
    node_id: record.node_id === null ? null : asString(record.node_id, "event.node_id", status),
    payload,
    timestamp: asString(record.timestamp, "event.timestamp", status),
  };
}

function commonRun(value: unknown, status = 502): Omit<AgentRunResponse, "agent_id"> {
  const record = schemaRecord(value, status);
  const runStatus = asString(record.status, "run.status", status);
  if (runStatus !== "running" && runStatus !== "waiting" && runStatus !== "verified" && runStatus !== "unverified" && runStatus !== "failed" && runStatus !== "interrupted" && runStatus !== "cancelled") {
    throw new LocalApiClientError("The local service returned an unknown run status.", { status, code: "invalid_response" });
  }
  const result = record.result === null ? null : asJsonValue(asRecord(record.result, status), "run.result", status) as JsonObject;
  let error: AgentRunResponse["error"] = null;
  if (record.error !== null) {
    const rawError = asRecord(record.error, status);
    error = { code: asString(rawError.code, "run.error.code", status), message: asString(rawError.message, "run.error.message", status) };
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    run_id: asString(record.run_id, "run_id", status),
    project_id: asString(record.project_id, "project_id", status),
    version_id: asString(record.version_id, "version_id", status),
    ...(record.conversation_id === undefined
      ? {}
      : { conversation_id: record.conversation_id === null ? null : asString(record.conversation_id, "conversation_id", status) }),
    status: runStatus,
    result,
    error,
    created_at: asString(record.created_at, "created_at", status),
    finished_at: record.finished_at === null ? null : asString(record.finished_at, "finished_at", status),
    ...(record.events === undefined ? {} : { events: asArray(record.events, "run.events", status).map((item) => runtimeEvent(item, status)) }),
  };
}

function agentRun(value: unknown, status = 502): AgentRunResponse {
  const record = schemaRecord(value, status);
  return { ...commonRun(record, status), agent_id: asString(record.agent_id, "agent_id", status) };
}

function workflowRun(value: unknown, status = 502): WorkflowRunResponse {
  const record = schemaRecord(value, status);
  const workflowId = asString(record.workflow_id, "workflow_id", status);
  const common = commonRun(record, status);
  const waiting = record.waiting === null ? null : asRecord(record.waiting, status);
  return { ...common, workflow_id: workflowId,
    waiting: waiting ? { kind: asString(waiting.kind, "waiting.kind", status), node_id: asString(waiting.node_id, "waiting.node_id", status), prompt: asText(waiting.prompt, "waiting.prompt", status) } : null,
    children: asArray(record.children, "children", status).map((value) => {
      const child = asRecord(value, status);
      const childStatus = child.status === null ? null : asString(child.status, "child.status", status);
      if (childStatus !== null && !["running", "waiting", "verified", "unverified", "failed", "interrupted", "cancelled"].includes(childStatus)) throw new LocalApiClientError("Invalid child run status", { status, code: "invalid_response" });
      return { node_id: asString(child.node_id, "child.node_id", status), agent_id: asString(child.agent_id, "child.agent_id", status), version_id: asString(child.version_id, "child.version_id", status), child_run_id: child.child_run_id === null ? null : asString(child.child_run_id, "child.run_id", status), status: childStatus as WorkflowRunResponse["children"][number]["status"] };
    }),
  };
}

function listedAgentRuns(value: unknown, status = 502): ListAgentRunsResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    runs: asArray(record.runs, "runs", status).map((item) => agentRun(item, status)),
  };
}

function conversationMessage(value: unknown, status = 502): AgentConversation["messages"][number] {
  const record = schemaRecord(value, status);
  const role = asString(record.role, "conversation.message.role", status);
  if (role !== "user" && role !== "assistant") {
    throw new LocalApiClientError("The local service returned an invalid conversation role.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    message_id: asString(record.message_id, "conversation.message.message_id", status),
    conversation_id: asString(record.conversation_id, "conversation.message.conversation_id", status),
    sequence: asNumber(record.sequence, "conversation.message.sequence", status),
    role,
    content: asText(record.content, "conversation.message.content", status),
    run_id: record.run_id === null ? null : asString(record.run_id, "conversation.message.run_id", status),
    created_at: asString(record.created_at, "conversation.message.created_at", status),
  };
}

function conversationSummary(value: unknown, status = 502): AgentConversationSummary {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    conversation_id: asString(record.conversation_id, "conversation.conversation_id", status),
    project_id: asString(record.project_id, "conversation.project_id", status),
    agent_id: asString(record.agent_id, "conversation.agent_id", status),
    title: asText(record.title, "conversation.title", status),
    message_count: asNumber(record.message_count, "conversation.message_count", status),
    created_at: asString(record.created_at, "conversation.created_at", status),
    updated_at: asString(record.updated_at, "conversation.updated_at", status),
  };
}

function listedAgentConversations(value: unknown, status = 502): ListAgentConversationsResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    conversations: asArray(record.conversations, "conversations", status).map((item) => conversationSummary(item, status)),
  };
}

function agentConversation(value: unknown, status = 502): AgentConversation {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    conversation_id: asString(record.conversation_id, "conversation.conversation_id", status),
    project_id: asString(record.project_id, "conversation.project_id", status),
    agent_id: asString(record.agent_id, "conversation.agent_id", status),
    title: asText(record.title, "conversation.title", status),
    created_at: asString(record.created_at, "conversation.created_at", status),
    updated_at: asString(record.updated_at, "conversation.updated_at", status),
    messages: asArray(record.messages, "conversation.messages", status).map((item) => conversationMessage(item, status)),
  };
}

function exported(value: unknown, status = 502): ExportResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    agent_id: asString(record.agent_id, "agent_id", status),
    source: source(record.source, status),
    source_text: asString(record.source_text, "source_text", status),
    file_hash: asString(record.file_hash, "file_hash", status),
    ...(record.community_origin === undefined ? {} : {
      community_origin: communityAgentOrigin(record.community_origin, status),
    }),
  };
}

function fallbackHttpError(status: number): LocalApiClientError {
  return new LocalApiClientError(
    status >= 500
      ? "The local service failed while handling this request. Restart the desktop sidecar and retry."
      : `The local service rejected this request (${status}).`,
    { status, code: status >= 500 ? "local_internal_error" : "http_error" },
  );
}

function fastapiDetailMessage(value: unknown): string | undefined {
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  if (!Array.isArray(value)) {
    return undefined;
  }
  const parts = value.flatMap((item) => {
    if (typeof item === "string" && item.trim()) {
      return [item];
    }
    if (item && typeof item === "object" && "msg" in item) {
      const message = (item as { msg?: unknown }).msg;
      return typeof message === "string" && message.trim() ? [message] : [];
    }
    return [];
  });
  return parts.length > 0 ? parts.join("; ") : undefined;
}

function errorEnvelope(value: unknown, status: number): LocalApiClientError {
  if (value == null || typeof value !== "object" || Array.isArray(value)) {
    return fallbackHttpError(status);
  }
  const record = value as Record<string, unknown>;
  if (typeof record.code === "string" && typeof record.message === "string") {
    let details: Record<string, string> | undefined;
    if (record.details !== undefined) {
      try {
        const rawDetails = asRecord(record.details, status);
        details = {};
        for (const [key, detail] of Object.entries(rawDetails)) {
          if (typeof detail !== "string") {
            return new LocalApiClientError("The local service returned invalid error details.", {
              status,
              code: "invalid_error_envelope",
            });
          }
          details[key] = detail;
        }
      } catch {
        return new LocalApiClientError("The local service returned invalid error details.", {
          status,
          code: "invalid_error_envelope",
        });
      }
    }
    return new LocalApiClientError(record.message, {
      status,
      code: record.code,
      requestId: typeof record.request_id === "string" ? record.request_id : undefined,
      details,
    });
  }
  const detail = fastapiDetailMessage(record.detail);
  if (detail) {
    return new LocalApiClientError(detail, { status, code: "http_error" });
  }
  return fallbackHttpError(status);
}

function parseSseChunk(chunk: string): { event: string; data: unknown } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of chunk.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}

async function readBuilderTurnStream(
  response: Response,
  onEvent?: (event: BuilderOperationEvent) => void,
): Promise<BuilderConversationSnapshot> {
  const reader = response.body?.getReader();
  if (!reader) {
    throw new LocalApiClientError("The local service returned an incomplete Builder turn.", { status: 502, code: "invalid_response" });
  }
  const decoder = new TextDecoder();
  let buffer = "";
  let snapshot: BuilderConversationSnapshot | undefined;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const parsed = parseSseChunk(part);
      if (!parsed || typeof parsed.data !== "object" || parsed.data === null) continue;
      if (parsed.event === "builder.event") {
        onEvent?.(builderOperationEvent(parsed.data, 200));
      } else if (parsed.event === "builder.snapshot") {
        snapshot = builderConversationSnapshot(parsed.data, 200);
      } else if (parsed.event === "builder.error") {
        const record = parsed.data as Record<string, unknown>;
        const status = typeof record.status === "number" ? record.status : 502;
        throw errorEnvelope(parsed.data, status);
      }
    }
  }
  if (!snapshot) {
    throw new LocalApiClientError("The local service returned an incomplete Builder turn.", { status: 502, code: "invalid_response" });
  }
  return snapshot;
}

export class LocalApiClient {
  private readonly baseUrl: string;
  private readonly fetcher: typeof fetch;

  constructor(options: LocalApiClientOptions = {}) {
    this.baseUrl = options.baseUrl?.trim() || configuredBaseUrl();
    this.fetcher = options.fetcher ?? globalThis.fetch.bind(globalThis);
  }

  listProjects(): Promise<ListProjectsResponse> {
    return this.request("projects", listProjects);
  }

  createProject(input: CreateProjectRequest): Promise<ProjectSummaryResponse> {
    return this.request("projects", projectSummary, {
      method: "POST",
      body: input,
    });
  }

  openProject(input: OpenProjectRequest): Promise<ProjectSummaryResponse> {
    return this.request("projects/open", projectSummary, {
      method: "POST",
      body: input,
    });
  }

  selectDirectory(): Promise<SelectDirectoryResponse> {
    return this.request("system/select-directory", selectedDirectory, {
      method: "POST",
      body: {},
      headers: { "X-Veyra-Desktop-Intent": "select-directory" },
    });
  }

  selectArchive(): Promise<SelectArchiveResponse> {
    return this.request("system/select-archive", selectedArchive, {
      method: "POST",
      body: {},
      headers: { "X-Veyra-Desktop-Intent": "select-archive" },
    });
  }

  revealProject(projectId: string): Promise<RevealProjectResponse> {
    return this.request("system/reveal-project", revealedProject, {
      method: "POST",
      body: { project_id: projectId },
      headers: { "X-Veyra-Desktop-Intent": "reveal-project" },
    });
  }

  getProject(projectId: string): Promise<ProjectSummaryResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}`, projectSummary);
  }

  updateProject(projectId: string, input: UpdateProjectRequest): Promise<ProjectSummaryResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}`, projectSummary, {
      method: "PATCH",
      body: input,
    });
  }

  deleteProject(projectId: string): Promise<DeleteProjectResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}`, deletedProject, { method: "DELETE" });
  }

  updateAgent(projectId: string, agentId: string, input: UpdateAgentRequest): Promise<ProjectSummaryResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}`, projectSummary, {
      method: "PATCH",
      body: input,
    });
  }

  deleteAgent(projectId: string, agentId: string): Promise<DeleteAgentResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}`,
      deletedAgent,
      { method: "DELETE" },
    );
  }

  listAgentTemplates(projectId: string): Promise<ListAgentTemplatesResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}/agent-templates`, agentTemplates);
  }

  createAgent(projectId: string, input: CreateAgentRequest): Promise<CreatedAgentResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}/agents`, createdAgent, {
      method: "POST",
      body: input,
    });
  }

  createWorkflow(projectId: string, input: CreateWorkflowRequest = {}): Promise<CreatedWorkflowResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}/workflows`, createdWorkflow, {
      method: "POST",
      body: input,
    });
  }

  deleteWorkflow(projectId: string, workflowId: string): Promise<DeleteWorkflowResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/workflows/${encodeURIComponent(workflowId)}`,
      deletedWorkflow,
      { method: "DELETE" },
    );
  }

  createKnowledge(projectId: string, input: CreateKnowledgeRequest = {}): Promise<KnowledgeDocumentResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}/knowledge`, knowledgeDocument, {
      method: "POST",
      body: input,
    });
  }

  ingestKnowledge(projectId: string, file: File): Promise<KnowledgeDocumentResponse> {
    const formData = new FormData();
    formData.append("file", file);
    return this.request(`projects/${encodeURIComponent(projectId)}/knowledge/ingest`, knowledgeDocument, { method: "POST", formData });
  }

  getKnowledge(projectId: string, knowledgeId: string): Promise<KnowledgeDocumentResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/knowledge/${encodeURIComponent(knowledgeId)}`,
      knowledgeDocument,
    );
  }

  getKnowledgeChunk(projectId: string, knowledgeId: string, chunkId: string, sourceFileHash: string): Promise<KnowledgeChunkResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/knowledge/${encodeURIComponent(knowledgeId)}/chunks/${encodeURIComponent(chunkId)}?source_file_hash=${encodeURIComponent(sourceFileHash)}`,
      (value, status) => {
        const record = schemaRecord(value, status);
        return {
          schema_version: LOCAL_API_SCHEMA_VERSION,
          project_id: asString(record.project_id, "project_id", status),
          reference: asString(record.reference, "reference", status),
          source_file_hash: asString(record.source_file_hash, "source_file_hash", status),
          chunk_id: asString(record.chunk_id, "chunk_id", status),
          line_start: asNumber(record.line_start, "line_start", status),
          line_end: asNumber(record.line_end, "line_end", status),
          text: asText(record.text, "text", status),
        };
      },
    );
  }

  buildKnowledgeIndex(projectId: string, knowledgeId: string): Promise<KnowledgeDocumentResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/knowledge/${encodeURIComponent(knowledgeId)}/index`,
      knowledgeDocument,
      { method: "POST" },
    );
  }

  updateKnowledge(projectId: string, knowledgeId: string, input: UpdateKnowledgeRequest): Promise<KnowledgeDocumentResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/knowledge/${encodeURIComponent(knowledgeId)}`,
      knowledgeDocument,
      { method: "PATCH", body: input },
    );
  }

  deleteKnowledge(projectId: string, knowledgeId: string): Promise<DeleteKnowledgeResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/knowledge/${encodeURIComponent(knowledgeId)}`,
      deletedKnowledge,
      { method: "DELETE" },
    );
  }

  importAgent(projectId: string, input: { file: File; name?: string; description?: string; parent_agent_id?: string; community_origin?: CommunityAgentOrigin }): Promise<CreatedAgentResponse> {
    const formData = new FormData();
    formData.append("file", input.file);
    if (input.name) formData.append("name", input.name);
    if (input.description) formData.append("description", input.description);
    if (input.parent_agent_id) formData.append("parent_agent_id", input.parent_agent_id);
    if (input.community_origin) {
      formData.append("community_owner_handle", input.community_origin.owner_handle);
      formData.append("community_slug", input.community_origin.slug);
      formData.append("community_version", input.community_origin.version);
      formData.append("community_source_hash", input.community_origin.source_hash);
    }
    return this.request(`projects/${encodeURIComponent(projectId)}/agents/import`, createdAgent, {
      method: "POST",
      formData,
    });
  }

  analyzeAgentImport(file: File): Promise<AgentImportRecord> {
    const formData = new FormData();
    formData.append("file", file);
    return this.request("agent-imports", agentImportRecord, { method: "POST", formData });
  }

  analyzeAgentImportFolder(path: string): Promise<AgentImportRecord> {
    const formData = new FormData();
    formData.append("path", path);
    return this.request("agent-imports", agentImportRecord, { method: "POST", formData });
  }

  getAgentImport(importId: string): Promise<AgentImportRecord> {
    return this.request(`agent-imports/${encodeURIComponent(importId)}`, agentImportRecord);
  }

  applyAgentImport(importId: string, input: AgentImportApplyRequest): Promise<AgentImportApplyResponse> {
    return this.request(`agent-imports/${encodeURIComponent(importId)}/apply`, agentImportApplyResponse, { method: "POST", body: input });
  }

  importProject(file: File): Promise<ProjectSummaryResponse> {
    const formData = new FormData();
    formData.append("file", file);
    return this.request("projects/import", projectSummary, {
      method: "POST",
      formData,
    });
  }

  importProjectFromPath(input: ImportProjectPathRequest): Promise<ProjectSummaryResponse> {
    return this.request("projects/import-path", projectSummary, {
      method: "POST",
      body: input,
    });
  }

  exportProject(projectId: string): Promise<Blob> {
    return this.requestBlob(`projects/${encodeURIComponent(projectId)}/export`);
  }

  listProjectFiles(projectId: string): Promise<ProjectFilesResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}/files`, projectFiles);
  }

  getProjectFile(projectId: string, path: string): Promise<ProjectFileContentResponse> {
    const query = new URLSearchParams({ path });
    return this.request(
      `projects/${encodeURIComponent(projectId)}/files/content?${query.toString()}`,
      projectFileContent,
    );
  }

  listAgents(projectId: string): Promise<ListAgentsResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}/agents`, listAgents);
  }

  getDraft(projectId: string, agentId: string): Promise<DraftResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/draft`,
      draft,
    );
  }

  saveDraft(
    projectId: string,
    agentId: string,
    input: SaveDraftRequest,
    options: { etag: string; idempotencyKey?: string },
  ): Promise<SaveDraftResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/draft`,
      savedDraft,
      {
        method: "PATCH",
        body: input,
        ifMatch: options.etag,
        idempotencyKey: options.idempotencyKey,
        requireIdempotencyKey: true,
      },
    );
  }

  reloadDraft(projectId: string, agentId: string): Promise<DraftResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/draft/reload`,
      draft,
      { method: "POST" },
    );
  }

  listAgentVersions(projectId: string, agentId: string): Promise<ListAgentVersionsResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/versions`, agentVersions);
  }

  listWorkflowVersions(projectId: string, workflowId: string): Promise<ListWorkflowVersionsResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}/workflows/${encodeURIComponent(workflowId)}/versions`, workflowVersions);
  }

  getWorkflowDraft(projectId: string, workflowId: string): Promise<WorkflowDraftResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/workflows/${encodeURIComponent(workflowId)}/draft`,
      workflowDraft,
    );
  }

  saveWorkflowDraft(
    projectId: string,
    workflowId: string,
    input: SaveWorkflowDraftRequest,
    options: { etag: string; idempotencyKey?: string },
  ): Promise<SaveWorkflowDraftResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/workflows/${encodeURIComponent(workflowId)}/draft`,
      savedWorkflowDraft,
      {
        method: "PATCH",
        body: input,
        ifMatch: options.etag,
        idempotencyKey: options.idempotencyKey,
        requireIdempotencyKey: true,
      },
    );
  }

  reloadWorkflowDraft(projectId: string, workflowId: string): Promise<WorkflowDraftResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/workflows/${encodeURIComponent(workflowId)}/draft/reload`,
      workflowDraft,
      { method: "POST" },
    );
  }

  validateWorkflow(projectId: string, workflowId: string): Promise<ValidateResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/workflows/${encodeURIComponent(workflowId)}/validate`,
      validated,
      { method: "POST" },
    );
  }

  commitWorkflow(
    projectId: string,
    workflowId: string,
    options: { expectedRevision: number; etag: string; idempotencyKey?: string },
  ): Promise<CommitResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/workflows/${encodeURIComponent(workflowId)}/commit`,
      committed,
      {
        method: "POST",
        body: { expected_revision: options.expectedRevision },
        ifMatch: options.etag,
        idempotencyKey: options.idempotencyKey,
        requireIdempotencyKey: true,
      },
    );
  }

  validate(projectId: string, agentId: string): Promise<ValidateResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/validate`,
      validated,
      { method: "POST" },
    );
  }

  commit(
    projectId: string,
    agentId: string,
    options: { expectedRevision: number; etag: string; idempotencyKey?: string },
  ): Promise<CommitResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/commit`,
      committed,
      {
        method: "POST",
        body: { expected_revision: options.expectedRevision },
        ifMatch: options.etag,
        idempotencyKey: options.idempotencyKey,
        requireIdempotencyKey: true,
      },
    );
  }

  listComponents(): Promise<ListComponentsResponse> {
    return this.request("components", listedComponents);
  }

  listResources(filters: ListResourceFilters = {}): Promise<ListResourcesResponse> {
    const params = new URLSearchParams();
    if (filters.kind) params.set("kind", filters.kind);
    if (filters.availability) params.set("availability", filters.availability);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return this.request(`resources${suffix}`, listedResources);
  }

  listProjectResources(projectId: string): Promise<ProjectResourcesResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}/resources`, projectResources);
  }

  addProjectResource(projectId: string, input: AddProjectResourceRequest): Promise<ProjectResourcesResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}/resources`, projectResources, { method: "POST", body: input });
  }

  removeProjectResource(projectId: string, resourceId: string, version: string): Promise<ProjectResourcesResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}/resources/${encodeURIComponent(resourceId)}/versions/${encodeURIComponent(version)}`, projectResources, { method: "DELETE" });
  }

  getResource(resourceId: string, version: string): Promise<ResourceDescriptor> {
    return this.request(`resources/${encodeURIComponent(resourceId)}/versions/${encodeURIComponent(version)}`, resource);
  }

  listPluginPacks(): Promise<ListPluginPacksResponse> {
    return this.request("plugins", listedPluginPacks);
  }

  listPluginTrash(): Promise<ListPluginTrashResponse> {
    return this.request("plugins/trash", listedPluginTrash);
  }

  importPluginPack(file: File): Promise<PluginPackResponse> {
    const formData = new FormData();
    formData.append("file", file);
    return this.request("plugins/import", pluginPackResponse, { method: "POST", formData });
  }

  activatePluginPack(pluginId: string, version: string, confirm = true): Promise<PluginPackResponse> {
    return this.request(
      `plugins/${encodeURIComponent(pluginId)}/versions/${encodeURIComponent(version)}/activate`,
      pluginPackResponse,
      { method: "POST", body: { confirm } },
    );
  }

  disablePluginPack(pluginId: string, version: string, confirm = true): Promise<PluginPackResponse> {
    return this.request(
      `plugins/${encodeURIComponent(pluginId)}/versions/${encodeURIComponent(version)}/disable`,
      pluginPackResponse,
      { method: "POST", body: { confirm } },
    );
  }

  uninstallPluginPack(pluginId: string, version: string, confirm = true): Promise<PluginPackUninstallResponse> {
    return this.request(
      `plugins/${encodeURIComponent(pluginId)}/versions/${encodeURIComponent(version)}/uninstall`,
      uninstalledPluginPack,
      { method: "POST", body: { confirm } },
    );
  }

  restorePluginPack(trashId: string, confirm = true): Promise<PluginPackResponse> {
    return this.request(
      `plugins/trash/${encodeURIComponent(trashId)}/restore`,
      pluginPackResponse,
      { method: "POST", body: { confirm } },
    );
  }

  downloadPluginPack(pluginId: string, version: string): Promise<Blob> {
    return this.requestBlob(`plugins/${encodeURIComponent(pluginId)}/versions/${encodeURIComponent(version)}/download`);
  }

  factoryStatus(): Promise<FactoryStatus> {
    return this.request("factory/status", factoryStatus);
  }

  probeFactoryCapabilities(): Promise<FactoryStatus> {
    return this.request("factory/capability-probe", factoryStatus, { method: "POST" });
  }

  runtimeStatus(): Promise<RuntimeStatus> {
    return this.request("runtime/status", runtimeStatus);
  }

  validateRuntimeProfile(profile: RuntimeApiProfileInput): Promise<RuntimeProfileValidation> {
    return this.request("runtime/profile/validate", runtimeProfileValidation, {
      method: "POST",
      body: { profile },
    });
  }

  runtimeReadiness(projectId: string, agentId: string): Promise<RuntimeReadiness> {
    return this.request(`projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/runtime-readiness`, runtimeReadiness);
  }

  uploadArtifact(projectId: string, file: File): Promise<ArtifactRecord> {
    const formData = new FormData();
    formData.append("file", file);
    return this.request(`projects/${encodeURIComponent(projectId)}/artifacts`, artifactRecord, { method: "POST", formData });
  }

  getArtifact(projectId: string, artifactId: string): Promise<ArtifactRecord> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}`,
      artifactRecord,
    );
  }

  artifactContent(projectId: string, artifactId: string): Promise<Blob> {
    return this.requestBlob(
      `projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/content`,
    );
  }

  workflowRuntimeReadiness(projectId: string, workflowId: string): Promise<WorkflowRuntimeReadiness> {
    return this.request(`projects/${encodeURIComponent(projectId)}/workflows/${encodeURIComponent(workflowId)}/runtime-readiness`, workflowRuntimeReadiness);
  }

  getSecretStatus(secretRef: string): Promise<SecretStatus> {
    return this.request(`secrets/${encodeURIComponent(secretRef)}`, secretStatus);
  }

  setSecret(secretRef: string, value: string): Promise<SecretStatus> {
    return this.request(`secrets/${encodeURIComponent(secretRef)}`, secretStatus, {
      method: "PUT",
      body: { value },
    });
  }

  deleteSecret(secretRef: string): Promise<SecretStatus> {
    return this.request(`secrets/${encodeURIComponent(secretRef)}`, secretStatus, { method: "DELETE" });
  }

  getProjectRuntimeProfile(projectId: string): Promise<RuntimeProfileResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/runtime-profile`,
      runtimeProfileResponse,
    );
  }

  setProjectRuntimeProfile(
    projectId: string,
    profile: RuntimeApiProfileInput | null,
  ): Promise<RuntimeProfileResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/runtime-profile`,
      runtimeProfileResponse,
      { method: "PATCH", body: { profile } },
    );
  }

  getAgentRuntimeProfile(
    projectId: string,
    agentId: string,
  ): Promise<RuntimeProfileResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/runtime-profile`,
      runtimeProfileResponse,
    );
  }

  setAgentRuntimeProfile(
    projectId: string,
    agentId: string,
    profile: RuntimeApiProfileInput | null,
  ): Promise<RuntimeProfileResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/runtime-profile`,
      runtimeProfileResponse,
      {
        method: "PATCH",
        body: { profile },
      },
    );
  }

  resolveBuilderIntent(projectId: string, input: BuilderResolveRequest): Promise<BuilderResolution> {
    return this.request(`projects/${encodeURIComponent(projectId)}/builder/resolve`, builderResolution, { method: "POST", body: input });
  }

  submitBuilderTurn(
    projectId: string,
    input: BuilderTurnRequest,
    options: { onEvent?: (event: BuilderOperationEvent) => void } = {},
  ): Promise<BuilderConversationSnapshot> {
    return this.submitBuilderTurnStream(projectId, input, options.onEvent);
  }

  getBuilderConversation(projectId: string, conversationId: string): Promise<BuilderConversationSnapshot> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/builder/conversations/${encodeURIComponent(conversationId)}`,
      builderConversationSnapshot,
    );
  }

  recordBuilderConversation(projectId: string, conversationId: string, input: BuilderConversationRecordRequest): Promise<BuilderConversationSnapshot> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/builder/conversations/${encodeURIComponent(conversationId)}/records`,
      builderConversationSnapshot,
      { method: "POST", body: input },
    );
  }

  renameBuilderConversation(projectId: string, conversationId: string, input: BuilderConversationRenameRequest): Promise<BuilderConversationSnapshot> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/builder/conversations/${encodeURIComponent(conversationId)}`,
      builderConversationSnapshot,
      { method: "PATCH", body: input },
    );
  }

  deleteBuilderConversation(projectId: string, conversationId: string): Promise<BuilderConversationDeleted> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/builder/conversations/${encodeURIComponent(conversationId)}`,
      builderConversationDeleted,
      { method: "DELETE" },
    );
  }

  listBuilderActivity(projectId?: string, limit?: number): Promise<BuilderActivityResponse> {
    const query = limit == null ? "" : `?${new URLSearchParams({ limit: String(limit) })}`;
    const path = projectId
      ? `projects/${encodeURIComponent(projectId)}/builder/activity${query}`
      : `builder/activity${query}`;
    return this.request(path, builderActivityResponse);
  }

  listWorkspaceTrash(): Promise<ListWorkspaceTrashResponse> {
    return this.request("trash", listedWorkspaceTrash);
  }

  restoreWorkspaceTrash(kind: WorkspaceTrashKind, itemId: string, confirm = true): Promise<WorkspaceTrashMutationResponse> {
    return this.request(
      `trash/${encodeURIComponent(kind)}/${encodeURIComponent(itemId)}/restore`,
      workspaceTrashMutation,
      { method: "POST", body: { confirm } },
    );
  }

  purgeWorkspaceTrash(kind: WorkspaceTrashKind, itemId: string, confirm = true): Promise<WorkspaceTrashMutationResponse> {
    return this.request(
      `trash/${encodeURIComponent(kind)}/${encodeURIComponent(itemId)}/purge`,
      workspaceTrashMutation,
      { method: "POST", body: { confirm } },
    );
  }

  startBuilderTestRun(projectId: string, conversationId: string, input: BuilderTestRunRequest): Promise<BuilderConversationSnapshot> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/builder/conversations/${encodeURIComponent(conversationId)}/test-runs`,
      builderConversationSnapshot,
      { method: "POST", body: input },
    );
  }

  commandBuilderTestRun(projectId: string, conversationId: string, operationId: string, input: BuilderTestRunCommandRequest): Promise<BuilderConversationSnapshot> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/builder/conversations/${encodeURIComponent(conversationId)}/operations/${encodeURIComponent(operationId)}/test-commands`,
      builderConversationSnapshot,
      { method: "POST", body: input },
    );
  }

  proposeBuilderTestRepair(projectId: string, conversationId: string, operationId: string, input: BuilderTestRepairRequest = { locale: "en" }): Promise<BuilderConversationSnapshot> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/builder/conversations/${encodeURIComponent(conversationId)}/operations/${encodeURIComponent(operationId)}/test-repair`,
      builderConversationSnapshot,
      { method: "POST", body: input },
    );
  }

  createEditProposal(projectId: string, input: CreateEditProposalRequest): Promise<EditProposal> {
    return this.request(`projects/${encodeURIComponent(projectId)}/edit-proposals`, editProposal, { method: "POST", body: input });
  }

  createKnowledgeBindingProposal(projectId: string, input: CreateKnowledgeBindingRequest): Promise<EditProposal> {
    return this.request(`projects/${encodeURIComponent(projectId)}/edit-proposals/knowledge-binding`, editProposal, { method: "POST", body: input });
  }

  createResourceBindingProposal(projectId: string, input: CreateResourceBindingRequest): Promise<EditProposal> {
    return this.request(`projects/${encodeURIComponent(projectId)}/edit-proposals/resource-binding`, editProposal, { method: "POST", body: input });
  }

  createValidationRepairProposal(projectId: string, input: CreateValidationRepairRequest): Promise<EditProposal> {
    return this.request(`projects/${encodeURIComponent(projectId)}/edit-proposals/validation-repair`, editProposal, { method: "POST", body: input });
  }

  listEditProposals(projectId: string, kind: EditTargetKind, targetId: string): Promise<ListEditProposalsResponse> {
    const query = new URLSearchParams({ target_kind: kind, target_id: targetId });
    return this.request(`projects/${encodeURIComponent(projectId)}/edit-proposals?${query}`, (value, status) => {
      const record = schemaRecord(value, status);
      return { schema_version: LOCAL_API_SCHEMA_VERSION, proposals: asArray(record.proposals, "proposals", status).map((item) => editProposal(item, status)) };
    });
  }

  commandEditProposal(projectId: string, proposalId: string, input: { command: EditProposalCommand; confirm: boolean }): Promise<EditProposal> {
    return this.request(`projects/${encodeURIComponent(projectId)}/edit-proposals/${encodeURIComponent(proposalId)}/commands`, editProposal, { method: "POST", body: input });
  }

  createFactorySession(projectId: string, input: { goal?: string } = {}): Promise<FactorySession> {
    return this.request(`projects/${encodeURIComponent(projectId)}/factory/sessions`, factorySession, { method: "POST", body: input });
  }

  getFactorySession(projectId: string, sessionId: string): Promise<FactorySession> {
    return this.request(`projects/${encodeURIComponent(projectId)}/factory/sessions/${encodeURIComponent(sessionId)}`, factorySession);
  }

  addFactoryMessage(projectId: string, sessionId: string, content: string): Promise<FactorySession> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/factory/sessions/${encodeURIComponent(sessionId)}/messages`,
      factorySession,
      { method: "POST", body: { content } },
    );
  }

  generateFactoryBlueprint(projectId: string, sessionId: string): Promise<FactorySession> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/factory/sessions/${encodeURIComponent(sessionId)}/generate`,
      factorySession,
      { method: "POST" },
    );
  }

  applyFactoryDraft(
    projectId: string,
    sessionId: string,
    input: { confirm: boolean; name?: string; description?: string; parent_agent_id?: string },
  ): Promise<ApplyFactoryDraftResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/factory/sessions/${encodeURIComponent(sessionId)}/apply-draft`,
      appliedFactoryDraft,
      { method: "POST", body: input },
    );
  }

  createResourceDraft(input: {
    confirm: boolean;
    kind: string;
    requested_reference: string;
    name?: string;
    description?: string;
    instruction?: string;
  }): Promise<ResourceDraftResponse> {
    return this.request("resources/drafts", resourceDraft, { method: "POST", body: input });
  }

  approveResourceDraft(resourceId: string, version: string, instruction: string): Promise<{ schema_version: "1.0"; resource: ResourceDescriptor }> {
    return this.request(
      `resources/${encodeURIComponent(resourceId)}/versions/${encodeURIComponent(version)}/approve`,
      approvedResourceDraft,
      { method: "POST", body: { instruction } },
    );
  }

  listMcpServers(): Promise<ListMcpServersResponse> {
    return this.request("mcp/servers", listedMcpServers);
  }

  createMcpServer(input: CreateMcpServerRequest): Promise<{ schema_version: "1.0"; server: McpServer }> {
    return this.request("mcp/servers", createdMcpServer, { method: "POST", body: input });
  }

  importMcpServers(input: ImportMcpServersRequest): Promise<ImportMcpServersResponse> {
    return this.request("mcp/servers/import", listedMcpServers, { method: "POST", body: input });
  }

  updateMcpServer(serverId: string, input: UpdateMcpServerRequest): Promise<{ schema_version: "1.0"; server: McpServer }> {
    return this.request(`mcp/servers/${encodeURIComponent(serverId)}`, createdMcpServer, { method: "PATCH", body: input });
  }

  discoverMcpServer(serverId: string): Promise<{ schema_version: "1.0"; server_id: string; tools: ResourceDescriptor[] }> {
    return this.request(`mcp/servers/${encodeURIComponent(serverId)}/discover`, discoveredMcpTools, { method: "POST" });
  }

  mcpServerReadiness(serverId: string): Promise<McpServerReadiness> {
    return this.request(`mcp/servers/${encodeURIComponent(serverId)}/readiness`, mcpServerReadiness);
  }

  approveMcpTool(serverId: string, resourceId: string, version: string): Promise<{ schema_version: "1.0"; server_id: string; resource: ResourceDescriptor }> {
    return this.request(
      `mcp/servers/${encodeURIComponent(serverId)}/tools/${encodeURIComponent(resourceId)}/versions/${encodeURIComponent(version)}/approve`,
      approvedMcpTool,
      { method: "POST" },
    );
  }

  deleteMcpServer(serverId: string): Promise<{ schema_version: "1.0"; server_id: string; deleted: boolean }> {
    return this.request(`mcp/servers/${encodeURIComponent(serverId)}`, deletedMcpServer, { method: "DELETE" });
  }

  orchestratorStatus(): Promise<OrchestratorStatus> {
    return this.request("orchestrator/status", parsedOrchestratorStatus);
  }

  listWorkItems(projectId: string): Promise<ListWorkItemsResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}/work-items`, listedWorkItems);
  }

  createWorkItem(
    projectId: string,
    input: { title: string; agent_id: string; description?: string; depends_on?: string[]; inputs?: JsonObject },
  ): Promise<WorkItem> {
    return this.request(`projects/${encodeURIComponent(projectId)}/work-items`, workItem, { method: "POST", body: input });
  }

  dispatchWorkItem(workItemId: string): Promise<WorkItem> {
    return this.request(`work-items/${encodeURIComponent(workItemId)}/dispatch`, workItem, { method: "POST" });
  }

  retryWorkItem(workItemId: string): Promise<WorkItem> {
    return this.request(`work-items/${encodeURIComponent(workItemId)}/retry`, workItem, { method: "POST" });
  }

  cancelWorkItem(workItemId: string): Promise<WorkItem> {
    return this.request(`work-items/${encodeURIComponent(workItemId)}/cancel`, workItem, { method: "POST" });
  }

  recoverWorkItem(workItemId: string): Promise<WorkItem> {
    return this.request(`work-items/${encodeURIComponent(workItemId)}/recover`, workItem, { method: "POST" });
  }

  runWorkflow(projectId: string, workflowId: string, input: StartAgentRunRequest): Promise<WorkflowRunResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}/workflows/${encodeURIComponent(workflowId)}/run`, workflowRun, { method: "POST", body: input, requireIdempotencyKey: true });
  }
  getWorkflowRun(projectId: string, workflowId: string, runId: string): Promise<WorkflowRunResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}/workflows/${encodeURIComponent(workflowId)}/runs/${encodeURIComponent(runId)}`, workflowRun);
  }
  listWorkflowRuns(projectId: string, workflowId: string): Promise<{ schema_version: "1.0"; runs: WorkflowRunResponse[] }> {
    return this.request(`projects/${encodeURIComponent(projectId)}/workflows/${encodeURIComponent(workflowId)}/runs`, (value, status) => { const record = schemaRecord(value, status); return { schema_version: "1.0", runs: asArray(record.runs, "runs", status).map((item) => workflowRun(item, status)) }; });
  }
  commandWorkflowRun(projectId: string, workflowId: string, runId: string, input: { command: "approve" | "reject" | "stop" }): Promise<WorkflowRunResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}/workflows/${encodeURIComponent(workflowId)}/runs/${encodeURIComponent(runId)}/commands`, workflowRun, { method: "POST", body: input, requireIdempotencyKey: true });
  }

  runAgent(
    projectId: string,
    agentId: string,
    input: StartAgentRunRequest,
    options: { idempotencyKey?: string } = {},
  ): Promise<AgentRunResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/run`,
      agentRun,
      {
        method: "POST",
        body: input,
        idempotencyKey: options.idempotencyKey,
        requireIdempotencyKey: true,
      },
    );
  }

  listAgentRuns(projectId: string, agentId: string): Promise<ListAgentRunsResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/runs`,
      listedAgentRuns,
    );
  }

  listAgentConversations(projectId: string, agentId: string): Promise<ListAgentConversationsResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/conversations`,
      listedAgentConversations,
    );
  }

  createAgentConversation(projectId: string, agentId: string, input: CreateAgentConversationRequest = {}): Promise<AgentConversation> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/conversations`,
      agentConversation,
      { method: "POST", body: input },
    );
  }

  getAgentConversation(projectId: string, agentId: string, conversationId: string): Promise<AgentConversation> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/conversations/${encodeURIComponent(conversationId)}`,
      agentConversation,
    );
  }

  getAgentRun(projectId: string, agentId: string, runId: string): Promise<AgentRunResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/runs/${encodeURIComponent(runId)}`,
      agentRun,
    );
  }

  commandAgentRun(
    projectId: string,
    agentId: string,
    runId: string,
    input: RunCommandRequest,
    options: { idempotencyKey?: string } = {},
  ): Promise<AgentRunResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/runs/${encodeURIComponent(runId)}/commands`,
      agentRun,
      {
        method: "POST",
        body: input,
        idempotencyKey: options.idempotencyKey,
        requireIdempotencyKey: true,
      },
    );
  }

  watchAgentRunEvents(
    projectId: string,
    agentId: string,
    runId: string,
    handlers: {
      onEvent: (event: RuntimeEvent) => void;
      onDone?: (status: AgentRunResponse["status"]) => void;
      onError?: (error: Error) => void;
    },
    options: { after?: number } = {},
  ): () => void {
    const after = options.after ?? 0;
    const url = `${apiUrl(
      this.baseUrl,
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/runs/${encodeURIComponent(runId)}/events`,
    )}?after=${encodeURIComponent(String(after))}`;
    const source = new EventSource(url, { withCredentials: true });
    let closed = false;
    const close = () => {
      closed = true;
      source.close();
    };
    source.addEventListener("runtime", (event) => {
      try {
        handlers.onEvent(runtimeEvent(JSON.parse(event.data)));
      } catch (cause) {
        handlers.onError?.(cause instanceof Error ? cause : new LocalApiClientError("The local service returned an invalid runtime event.", { status: 502, code: "invalid_response" }));
      }
    });
    source.addEventListener("done", (event) => {
      try {
        const payload = JSON.parse(event.data) as { status?: AgentRunResponse["status"] };
        if (payload.status) handlers.onDone?.(payload.status);
      } catch (cause) {
        handlers.onError?.(cause instanceof Error ? cause : new LocalApiClientError("The local service returned an invalid stream status.", { status: 502, code: "invalid_response" }));
      } finally {
        close();
      }
    });
    source.onerror = () => {
      if (closed) return;
      close();
      handlers.onError?.(new LocalApiClientError("The local run event stream closed unexpectedly.", { status: 0, code: "unavailable" }));
    };
    return close;
  }

  exportAgent(projectId: string, agentId: string): Promise<ExportResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/export`,
      exported,
    );
  }

  private async submitBuilderTurnStream(
    projectId: string,
    input: BuilderTurnRequest,
    onEvent?: (event: BuilderOperationEvent) => void,
  ): Promise<BuilderConversationSnapshot> {
    const path = `projects/${encodeURIComponent(projectId)}/builder/turns`;
    let response: Response;
    try {
      response = await this.fetcher(apiUrl(this.baseUrl, path), {
        method: "POST",
        headers: {
          Accept: "text/event-stream, application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify(input),
        credentials: "include",
      });
    } catch {
      throw new LocalApiClientError(
        "The local service is unavailable. Check that the desktop sidecar is running.",
        { status: 0, code: "unavailable" },
      );
    }
    const type = response.headers.get("content-type") ?? "";
    if (type.includes("text/event-stream") && response.body) {
      return readBuilderTurnStream(response, onEvent);
    }
    const payload = await response.json().catch(() => undefined);
    if (!response.ok) throw errorEnvelope(payload, response.status);
    return builderConversationSnapshot(payload, response.status);
  }

  private async request<T>(
    path: string,
    parse: (value: unknown, status?: number) => T,
    options: RequestOptions = {},
  ): Promise<T> {
    const method = options.method ?? "GET";
    const headers: Record<string, string> = { Accept: "application/json" };
    if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    if (options.ifMatch !== undefined) {
      headers["If-Match"] = options.ifMatch;
    }
    if (options.requireIdempotencyKey) {
      headers["Idempotency-Key"] = options.idempotencyKey ?? newUuidV7();
    }
    Object.assign(headers, options.headers);

    let response: Response;
    try {
      response = await this.fetcher(apiUrl(this.baseUrl, path), {
        method,
        headers,
        ...(options.formData ? { body: options.formData } : options.body === undefined ? {} : { body: JSON.stringify(options.body) }),
        credentials: "include",
      });
    } catch (error) {
      throw new LocalApiClientError(
        "The local service is unavailable. Check that the desktop sidecar is running.",
        { status: 0, code: "unavailable" },
      );
    }

    const payload = await response.json().catch(() => undefined);
    if (!response.ok) {
      throw errorEnvelope(payload, response.status);
    }
    return parse(payload, response.status);
  }

  private async requestBlob(path: string): Promise<Blob> {
    let response: Response;
    try {
      response = await this.fetcher(apiUrl(this.baseUrl, path), {
        method: "GET",
        headers: { Accept: "application/zip, application/json" },
        credentials: "include",
      });
    } catch {
      throw new LocalApiClientError(
        "The local service is unavailable. Check that the desktop sidecar is running.",
        { status: 0, code: "unavailable" },
      );
    }
    if (!response.ok) {
      const payload = await response.json().catch(() => undefined);
      throw errorEnvelope(payload, response.status);
    }
    return response.blob();
  }
}

export function createLocalApiClient(options: LocalApiClientOptions = {}): LocalApiClient {
  return new LocalApiClient(options);
}
