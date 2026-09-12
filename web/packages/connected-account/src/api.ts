import type {
  CommunityAcceptedResponse,
  CommunityAccount,
  CommunityAuthenticatedResponse,
  CommunityDeviceSession,
  CommunityLoginRequest,
  CommunityMeResponse,
  CommunityPasswordResetRequest,
  CommunityPasswordResetResponse,
  CommunityProfileUpdate,
  CommunityRegistrationRequest,
  CommunitySessionListResponse,
  CommunityVerificationCodeRequest,
  CommunityRegistryEntry,
  CommunityRegistryListResponse,
  CommunityForkOrigin,
  CommunityRegistryFeedbackResponse,
  CommunityRegistryReportRequest,
  CommunityRegistryReportResponse,
  CommunityRegistryReviewRequest,
  CommunityRegistryReviewsResponse,
  CommunityRegistryVersionsResponse,
  CommunityRegistryModerationQueueResponse,
  CommunityRegistryModerationRequest,
  CommunityPluginEntry,
  CommunityPluginListResponse,
  CommunityPluginVersionsResponse,
  CommunityPluginModerationQueueResponse,
  CommunityPluginModerationRequest,
} from "@veyra/api-contracts";
import { communityAccountApiPaths } from "@veyra/api-contracts";

export type CommunityApiOptions = {
  baseUrl: string;
  fetcher?: typeof fetch;
};

export class CommunityApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly validationMessages: string[];

  constructor(message: string, options: { status?: number; code?: string; validationMessages?: string[] } = {}) {
    super(message);
    this.name = "CommunityApiError";
    this.status = options.status ?? 0;
    this.code = options.code ?? "request_failed";
    this.validationMessages = options.validationMessages ?? [];
  }
}

export type CommunityApi = {
  hasRefreshEvidence: () => boolean;
  me: () => Promise<CommunityAccount>;
  refresh: () => Promise<CommunityAccount>;
  requestVerificationCode: (email: string, purpose: CommunityVerificationCodeRequest["purpose"]) => Promise<CommunityAcceptedResponse>;
  register: (payload: Omit<CommunityRegistrationRequest, "device_name">) => Promise<CommunityAccount>;
  login: (payload: Omit<CommunityLoginRequest, "device_name">) => Promise<CommunityAccount>;
  logout: () => Promise<void>;
  resetPassword: (payload: Omit<CommunityPasswordResetRequest, "device_name">) => Promise<CommunityPasswordResetResponse>;
  updateProfile: (payload: CommunityProfileUpdate) => Promise<CommunityAccount>;
  listSessions: () => Promise<CommunityDeviceSession[]>;
  revokeSession: (sessionId: string) => Promise<void>;
  uploadAvatar: (file: File) => Promise<CommunityAccount>;
  replaceAvatar: (file: File) => Promise<CommunityAccount>;
  deleteAvatar: () => Promise<void>;
  listRegistryAgents: (query?: string) => Promise<CommunityRegistryEntry[]>;
  getRegistryAgent: (ownerHandle: string, slug: string, version?: string) => Promise<CommunityRegistryEntry>;
  listRegistryAgentVersions: (ownerHandle: string, slug: string) => Promise<CommunityRegistryEntry[]>;
  listRegistryModerationQueue: () => Promise<CommunityRegistryEntry[]>;
  moderateRegistryAgent: (ownerHandle: string, slug: string, version: string, input: CommunityRegistryModerationRequest) => Promise<CommunityRegistryEntry>;
  downloadRegistryAgent: (ownerHandle: string, slug: string, version: string) => Promise<Blob>;
  publishRegistryAgent: (file: File, forkOf?: CommunityForkOrigin) => Promise<CommunityRegistryEntry>;
  starRegistryAgent: (ownerHandle: string, slug: string, version: string) => Promise<CommunityRegistryFeedbackResponse>;
  getRegistryStarStatus: (ownerHandle: string, slug: string, version: string) => Promise<CommunityRegistryFeedbackResponse>;
  unstarRegistryAgent: (ownerHandle: string, slug: string, version: string) => Promise<CommunityRegistryFeedbackResponse>;
  listRegistryReviews: (ownerHandle: string, slug: string, version: string) => Promise<CommunityRegistryReviewsResponse>;
  reviewRegistryAgent: (ownerHandle: string, slug: string, version: string, input: CommunityRegistryReviewRequest) => Promise<CommunityRegistryFeedbackResponse & { review: CommunityRegistryReviewsResponse["reviews"][number] }>;
  reportRegistryAgent: (ownerHandle: string, slug: string, version: string, input: CommunityRegistryReportRequest) => Promise<CommunityRegistryReportResponse>;
  listRegistryPlugins: (query?: string) => Promise<CommunityPluginEntry[]>;
  getRegistryPlugin: (ownerHandle: string, slug: string, version?: string) => Promise<CommunityPluginEntry>;
  listRegistryPluginVersions: (ownerHandle: string, slug: string) => Promise<CommunityPluginEntry[]>;
  downloadRegistryPlugin: (ownerHandle: string, slug: string, version: string) => Promise<Blob>;
  publishRegistryPlugin: (file: File) => Promise<CommunityPluginEntry>;
  listRegistryPluginModerationQueue: () => Promise<CommunityPluginEntry[]>;
  moderateRegistryPlugin: (ownerHandle: string, slug: string, version: string, input: CommunityPluginModerationRequest) => Promise<CommunityPluginEntry>;
};

type ErrorBody = {
  detail?: unknown;
};

function cookieValue(name: string): string | null {
  if (typeof document === "undefined") return null;
  const prefix = `${encodeURIComponent(name)}=`;
  for (const part of document.cookie.split(";")) {
    const value = part.trim();
    if (value.startsWith(prefix)) return decodeURIComponent(value.slice(prefix.length));
  }
  return null;
}

export function readCommunityCsrfToken(): string | null {
  return cookieValue("veyra-csrf") ?? cookieValue("__Host-veyra-csrf");
}

export function normalizeCommunityAvatarUrl(value: string | null | undefined, baseUrl: string): string | null {
  if (!value) return null;
  if (/^[a-z][a-z\d+.-]*:/i.test(value)) return value;
  const parsed = new URL(value, "http://community.invalid");
  const communityApiPath = "/api/v1";
  if (parsed.pathname === communityApiPath || parsed.pathname.startsWith(`${communityApiPath}/`)) {
    const normalizedBase = baseUrl.trim().replace(/\/$/, "");
    return `${normalizedBase}${parsed.pathname.slice(communityApiPath.length)}${parsed.search}${parsed.hash}`;
  }
  return value;
}

function validationMessages(detail: unknown): string[] {
  if (!Array.isArray(detail)) return [];
  return detail.flatMap((item) => {
    if (typeof item !== "object" || item === null || !("msg" in item)) return [];
    return typeof item.msg === "string" ? [item.msg] : [];
  });
}

async function apiError(response: Response): Promise<CommunityApiError> {
  let body: ErrorBody = {};
  try {
    const candidate: unknown = await response.json();
    if (typeof candidate === "object" && candidate !== null) body = candidate as ErrorBody;
  } catch {
    // An empty or non-JSON response still has a useful HTTP status.
  }
  const messages = validationMessages(body.detail);
  const code = typeof body.detail === "string"
    ? body.detail
    : messages.length > 0
      ? "validation_error"
      : `http_${response.status}`;
  return new CommunityApiError(code, { status: response.status, code, validationMessages: messages });
}

function browserDeviceName(): string {
  const platform = typeof navigator !== "undefined" ? navigator.platform?.trim() : "";
  return platform ? `${platform} browser` : "Web browser";
}

function jsonBody(value: object): string {
  return JSON.stringify(value);
}

export function createCommunityApi(options: CommunityApiOptions): CommunityApi {
  const apiBaseUrl = options.baseUrl.trim().replace(/\/$/, "");
  if (!apiBaseUrl) throw new Error("Community API base URL is required");
  const fetcher = options.fetcher ?? ((input: RequestInfo | URL, init?: RequestInit) => fetch(input, init));

  function accountWithNormalizedAvatar(account: CommunityAccount): CommunityAccount {
    return { ...account, avatar_url: normalizeCommunityAvatarUrl(account.avatar_url, apiBaseUrl) };
  }

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const method = (init.method ?? "GET").toUpperCase();
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (init.body !== undefined && !(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      const csrf = readCommunityCsrfToken();
      if (csrf) headers.set("X-CSRF-Token", csrf);
    }

    let response: Response;
    try {
      response = await fetcher(`${apiBaseUrl}${path}`, { ...init, method, headers, credentials: "include" });
    } catch (error) {
      throw new CommunityApiError(error instanceof Error ? error.message : "network_unavailable", { code: "network_unavailable" });
    }

    if (!response.ok) throw await apiError(response);
    if (response.status === 204) return undefined as T;
    return await response.json() as T;
  }

  async function requestBlob(path: string): Promise<Blob> {
    let response: Response;
    try {
      response = await fetcher(`${apiBaseUrl}${path}`, {
        method: "GET",
        headers: { Accept: "application/zip, application/yaml, text/yaml" },
        credentials: "include",
      });
    } catch (error) {
      throw new CommunityApiError(error instanceof Error ? error.message : "network_unavailable", { code: "network_unavailable" });
    }
    if (!response.ok) throw await apiError(response);
    return response.blob();
  }

  const api: CommunityApi = {
    hasRefreshEvidence: () => readCommunityCsrfToken() !== null,

    async me() {
      const response = await request<CommunityMeResponse>(communityAccountApiPaths.me);
      return accountWithNormalizedAvatar(response.account);
    },

    async refresh() {
      const response = await request<CommunityAuthenticatedResponse>("/auth/refresh", { method: "POST" });
      return accountWithNormalizedAvatar(response.account);
    },

    async requestVerificationCode(email, purpose) {
      const payload: CommunityVerificationCodeRequest = { email, purpose, device_name: browserDeviceName() };
      return request("/auth/verification-codes", { method: "POST", body: jsonBody(payload) });
    },

    async register(payload) {
      const response = await request<CommunityAuthenticatedResponse>("/auth/register", { method: "POST", body: jsonBody({ ...payload, device_name: browserDeviceName() }) });
      return accountWithNormalizedAvatar(response.account);
    },

    async login(payload) {
      const response = await request<CommunityAuthenticatedResponse>("/auth/login", { method: "POST", body: jsonBody({ ...payload, device_name: browserDeviceName() }) });
      return accountWithNormalizedAvatar(response.account);
    },

    async logout() {
      await request<void>("/auth/logout", { method: "POST" });
    },

    async resetPassword(payload) {
      return request("/auth/password-reset/confirm", { method: "POST", body: jsonBody({ ...payload, device_name: browserDeviceName() }) });
    },

    async updateProfile(payload) {
      const response = await request<CommunityMeResponse>(communityAccountApiPaths.profile, { method: "PATCH", body: jsonBody(payload) });
      return accountWithNormalizedAvatar(response.account);
    },

    async listSessions() {
      const response = await request<CommunitySessionListResponse>(communityAccountApiPaths.sessions);
      return response.sessions;
    },

    async revokeSession(sessionId) {
      await request<void>(`${communityAccountApiPaths.sessions}/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
    },

    async uploadAvatar(file) {
      return api.replaceAvatar(file);
    },

    async replaceAvatar(file) {
      const body = new FormData();
      body.append("avatar", file, file.name);
      const response = await request<CommunityMeResponse>(communityAccountApiPaths.avatar, { method: "POST", body });
      return accountWithNormalizedAvatar(response.account);
    },

    async deleteAvatar() {
      await request<void>(communityAccountApiPaths.avatar, { method: "DELETE" });
    },

    async listRegistryAgents(query) {
      const suffix = query?.trim() ? `?query=${encodeURIComponent(query.trim())}` : "";
      const response = await request<CommunityRegistryListResponse>(`/registry/agents${suffix}`);
      return response.entries;
    },

    async getRegistryAgent(ownerHandle, slug, version) {
      const path = version
        ? `/registry/agents/${encodeURIComponent(ownerHandle)}/${encodeURIComponent(slug)}/versions/${encodeURIComponent(version)}`
        : `/registry/agents/${encodeURIComponent(ownerHandle)}/${encodeURIComponent(slug)}`;
      return request<CommunityRegistryEntry>(path);
    },

    async listRegistryAgentVersions(ownerHandle, slug) {
      const response = await request<CommunityRegistryVersionsResponse>(`/registry/agents/${encodeURIComponent(ownerHandle)}/${encodeURIComponent(slug)}/versions`);
      return response.versions;
    },

    async listRegistryModerationQueue() {
      const response = await request<CommunityRegistryModerationQueueResponse>("/registry/moderation/queue");
      return response.entries;
    },

    async moderateRegistryAgent(ownerHandle, slug, version, input) {
      return request<CommunityRegistryEntry>(`/registry/agents/${encodeURIComponent(ownerHandle)}/${encodeURIComponent(slug)}/versions/${encodeURIComponent(version)}/moderate`, { method: "POST", body: jsonBody(input) });
    },

    async downloadRegistryAgent(ownerHandle, slug, version) {
      return requestBlob(`/registry/agents/${encodeURIComponent(ownerHandle)}/${encodeURIComponent(slug)}/versions/${encodeURIComponent(version)}/download`);
    },

    async publishRegistryAgent(file, forkOf) {
      const body = new FormData();
      body.append("package", file, file.name);
      if (forkOf) {
        body.append("fork_owner_handle", forkOf.owner_handle);
        body.append("fork_slug", forkOf.slug);
        body.append("fork_version", forkOf.version);
        body.append("fork_source_hash", forkOf.source_hash);
      }
      return request<CommunityRegistryEntry>("/registry/agents", { method: "POST", body });
    },

    async starRegistryAgent(ownerHandle, slug, version) {
      return request<CommunityRegistryFeedbackResponse>(`/registry/agents/${encodeURIComponent(ownerHandle)}/${encodeURIComponent(slug)}/versions/${encodeURIComponent(version)}/star`, { method: "POST" });
    },

    async getRegistryStarStatus(ownerHandle, slug, version) {
      return request<CommunityRegistryFeedbackResponse>(`/registry/agents/${encodeURIComponent(ownerHandle)}/${encodeURIComponent(slug)}/versions/${encodeURIComponent(version)}/star`);
    },

    async unstarRegistryAgent(ownerHandle, slug, version) {
      return request<CommunityRegistryFeedbackResponse>(`/registry/agents/${encodeURIComponent(ownerHandle)}/${encodeURIComponent(slug)}/versions/${encodeURIComponent(version)}/star`, { method: "DELETE" });
    },

    async listRegistryReviews(ownerHandle, slug, version) {
      return request<CommunityRegistryReviewsResponse>(`/registry/agents/${encodeURIComponent(ownerHandle)}/${encodeURIComponent(slug)}/versions/${encodeURIComponent(version)}/reviews`);
    },

    async reviewRegistryAgent(ownerHandle, slug, version, input) {
      return request<CommunityRegistryFeedbackResponse & { review: CommunityRegistryReviewsResponse["reviews"][number] }>(`/registry/agents/${encodeURIComponent(ownerHandle)}/${encodeURIComponent(slug)}/versions/${encodeURIComponent(version)}/reviews`, { method: "POST", body: jsonBody(input) });
    },

    async reportRegistryAgent(ownerHandle, slug, version, input) {
      return request<CommunityRegistryReportResponse>(`/registry/agents/${encodeURIComponent(ownerHandle)}/${encodeURIComponent(slug)}/versions/${encodeURIComponent(version)}/report`, { method: "POST", body: jsonBody(input) });
    },

    async listRegistryPlugins(query) {
      const suffix = query?.trim() ? `?query=${encodeURIComponent(query.trim())}` : "";
      const response = await request<CommunityPluginListResponse>(`/registry/plugins${suffix}`);
      return response.entries;
    },

    async getRegistryPlugin(ownerHandle, slug, version) {
      const path = version
        ? `/registry/plugins/${encodeURIComponent(ownerHandle)}/${encodeURIComponent(slug)}/versions/${encodeURIComponent(version)}`
        : `/registry/plugins/${encodeURIComponent(ownerHandle)}/${encodeURIComponent(slug)}`;
      return request<CommunityPluginEntry>(path);
    },

    async listRegistryPluginVersions(ownerHandle, slug) {
      const response = await request<CommunityPluginVersionsResponse>(`/registry/plugins/${encodeURIComponent(ownerHandle)}/${encodeURIComponent(slug)}/versions`);
      return response.versions;
    },

    async downloadRegistryPlugin(ownerHandle, slug, version) {
      return requestBlob(`/registry/plugins/${encodeURIComponent(ownerHandle)}/${encodeURIComponent(slug)}/versions/${encodeURIComponent(version)}/download`);
    },

    async publishRegistryPlugin(file) {
      const body = new FormData();
      body.append("package", file, file.name);
      return request<CommunityPluginEntry>("/registry/plugins", { method: "POST", body });
    },

    async listRegistryPluginModerationQueue() {
      const response = await request<CommunityPluginModerationQueueResponse>("/registry/plugins/moderation/queue");
      return response.entries;
    },

    async moderateRegistryPlugin(ownerHandle, slug, version, input) {
      return request<CommunityPluginEntry>(`/registry/plugins/${encodeURIComponent(ownerHandle)}/${encodeURIComponent(slug)}/versions/${encodeURIComponent(version)}/moderate`, { method: "POST", body: jsonBody(input) });
    },
  };

  return api;
}
