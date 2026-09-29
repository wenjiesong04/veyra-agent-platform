import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentImportApplyResponse, AgentImportRecord, CommunityAccount, CommunityRegistryEntry, ProjectSummaryResponse } from "@veyra/api-contracts";
import { AuthProvider, type CommunityApi, type CommunitySection } from "@veyra/connected-account";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../api/project-workspace";
import type { LocalProjectApi } from "../api/local-client";
import { CommunityPage } from "./community";

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

const entry = {
  schema_version: "community.registry.v1",
  owner_handle: "agent-maker",
  owner_display_name: "Agent Maker",
  slug: "meeting-summary",
  name: "Meeting Summary",
  description: "Summarize a meeting.",
  version: "1.2.0",
  source_hash: "a".repeat(64),
  behavior_hash: "b".repeat(64),
  lock_hash: "c".repeat(64),
  status: "published",
  created_at: "2026-09-20T00:00:00Z",
  published_at: "2026-09-20T00:00:00Z",
  fork_of: null,
  capabilities: {
    tools: ["veyra.tool.filesystem.read@1.0.0"], skills: [], policies: [], knowledge: [], secret_refs: [],
    permissions: { network_hosts: [], tools: [], filesystem_read_roots: ["project"], filesystem_write_roots: [], shell_workspace_only: false },
    verification_required: false, verification_checks: [], node_count: 2, risk_level: "low", risk_reasons: [],
  },
  scan: { schema_version: "community.scan.v1", status: "passed", package_bytes: 512, checks: [], warnings: [], risk_level: "low", risk_reasons: [] },
  star_count: 1,
  review_count: 0,
  average_rating: 0,
} as CommunityRegistryEntry;

const importRecord = {
  schema_version: "agent.import.v1",
  import_id: "01a0cd34-90b2-7e69-9045-8062dea9efdc",
  state: "analyzed",
  source_kind: "yaml",
  source_name: "meeting-summary.vagent.yaml",
  source_path: "meeting-summary.vagent.yaml",
  detected_format: "veyra_agent_yaml",
  compatibility: 1,
  preview: { name: "Meeting Summary", description: "Summarize a meeting.", instructions: "", model: {}, inputs: {}, outputs: {}, tools: [], skills: [], knowledge_files: [], workflow_present: false },
  capabilities: [],
  warnings: [],
  generated_source: {},
  manifest: {},
  community_origin: { owner_handle: entry.owner_handle, slug: entry.slug, version: entry.version, source_hash: entry.source_hash },
  project_validation: {
    project_id: "project-1",
    source_hash: entry.source_hash,
    assessment_hash: "assessment-hash",
    dependencies: [],
    dependency_summary: { total: 0, ready: 0, attention: 0 },
    runtime_ready: true,
    runtime_ready_scope: "agent_dependencies",
  },
} as unknown as AgentImportRecord;

function project(): ProjectSummaryResponse {
  return {
    schema_version: "1.0",
    project_id: "project-1",
    root_path: "/tmp/project-1",
    name: "Local Project",
    description: "",
    pinned: false,
    pinned_at: null,
    indexed_at: "2026-09-20T00:00:00Z",
    manifest_hash: "manifest-hash",
    default_agent_id: null,
    agent_count: 0,
    agents: [],
  };
}

function renderCommunity(section: CommunitySection = "discover", detail = true, starred = section === "starred", account: CommunityAccount | null = null) {
  const localApi = {
    listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project()] }),
    analyzeAgentImport: vi.fn().mockResolvedValue(importRecord),
    applyAgentImport: vi.fn().mockResolvedValue({ import: importRecord, agent: { agent_id: "local-agent-1" } } as unknown as AgentImportApplyResponse),
  } as unknown as LocalProjectApi;
  const communityApi = {
    hasRefreshEvidence: vi.fn().mockReturnValue(Boolean(account)),
    me: vi.fn().mockResolvedValue(account),
    listRegistryAgents: vi.fn().mockResolvedValue([entry]),
    getRegistryAgent: vi.fn().mockResolvedValue(entry),
    listRegistryAgentVersions: vi.fn().mockResolvedValue([entry]),
    listMyRegistryAgents: vi.fn().mockResolvedValue([entry]),
    listStarredRegistryAgents: vi.fn().mockResolvedValue(starred ? [entry] : []),
    starRegistryAgent: vi.fn().mockResolvedValue({ starred: true, star_count: 2, review_count: 0, average_rating: 0 }),
    unstarRegistryAgent: vi.fn().mockResolvedValue({ starred: false, star_count: 0, review_count: 0, average_rating: 0 }),
    downloadRegistryAgent: vi.fn().mockResolvedValue(new Blob(["source"])),
    listRegistryReviews: vi.fn().mockResolvedValue({ reviews: [] }),
    getRegistryStarStatus: vi.fn().mockResolvedValue({ starred: false, star_count: 1, review_count: 0, average_rating: 0 }),
  } as unknown as CommunityApi;
  render(<ThemeProvider><AuthProvider api={communityApi}><ProjectWorkspaceProvider api={localApi}><CommunityPage section={section} {...(detail ? { owner: entry.owner_handle, slug: entry.slug, versionId: entry.version } : {})} /></ProjectWorkspaceProvider></AuthProvider></ThemeProvider>);
  return { localApi, communityApi };
}

describe("Community Agent import confirmation", () => {
  it("keeps Project unchanged through preview and creates a Draft only after explicit confirmation", async () => {
    const user = userEvent.setup();
    const { localApi, communityApi } = renderCommunity();

    await screen.findByRole("heading", { name: "Meeting Summary", level: 2 });
    await user.click(screen.getByRole("button", { name: "Preview import" }));
    expect(await screen.findByText("Local import preview")).toBeInTheDocument();
    expect(localApi.analyzeAgentImport).toHaveBeenCalledWith(expect.any(File), {
      owner_handle: entry.owner_handle,
      slug: entry.slug,
      version: entry.version,
      source_hash: entry.source_hash,
    }, "project-1");
    expect(localApi.applyAgentImport).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Confirm and create local Draft" }));
    await waitFor(() => expect(localApi.applyAgentImport).toHaveBeenCalledWith(importRecord.import_id, {
      project_id: "project-1",
      confirm: true,
    }));
    expect(window.location.hash).toContain("local-agent-1");
    expect(communityApi.downloadRegistryAgent).toHaveBeenCalledWith(entry.owner_handle, entry.slug, entry.version);
  });

  it("loads Published and Starred from account-owned Community endpoints", async () => {
    const user = userEvent.setup();
    const published = renderCommunity("published", false);
    expect(await screen.findByText("Meeting Summary")).toBeInTheDocument();
    expect(published.communityApi.listMyRegistryAgents).toHaveBeenCalled();
    cleanup();

    const starred = renderCommunity("starred", false);
    expect(await screen.findByText("Meeting Summary")).toBeInTheDocument();
    expect(starred.communityApi.listStarredRegistryAgents).toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Unstar" }));
    expect(starred.communityApi.unstarRegistryAgent).toHaveBeenCalledWith(entry.owner_handle, entry.slug, entry.version);
    expect(await screen.findByText("No starred releases yet")).toBeInTheDocument();
  });

  it("renders Creator Center on Mine with real KPI and action cards", async () => {
    const user = userEvent.setup();
    const account = {
      id: "account-1",
      email: "alice@example.com",
      handle: "veyra-alice",
      display_name: "Alice",
      avatar_url: "/community-api/api/v1/avatars/account-1",
    };
    const { communityApi } = renderCommunity("mine", false, false, account);

    expect(await screen.findByRole("heading", { name: "Alice", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("Account connected")).toBeInTheDocument();
    expect(screen.getByText("@veyra-alice")).toBeInTheDocument();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    expect(document.querySelector(".community-creator-avatar img")).toHaveAttribute("src", account.avatar_url);
    expect(communityApi.listMyRegistryAgents).toHaveBeenCalled();

    const metrics = await screen.findByLabelText("Creator overview");
    expect(metrics).toHaveTextContent("Published");
    expect(metrics).toHaveTextContent("In review");
    expect(metrics).toHaveTextContent("Rejected");
    expect(metrics).toHaveTextContent("Total stars");
    expect(metrics).toHaveTextContent("1");

    expect(screen.getByText("2 live publish lanes")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Project/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Workflow/i })).toBeDisabled();
    expect(await screen.findByText("Nothing needs attention")).toBeInTheDocument();
    expect(await screen.findByText(/Total stars: 1/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View all/i })).toHaveAttribute("href", "#/community/published");

    await user.click(screen.getByRole("button", { name: /^Agent/i }));
    expect(await screen.findByText("Publish a local Agent as an immutable version")).toBeInTheDocument();
  });
});

describe("Community Discover Star state", () => {
  it("restores the account Star state from the real Starred list after refresh", async () => {
    const user = userEvent.setup();
    const { communityApi } = renderCommunity("discover", false);

    const starButton = await screen.findByRole("button", { name: "Star" });
    expect(communityApi.listStarredRegistryAgents).toHaveBeenCalled();

    await user.click(starButton);
    expect(communityApi.starRegistryAgent).toHaveBeenCalledWith(entry.owner_handle, entry.slug, entry.version);
    expect(await screen.findByRole("button", { name: "Unstar" })).toBeInTheDocument();

    vi.mocked(communityApi.listStarredRegistryAgents).mockResolvedValue([entry]);
    await user.type(screen.getByRole("textbox"), "Meeting");
    expect(await screen.findByRole("button", { name: "Unstar" })).toBeInTheDocument();
  });

  it("uses the same saved Star state on Published as Discover", async () => {
    const { communityApi } = renderCommunity("published", false, true);

    expect(await screen.findByRole("button", { name: "Unstar" })).toBeInTheDocument();
    expect(communityApi.listStarredRegistryAgents).toHaveBeenCalled();
  });
});
