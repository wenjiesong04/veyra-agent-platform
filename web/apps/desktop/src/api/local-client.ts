import {
  LOCAL_API_SCHEMA_VERSION,
  type AgentSource,
  type AgentRunResponse,
  type AgentTemplate,
  type ComponentDefinition,
  type CommitResponse,
  type CreateAgentRequest,
  type CreatedAgentResponse,
  type CreateProjectRequest,
  type DeleteProjectResponse,
  type DeleteAgentResponse,
  type DraftResponse,
  type ExportResponse,
  type FactoryMissingCapability,
  type FactoryResourcePlanItem,
  type FactoryRunAvailability,
  type FactorySession,
  type FactorySessionState,
  type FactoryStatus,
  type RuntimeStatus,
  type ApplyFactoryDraftResponse,
  type FactoryMessage,
  type JsonObject,
  type JsonValue,
  type ListAgentRunsResponse,
  type ListAgentsResponse,
  type ListAgentTemplatesResponse,
  type ListComponentsResponse,
  type ListResourceFilters,
  type ListResourcesResponse,
  type ListProjectsResponse,
  type LocalErrorEnvelope,
  type OpenProjectRequest,
  type ProjectAgentRecord,
  type ProjectSummaryResponse,
  type SaveDraftRequest,
  type SaveDraftResponse,
  type SelectDirectoryResponse,
  type StartAgentRunRequest,
  type ResourceDescriptor,
  type ResourceAvailability,
  type ResourceKind,
  type ResourceRuntimeStatus,
  type UpdateProjectRequest,
  type UpdateAgentRequest,
  type ValidateResponse,
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
  importAgent(projectId: string, input: { file: File; name?: string; description?: string }): Promise<CreatedAgentResponse>;
  getDraft(projectId: string, agentId: string): Promise<DraftResponse>;
  /** Studio mutations are optional so narrow consumers can still supply read-only APIs. */
  saveDraft?(projectId: string, agentId: string, input: SaveDraftRequest, options: { etag: string; idempotencyKey?: string }): Promise<SaveDraftResponse>;
  reloadDraft?(projectId: string, agentId: string): Promise<DraftResponse>;
  validate?(projectId: string, agentId: string): Promise<ValidateResponse>;
  commit?(projectId: string, agentId: string, options: { expectedRevision: number; etag: string; idempotencyKey?: string }): Promise<CommitResponse>;
  listComponents?(): Promise<ListComponentsResponse>;
  listResources?(filters?: ListResourceFilters): Promise<ListResourcesResponse>;
  getResource?(resourceId: string, version: string): Promise<ResourceDescriptor>;
  factoryStatus?(): Promise<FactoryStatus>;
  runtimeStatus?(): Promise<RuntimeStatus>;
  createFactorySession?(projectId: string, input?: { goal?: string }): Promise<FactorySession>;
  getFactorySession?(projectId: string, sessionId: string): Promise<FactorySession>;
  addFactoryMessage?(projectId: string, sessionId: string, content: string): Promise<FactorySession>;
  generateFactoryBlueprint?(projectId: string, sessionId: string): Promise<FactorySession>;
  applyFactoryDraft?(projectId: string, sessionId: string, input: { confirm: boolean; name?: string; description?: string }): Promise<ApplyFactoryDraftResponse>;
  runAgent?(projectId: string, agentId: string, input: StartAgentRunRequest, options?: { idempotencyKey?: string }): Promise<AgentRunResponse>;
  listAgentRuns?(projectId: string, agentId: string): Promise<ListAgentRunsResponse>;
  getAgentRun?(projectId: string, agentId: string, runId: string): Promise<AgentRunResponse>;
  selectDirectory(): Promise<SelectDirectoryResponse>;
};

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
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
  };
}

function listProjects(value: unknown, status = 502): ListProjectsResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    projects: asArray(record.projects, "projects", status).map((item) => projectSummary(item, status)),
  };
}

function selectedDirectory(value: unknown, status = 502): SelectDirectoryResponse {
  const record = schemaRecord(value, status);
  if (record.status === "selected") return { schema_version: LOCAL_API_SCHEMA_VERSION, status: "selected", root_path: asString(record.root_path, "root_path", status) };
  if (record.status === "cancelled" && record.root_path === null) return { schema_version: LOCAL_API_SCHEMA_VERSION, status: "cancelled", root_path: null };
  throw new LocalApiClientError("The local service returned an invalid directory selection.", { status, code: "invalid_response" });
}

function listAgents(value: unknown, status = 502): ListAgentsResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    agents: asArray(record.agents, "agents", status).map((item) => projectAgent(item, status)),
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

function validated(value: unknown, status = 502): ValidateResponse {
  const record = schemaRecord(value, status);
  if (record.valid !== true) {
    throw new LocalApiClientError("The local service returned an invalid validation result.", {
      status,
      code: "invalid_response",
    });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    valid: true,
    source_hash: asString(record.source_hash, "source_hash", status),
    behavior_hash: asString(record.behavior_hash, "behavior_hash", status),
    lock_hash: asString(record.lock_hash, "lock_hash", status),
    file_hash: asString(record.file_hash, "file_hash", status),
  };
}

function committed(value: unknown, status = 502): CommitResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    version_id: asString(record.version_id, "version_id", status),
    agent_id: asString(record.agent_id, "agent_id", status),
    source_hash: asString(record.source_hash, "source_hash", status),
    behavior_hash: asString(record.behavior_hash, "behavior_hash", status),
    lock_hash: asString(record.lock_hash, "lock_hash", status),
    file_hash: asString(record.file_hash, "file_hash", status),
  };
}

const componentTypes = new Set<ComponentDefinition["type"]>([
  "Start",
  "Agent",
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
  "tool.requested", "tool.started", "tool.completed", "approval.requested", "approval.resolved", "input.requested", "input.resolved",
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
  if (!resourceKinds.has(kind) || !resourceAvailability.has(availability) || !resourceRuntimeStatuses.has(runtimeStatus) || record.origin !== "builtin" || typeof record.factory_selectable !== "boolean") {
    throw new LocalApiClientError("The local service returned an invalid Resource descriptor.", { status, code: "invalid_response" });
  }
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    resource_id: asString(record.resource_id, "resource.resource_id", status),
    kind,
    version: asString(record.version, "resource.version", status),
    reference: asString(record.reference, "resource.reference", status),
    name: asString(record.name, "resource.name", status),
    description: asText(record.description, "resource.description", status),
    origin: "builtin",
    content_hash: asString(record.content_hash, "resource.content_hash", status),
    availability,
    factory_selectable: record.factory_selectable,
    runtime_status: runtimeStatus,
    required_permissions: resourcePermissions(record.required_permissions, status),
    tags: asArray(record.tags, "resource.tags", status).map((item) => asString(item, "resource tag", status)),
    spec: asRecord(record.spec, status) as ResourceDescriptor["spec"],
  };
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
  if (proposal.action !== "quarantined_resource_draft" || proposal.executable !== false) {
    throw new LocalApiClientError("The local service returned an invalid missing-capability proposal.", { status, code: "invalid_response" });
  }
  return {
    kind: asString(record.kind, "factory.missing.kind", status),
    reference: asString(record.reference, "factory.missing.reference", status),
    reason: asString(record.reason, "factory.missing.reason", status),
    proposal: { action: "quarantined_resource_draft", executable: false },
  };
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

function agentRun(value: unknown, status = 502): AgentRunResponse {
  const record = schemaRecord(value, status);
  const runStatus = asString(record.status, "run.status", status);
  if (runStatus !== "running" && runStatus !== "verified" && runStatus !== "unverified" && runStatus !== "failed" && runStatus !== "interrupted") {
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
    agent_id: asString(record.agent_id, "agent_id", status),
    version_id: asString(record.version_id, "version_id", status),
    status: runStatus,
    result,
    error,
    created_at: asString(record.created_at, "created_at", status),
    finished_at: record.finished_at === null ? null : asString(record.finished_at, "finished_at", status),
    ...(record.events === undefined ? {} : { events: asArray(record.events, "run.events", status).map((item) => runtimeEvent(item, status)) }),
  };
}

function listedAgentRuns(value: unknown, status = 502): ListAgentRunsResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    runs: asArray(record.runs, "runs", status).map((item) => agentRun(item, status)),
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
  };
}

function errorEnvelope(value: unknown, status: number): LocalApiClientError {
  let record: Record<string, unknown>;
  try {
    record = schemaRecord(value, status);
  } catch {
    return new LocalApiClientError("The local service returned an invalid error response.", {
      status,
      code: "invalid_error_envelope",
    });
  }
  if (
    typeof record.code !== "string" ||
    typeof record.message !== "string" ||
    typeof record.request_id !== "string"
  ) {
    return new LocalApiClientError("The local service returned an invalid error response.", {
      status,
      code: "invalid_error_envelope",
    });
  }
  let details: Record<string, string> | undefined;
  if (record.details !== undefined) {
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
  }
  const envelope: LocalErrorEnvelope = {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    code: record.code,
    message: record.message,
    request_id: record.request_id,
    ...(details ? { details } : {}),
  };
  return new LocalApiClientError(envelope.message, {
    status,
    code: envelope.code,
    requestId: envelope.request_id,
    details: envelope.details,
  });
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

  importAgent(projectId: string, input: { file: File; name?: string; description?: string }): Promise<CreatedAgentResponse> {
    const formData = new FormData();
    formData.append("file", input.file);
    if (input.name) formData.append("name", input.name);
    if (input.description) formData.append("description", input.description);
    return this.request(`projects/${encodeURIComponent(projectId)}/agents/import`, createdAgent, {
      method: "POST",
      formData,
    });
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

  getResource(resourceId: string, version: string): Promise<ResourceDescriptor> {
    return this.request(`resources/${encodeURIComponent(resourceId)}/versions/${encodeURIComponent(version)}`, resource);
  }

  factoryStatus(): Promise<FactoryStatus> {
    return this.request("factory/status", factoryStatus);
  }

  runtimeStatus(): Promise<RuntimeStatus> {
    return this.request("runtime/status", runtimeStatus);
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
    input: { confirm: boolean; name?: string; description?: string },
  ): Promise<ApplyFactoryDraftResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/factory/sessions/${encodeURIComponent(sessionId)}/apply-draft`,
      appliedFactoryDraft,
      { method: "POST", body: input },
    );
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

  getAgentRun(projectId: string, agentId: string, runId: string): Promise<AgentRunResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/runs/${encodeURIComponent(runId)}`,
      agentRun,
    );
  }

  exportAgent(projectId: string, agentId: string): Promise<ExportResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/export`,
      exported,
    );
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
}

export function createLocalApiClient(options: LocalApiClientOptions = {}): LocalApiClient {
  return new LocalApiClient(options);
}
