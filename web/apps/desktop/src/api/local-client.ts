import {
  LOCAL_API_SCHEMA_VERSION,
  type AgentSource,
  type CommitResponse,
  type CreateProjectRequest,
  type DraftResponse,
  type ExportResponse,
  type ListAgentsResponse,
  type ListProjectsResponse,
  type LocalErrorEnvelope,
  type OpenProjectRequest,
  type ProjectAgentRecord,
  type ProjectSummaryResponse,
  type SaveDraftRequest,
  type SaveDraftResponse,
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
};

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH";
  body?: object;
  ifMatch?: string;
  idempotencyKey?: string;
  requireIdempotencyKey?: boolean;
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
    manifest_hash: asString(record.manifest_hash, "manifest_hash", status),
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

function listAgents(value: unknown, status = 502): ListAgentsResponse {
  const record = schemaRecord(value, status);
  return {
    schema_version: LOCAL_API_SCHEMA_VERSION,
    agents: asArray(record.agents, "agents", status).map((item) => projectAgent(item, status)),
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

  getProject(projectId: string): Promise<ProjectSummaryResponse> {
    return this.request(`projects/${encodeURIComponent(projectId)}`, projectSummary);
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
    options: { idempotencyKey?: string } = {},
  ): Promise<CommitResponse> {
    return this.request(
      `projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(agentId)}/commit`,
      committed,
      {
        method: "POST",
        idempotencyKey: options.idempotencyKey,
        requireIdempotencyKey: true,
      },
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

    let response: Response;
    try {
      response = await this.fetcher(apiUrl(this.baseUrl, path), {
        method,
        headers,
        ...(options.body === undefined ? {} : { body: JSON.stringify(options.body) }),
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
