export const desktopRoutePaths = {
  projects: "#/projects",
  factory: "#/factory",
  studio: "#/studio",
  runs: "#/runs",
  monitor: "#/monitor",
  community: "#/community",
  account: "#/account",
  settings: "#/settings",
} as const;

export type DesktopRoute = keyof typeof desktopRoutePaths;

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

export type CommunityEntry = {
  id: string;
  name: string;
  author: string;
  summary: string;
  version: string;
  category: string;
  installs: string;
  verified: boolean;
};

export type AccountSummary = {
  displayName: string;
  mode: "local" | "connected";
  workspaceLabel: string;
  permissions: string[];
};
