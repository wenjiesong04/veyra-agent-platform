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
} from "@veyra/api-contracts";

const configuredBaseUrl = import.meta.env.VITE_COMMUNITY_API_BASE_URL?.trim();
const apiBaseUrl = (configuredBaseUrl || "/api/v1").replace(/\/$/, "");
const csrfCookieNames = import.meta.env.PROD
  ? ["__Host-veyra-csrf", "veyra-csrf"] as const
  : ["veyra-csrf", "__Host-veyra-csrf"] as const;

type ErrorBody = {
  detail?: unknown;
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

function cookieValue(name: string): string | null {
  const prefix = `${encodeURIComponent(name)}=`;
  for (const part of document.cookie.split(";")) {
    const value = part.trim();
    if (value.startsWith(prefix)) return decodeURIComponent(value.slice(prefix.length));
  }
  return null;
}

export function readCommunityCsrfToken(): string | null {
  for (const name of csrfCookieNames) {
    const token = cookieValue(name);
    if (token) return token;
  }
  return null;
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
  return new CommunityApiError(code, {
    status: response.status,
    code,
    validationMessages: messages,
  });
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = readCommunityCsrfToken();
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      method,
      headers,
      credentials: "include",
    });
  } catch (error) {
    throw new CommunityApiError(error instanceof Error ? error.message : "network_unavailable", {
      code: "network_unavailable",
    });
  }

  if (!response.ok) throw await apiError(response);
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

function jsonBody(value: object): string {
  return JSON.stringify(value);
}

function browserDeviceName(): string {
  const platform = navigator.platform?.trim();
  return platform ? `${platform} browser` : "Web browser";
}

export const communityApi = {
  hasRefreshEvidence(): boolean {
    return readCommunityCsrfToken() !== null;
  },

  async me(): Promise<CommunityAccount> {
    const response = await request<CommunityMeResponse>("/account/me");
    return response.account;
  },

  async refresh(): Promise<CommunityAccount> {
    const response = await request<CommunityAuthenticatedResponse>("/auth/refresh", { method: "POST" });
    return response.account;
  },

  async requestVerificationCode(email: string, purpose: CommunityVerificationCodeRequest["purpose"]): Promise<CommunityAcceptedResponse> {
    const payload: CommunityVerificationCodeRequest = { email, purpose, device_name: browserDeviceName() };
    return request("/auth/verification-codes", { method: "POST", body: jsonBody(payload) });
  },

  async register(payload: Omit<CommunityRegistrationRequest, "device_name">): Promise<CommunityAccount> {
    const response = await request<CommunityAuthenticatedResponse>("/auth/register", {
      method: "POST",
      body: jsonBody({ ...payload, device_name: browserDeviceName() }),
    });
    return response.account;
  },

  async login(payload: Omit<CommunityLoginRequest, "device_name">): Promise<CommunityAccount> {
    const response = await request<CommunityAuthenticatedResponse>("/auth/login", {
      method: "POST",
      body: jsonBody({ ...payload, device_name: browserDeviceName() }),
    });
    return response.account;
  },

  async logout(): Promise<void> {
    await request<void>("/auth/logout", { method: "POST" });
  },

  async resetPassword(payload: Omit<CommunityPasswordResetRequest, "device_name">): Promise<CommunityPasswordResetResponse> {
    return request("/auth/password-reset/confirm", {
      method: "POST",
      body: jsonBody({ ...payload, device_name: browserDeviceName() }),
    });
  },

  async updateProfile(payload: CommunityProfileUpdate): Promise<CommunityAccount> {
    const response = await request<CommunityMeResponse>("/account/profile", {
      method: "PATCH",
      body: jsonBody(payload),
    });
    return response.account;
  },

  async listSessions(): Promise<CommunityDeviceSession[]> {
    const response = await request<CommunitySessionListResponse>("/account/sessions");
    return response.sessions;
  },

  async revokeSession(sessionId: string): Promise<void> {
    await request<void>(`/account/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
  },
};
