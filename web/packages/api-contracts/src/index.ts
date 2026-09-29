import { communityAuthRoutePaths } from "./community-auth";

export const desktopRoutePaths = {
  chat: "#/chat",
  projects: "#/projects",
  components: "#/components",
  resources: "#/resources",
  files: "#/files",
  runs: "#/runs",
  monitor: "#/monitor",
  community: "#/community",
  account: "#/account",
  settings: "#/settings",
  trash: "#/trash",
} as const;

export type DesktopRoute = keyof typeof desktopRoutePaths;

export const projectRoutePaths = {
  project: (projectId: string) => `#/projects/${encodeRouteSegment(projectId)}`,
  projectChat: (projectId: string, conversationId?: string) => conversationId
    ? `#/projects/${encodeRouteSegment(projectId)}/chat?conversation=${encodeRouteSegment(conversationId)}`
    : `#/projects/${encodeRouteSegment(projectId)}/chat`,
  projectAnalysis: (projectId: string) => `#/projects/${encodeRouteSegment(projectId)}/analysis`,
  projectResources: (projectId: string) => `#/projects/${encodeRouteSegment(projectId)}/resources`,
  agents: (projectId: string) => `#/projects/${encodeRouteSegment(projectId)}/agents`,
  agent: (projectId: string, agentId: string) => `#/projects/${encodeRouteSegment(projectId)}/agents/${encodeRouteSegment(agentId)}`,
  agentVersion: (projectId: string, agentId: string, versionId: string) => `#/projects/${encodeRouteSegment(projectId)}/agents/${encodeRouteSegment(agentId)}/versions/${encodeRouteSegment(versionId)}`,
  factory: (projectId: string) => `#/projects/${encodeRouteSegment(projectId)}/factory`,
  agentDesign: (projectId: string, agentId: string) => `#/projects/${encodeRouteSegment(projectId)}/agents/${encodeRouteSegment(agentId)}/design`,
  agentDesignFromWorkflow: (projectId: string, agentId: string, workflowId: string) => `#/projects/${encodeRouteSegment(projectId)}/agents/${encodeRouteSegment(agentId)}/design?fromWorkflow=${encodeRouteSegment(workflowId)}`,
  agentAnalysis: (projectId: string, agentId: string) => `#/projects/${encodeRouteSegment(projectId)}/agents/${encodeRouteSegment(agentId)}/analysis`,
  agentRun: (projectId: string, agentId: string) => `#/projects/${encodeRouteSegment(projectId)}/agents/${encodeRouteSegment(agentId)}/run`,
  workflows: (projectId: string) => `#/projects/${encodeRouteSegment(projectId)}/workflows`,
  workflow: (projectId: string, workflowId: string) => `#/projects/${encodeRouteSegment(projectId)}/workflows/${encodeRouteSegment(workflowId)}`,
  knowledge: (projectId: string) => `#/projects/${encodeRouteSegment(projectId)}/knowledge`,
  knowledgeItem: (projectId: string, knowledgeId: string) => `#/projects/${encodeRouteSegment(projectId)}/knowledge/${encodeRouteSegment(knowledgeId)}`,
  files: (projectId: string) => `#/projects/${encodeRouteSegment(projectId)}/files`,
  runs: (projectId: string) => `#/projects/${encodeRouteSegment(projectId)}/runs`,
} as const;

export const communityRoutePaths = {
  catalog: "#/community",
  published: "#/community/published",
  starred: "#/community/starred",
  mine: "#/community/mine",
  following: "#/community/following",
  entry: (owner: string, slug: string) => `#/community/${encodeRouteSegment(owner)}/${encodeRouteSegment(slug)}`,
  version: (owner: string, slug: string, versionId: string) => `#/community/${encodeRouteSegment(owner)}/${encodeRouteSegment(slug)}/versions/${encodeRouteSegment(versionId)}`,
} as const;

export const libraryRoutePaths = {
  component: (componentId: string) => `#/components/${encodeRouteSegment(componentId)}`,
  file: (fileId: string) => `#/files/${encodeRouteSegment(fileId)}`,
} as const;

export type ProjectRouteKind = "project" | "project-chat" | "project-analysis" | "project-resources" | "project-agents" | "project-workflows" | "project-workflow" | "project-knowledge" | "project-knowledge-item" | "project-files" | "project-runs" | "agent-detail" | "agent-version" | "factory" | "agent-design" | "agent-analysis" | "agent-run";
export type CommunitySubrouteKind = "community-published" | "community-starred" | "community-mine";
export type DesktopSubrouteKind = "component" | "file" | "community-entry" | "community-version" | CommunitySubrouteKind;
export type DesktopAuthRouteKind = "login" | "register" | "forgot-password";

export type DesktopRouteLocation =
  | { kind: "projects"; path: string }
  | { kind: DesktopRoute; path: string; }
  | { kind: ProjectRouteKind; path: string; projectId: string; agentId?: string; versionId?: string; workflowId?: string; knowledgeId?: string; conversationId?: string }
  | { kind: DesktopSubrouteKind; path: string; componentId?: string; fileId?: string; owner?: string; slug?: string; versionId?: string }
  | { kind: DesktopAuthRouteKind; path: string }
  | { kind: "not-found"; path: string };

function encodeRouteSegment(value: string): string {
  return encodeURIComponent(value);
}

function decodeRouteSegment(value: string): string | null {
  try {
    const decoded = decodeURIComponent(value);
    return decoded.trim() ? decoded : null;
  } catch {
    return null;
  }
}

function normalizeRoutePath(input: string): string {
  const withoutHash = input.replace(/^#\/?/, "");
  const withoutQuery = withoutHash.split("?")[0] ?? "";
  return withoutQuery.replace(/^\/+|\/+$/g, "");
}

function fromWorkflowQuery(input: string): string | undefined {
  const raw = input.replace(/^#/, "");
  const query = raw.includes("?") ? raw.slice(raw.indexOf("?") + 1) : "";
  const value = new URLSearchParams(query).get("fromWorkflow");
  const decoded = value ? decodeRouteSegment(value) : null;
  return decoded ?? undefined;
}

function conversationQuery(input: string): string | undefined {
  const raw = input.replace(/^#/, "");
  const query = raw.includes("?") ? raw.slice(raw.indexOf("?") + 1) : "";
  const value = new URLSearchParams(query).get("conversation");
  const decoded = value ? decodeRouteSegment(value) : null;
  return decoded ?? undefined;
}

export function parseDesktopRoute(input: string): DesktopRouteLocation {
  const normalized = normalizeRoutePath(input);
  const path = normalized ? `#/${normalized}` : "#/projects";
  const fromWorkflow = fromWorkflowQuery(input);
  const parts = normalized.split("/").filter(Boolean);

  if (parts.length === 0 || (parts.length === 1 && parts[0] === "projects")) {
    return { kind: "projects", path };
  }

  const topLevel = parts[0] as DesktopRoute | undefined;
  if (parts.length === 1 && topLevel && topLevel in desktopRoutePaths) {
    return { kind: topLevel, path };
  }
  if (parts.length === 1 && parts[0] === "login") return { kind: "login", path };
  if (parts.length === 1 && parts[0] === "register") return { kind: "register", path };
  if (parts.length === 1 && parts[0] === "forgot-password") return { kind: "forgot-password", path };

  if (parts[0] === "components" && parts.length === 2) {
    const componentId = decodeRouteSegment(parts[1]);
    return componentId ? { kind: "component", path, componentId } : { kind: "not-found", path };
  }
  if (parts[0] === "files" && parts.length === 2) {
    const fileId = decodeRouteSegment(parts[1]);
    return fileId ? { kind: "file", path, fileId } : { kind: "not-found", path };
  }
  if (parts[0] === "components" || parts[0] === "files") return { kind: "not-found", path };

  if (parts[0] === "community" && parts.length === 3) {
    const owner = decodeRouteSegment(parts[1]);
    const slug = decodeRouteSegment(parts[2]);
    return owner && slug ? { kind: "community-entry", path, owner, slug } : { kind: "not-found", path };
  }
  if (parts[0] === "community" && parts.length === 2 && (parts[1] === "published" || parts[1] === "starred" || parts[1] === "mine" || parts[1] === "following")) {
    const kind: CommunitySubrouteKind = parts[1] === "published"
      ? "community-published"
      : parts[1] === "starred"
        ? "community-starred"
        : "community-mine";
    return { kind, path };
  }
  if (parts[0] === "community" && parts.length === 5 && parts[3] === "versions") {
    const owner = decodeRouteSegment(parts[1]);
    const slug = decodeRouteSegment(parts[2]);
    const versionId = decodeRouteSegment(parts[4]);
    return owner && slug && versionId ? { kind: "community-version", path, owner, slug, versionId } : { kind: "not-found", path };
  }
  if (parts[0] === "community") return { kind: "not-found", path };

  if (parts[0] !== "projects") return { kind: "not-found", path };
  const projectId = parts[1] ? decodeRouteSegment(parts[1]) : null;
  if (!projectId) return { kind: "not-found", path };
  if (parts.length === 2) return { kind: "project", path, projectId };
  if (parts.length === 3 && parts[2] === "chat") {
    const conversationId = conversationQuery(input);
    return conversationId
      ? { kind: "project-chat", path, projectId, conversationId }
      : { kind: "project-chat", path, projectId };
  }
  if (parts.length === 3 && parts[2] === "analysis") return { kind: "project-analysis", path, projectId };
  if (parts.length === 3 && parts[2] === "resources") return { kind: "project-resources", path, projectId };
  if (parts.length === 3 && parts[2] === "factory") return { kind: "factory", path, projectId };

  if (parts.length === 3 && parts[2] === "agents") return { kind: "project-agents", path, projectId };
  if (parts.length === 3 && parts[2] === "workflows") return { kind: "project-workflows", path, projectId };
  if (parts.length === 3 && parts[2] === "knowledge") return { kind: "project-knowledge", path, projectId };
  if (parts.length === 3 && parts[2] === "files") return { kind: "project-files", path, projectId };
  if (parts.length === 3 && parts[2] === "runs") return { kind: "project-runs", path, projectId };
  const nestedId = parts[3] ? decodeRouteSegment(parts[3]) : null;
  if (parts.length === 4 && parts[2] === "workflows" && nestedId) return { kind: "project-workflow", path, projectId, workflowId: nestedId };
  if (parts.length === 4 && parts[2] === "knowledge" && nestedId) return { kind: "project-knowledge-item", path, projectId, knowledgeId: nestedId };

  const agentId = parts[3] ? decodeRouteSegment(parts[3]) : null;
  if (parts.length === 4 && parts[2] === "agents" && agentId) return { kind: "agent-detail", path, projectId, agentId };
  const versionId = parts[5] ? decodeRouteSegment(parts[5]) : null;
  if (parts.length === 6 && parts[2] === "agents" && agentId && parts[4] === "versions" && versionId) return { kind: "agent-version", path, projectId, agentId, versionId, ...(fromWorkflow ? { workflowId: fromWorkflow } : {}) };
  if (parts.length === 5 && parts[2] === "agents" && agentId && parts[4] === "design") {
    return { kind: "agent-design", path, projectId, agentId, ...(fromWorkflow ? { workflowId: fromWorkflow } : {}) };
  }
  if (parts.length === 5 && parts[2] === "agents" && agentId && parts[4] === "analysis") {
    return { kind: "agent-analysis", path, projectId, agentId };
  }
  if (parts.length === 5 && parts[2] === "agents" && agentId && parts[4] === "run") {
    return { kind: "agent-run", path, projectId, agentId };
  }

  return { kind: "not-found", path };
}

export function isDesktopPublicAuthRoute(kind: DesktopRouteLocation["kind"]): boolean {
  return kind === "login" || kind === "register" || kind === "forgot-password";
}

export function readDesktopLoginNext(hash: string): string | null {
  const raw = hash.replace(/^#/, "");
  const query = raw.includes("?") ? raw.slice(raw.indexOf("?") + 1) : "";
  const value = new URLSearchParams(query).get("next");
  if (!value) return null;
  let decoded = value;
  try {
    decoded = decodeURIComponent(value);
  } catch {
    return null;
  }
  if (!decoded.startsWith("#/")) return null;
  if (isDesktopPublicAuthRoute(parseDesktopRoute(decoded).kind)) return null;
  return decoded;
}

export function desktopLoginHash(fromHash = ""): string {
  const parsed = parseDesktopRoute(fromHash);
  if (isDesktopPublicAuthRoute(parsed.kind)) {
    if (parsed.kind === "login") return fromHash.startsWith("#/login") ? fromHash : communityAuthRoutePaths.login;
    return `#/${parsed.kind}`;
  }
  const target = fromHash.startsWith("#") ? fromHash : parsed.path;
  return `${communityAuthRoutePaths.login}?next=${encodeURIComponent(target)}`;
}

export function desktopPathAfterAuth(hash: string, fallback: string): string {
  return readDesktopLoginNext(hash) ?? fallback;
}

export type HealthTone = "good" | "warn" | "bad" | "neutral";
export type ProjectState = "active" | "paused" | "ready";
export type AgentState = "draft" | "ready" | "running" | "attention";
export type RunState = "queued" | "running" | "waiting" | "verified" | "failed";

export type ProjectSummary = {
  id: string;
  name: string;
  description: string;
  state: ProjectState;
  agentCount: number;
  activeRuns: number;
  updatedAt: string;
};

export type AgentSummary = {
  id: string;
  projectId: string;
  name: string;
  description: string;
  state: AgentState;
  version: string;
  componentCount: number;
  lastRun: string;
};

export type RunSummary = {
  id: string;
  agentName: string;
  projectName: string;
  state: RunState;
  startedAt: string;
  duration: string;
  eventCount: number;
};

export type MonitorSignal = {
  id: string;
  label: string;
  detail: string;
  tone: HealthTone;
  time: string;
};

export type AccountSummary = {
  displayName: string;
  mode: "local" | "connected";
  workspaceLabel: string;
  permissions: string[];
};

export * from "./local";
export * from "./cloud";
export * from "./community-auth";
export * from "./community-registry";
