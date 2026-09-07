import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentRunResponse, ProjectSummaryResponse } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../api/project-workspace";
import type { LocalProjectApi } from "../api/local-client";
import { RunsPage } from "./runs";

function project(): ProjectSummaryResponse {
  return {
    schema_version: "1.0",
    project_id: "project-1",
    root_path: "/tmp/project-1",
    name: "Indexed Project",
    description: "",
    pinned: false,
    pinned_at: null,
    indexed_at: "2026-08-28T00:00:00Z",
    manifest_hash: "hash",
    default_agent_id: null,
    agent_count: 1,
    agents: [{ agent_id: "agent-1", slug: "reviewer", name: "Review Companion", description: "", pinned: false, source_path: "agents/reviewer/agent.vagent.yaml", source_file_hash: "agent-hash" }],
  };
}

function run(): AgentRunResponse {
  return {
    schema_version: "1.0",
    run_id: "run-live-1",
    project_id: "project-1",
    agent_id: "agent-1",
    version_id: "version-1",
    status: "verified",
    result: { result: "ok" },
    error: null,
    created_at: "2026-08-28T10:00:00Z",
    finished_at: "2026-08-28T10:00:18Z",
  };
}

function renderPage(api: LocalProjectApi, projectId?: string) {
  return render(
    <ThemeProvider>
      <ProjectWorkspaceProvider api={api}>
        <RunsPage projectId={projectId} />
      </ProjectWorkspaceProvider>
    </ThemeProvider>,
  );
}

afterEach(() => cleanup());

describe("RunsPage", () => {
  it("lists durable Runtime runs instead of fixture rows", async () => {
    const summary = project();
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [summary] }),
      listAgentRuns: vi.fn().mockResolvedValue({ schema_version: "1.0", runs: [run()] }),
      listWorkflowRuns: vi.fn().mockResolvedValue({ schema_version: "1.0", runs: [] }),
    } as unknown as LocalProjectApi;
    renderPage(api, "project-1");
    expect(await screen.findByText("Review Companion")).toBeInTheDocument();
    expect(screen.getByText("run-live-1")).toBeInTheDocument();
    expect(screen.queryByText("Release Check")).not.toBeInTheDocument();
    expect(screen.queryByText("run-1042")).not.toBeInTheDocument();
    expect(api.listAgentRuns).toHaveBeenCalledWith("project-1", "agent-1");
  });

  it("shows an empty state when the Project has no runs", async () => {
    const summary = project();
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [summary] }),
      listAgentRuns: vi.fn().mockResolvedValue({ schema_version: "1.0", runs: [] }),
      listWorkflowRuns: vi.fn().mockResolvedValue({ schema_version: "1.0", runs: [] }),
    } as unknown as LocalProjectApi;
    renderPage(api, "project-1");
    expect(await screen.findByText("No runs yet")).toBeInTheDocument();
    expect(screen.queryByText("Release Room")).not.toBeInTheDocument();
  });
});
