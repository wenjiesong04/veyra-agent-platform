import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProjectSummaryResponse } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../api/project-workspace";
import type { LocalProjectApi } from "../api/local-client";
import { ProjectDetailPage } from "./project-detail";

function project(overrides: Partial<ProjectSummaryResponse> = {}): ProjectSummaryResponse {
  return {
    schema_version: "1.0",
    project_id: "project-1",
    root_path: "/tmp/project-1",
    name: "Team Project",
    description: "Collaboration",
    pinned: false,
    pinned_at: null,
    indexed_at: "2026-08-28T00:00:00Z",
    manifest_hash: "hash",
    default_agent_id: "parent",
    agent_count: 3,
    agents: [
      { agent_id: "parent", slug: "parent", name: "Parent", description: "", pinned: true, source_path: "agents/parent/agent.vagent.yaml", source_file_hash: "a" },
      { agent_id: "child", slug: "child", name: "Child", description: "", pinned: false, source_path: "agents/child/agent.vagent.yaml", source_file_hash: "b", parent_agent_id: "parent" },
      { agent_id: "grand", slug: "grand", name: "Grand", description: "", pinned: false, source_path: "agents/grand/agent.vagent.yaml", source_file_hash: "c", parent_agent_id: "child" },
    ],
    ...overrides,
  };
}

function renderPage(api: LocalProjectApi) {
  return render(
    <ThemeProvider>
      <ProjectWorkspaceProvider api={api}>
        <ProjectDetailPage projectId="project-1" />
      </ProjectWorkspaceProvider>
    </ThemeProvider>,
  );
}

afterEach(() => cleanup());

describe("ProjectDetailPage", () => {
  it.each(["en", "zh"] as const)("offers a scoped create-in-chat link for an empty Project in %s without sending a request", async (locale) => {
    window.localStorage.setItem("veyra.language", locale);
    const summary = project({ agents: [], agent_count: 0, default_agent_id: null });
    const submitBuilderTurn = vi.fn();
    const createFactorySession = vi.fn();
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [summary] }), getProject: vi.fn().mockResolvedValue(summary), submitBuilderTurn, createFactorySession } as unknown as LocalProjectApi;
    renderPage(api);
    const action = await screen.findByRole("link", { name: locale === "zh" ? "用对话创建 Agent" : "Create an Agent in chat" });
    expect(action).toHaveAttribute("href", "#/projects/project-1/chat");
    action.focus();
    expect(action).toHaveFocus();
    expect(submitBuilderTurn).not.toHaveBeenCalled();
    expect(createFactorySession).not.toHaveBeenCalled();
  });

  it("renders a nested Agent file tree and parent_agent_id collaboration edges", async () => {
    window.localStorage.setItem("veyra.language", "en");
    const summary = project();
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [summary] }),
      getProject: vi.fn().mockResolvedValue(summary),
      revealProject: vi.fn().mockResolvedValue({ schema_version: "1.0", status: "revealed", root_path: "/tmp/project-1" }),
      listProjectFiles: vi.fn().mockResolvedValue({
        schema_version: "1.0",
        project_id: "project-1",
        files: [{ path: "README.md", kind: "readme", byte_length: 12 }],
      }),
    } as unknown as LocalProjectApi;
    renderPage(api);
    expect(await screen.findByText("agents/grand/agent.vagent.yaml")).toBeInTheDocument();
    expect(screen.getByText("grand child-of child")).toBeInTheDocument();
    expect(screen.getByText("child child-of parent")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /README.md/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show Project Location" })).toBeInTheDocument();
  });
});
