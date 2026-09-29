import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProjectSummaryResponse } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../api/project-workspace";
import type { LocalProjectApi } from "../api/local-client";
import { takePendingFactoryPrompt } from "../features/agents/chat/pending-factory-prompt";
import { NewChatPage } from "./new-chat";

const alpha: ProjectSummaryResponse = {
  schema_version: "1.0",
  project_id: "project-1",
  root_path: "/tmp/project-1",
  name: "Alpha",
  description: "",
  pinned: false,
  pinned_at: null,
  indexed_at: "2026-08-28T00:00:00Z",
  manifest_hash: "hash",
  default_agent_id: "agent-1",
  agent_count: 1,
  agents: [{ agent_id: "agent-1", slug: "reviewer", name: "Reviewer", description: "", pinned: false, source_path: "agents/reviewer/agent.vagent.yaml", source_file_hash: "hash" }],
};

function apiFor(projects: ProjectSummaryResponse[]): LocalProjectApi {
  return {
    listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects }),
    createProject: vi.fn().mockResolvedValue({
      ...alpha,
      project_id: "created-project",
      name: "Created Project",
      root_path: "/tmp/created-project",
      default_agent_id: null,
      agent_count: 0,
      agents: [],
    }),
    getProject: vi.fn().mockImplementation(async (projectId: string) => projects.find((item) => item.project_id === projectId) ?? alpha),
  } as unknown as LocalProjectApi;
}

function renderLanding(api: LocalProjectApi) {
  return render(
    <ThemeProvider>
      <ProjectWorkspaceProvider api={api}>
        <NewChatPage />
      </ProjectWorkspaceProvider>
    </ThemeProvider>,
  );
}

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  window.location.hash = "";
});

describe("NewChatPage", () => {
  it("creates a Project and keeps the prompt for that conversation", async () => {
    const api = apiFor([]);
    const user = userEvent.setup();
    renderLanding(api);
    await user.type(await screen.findByRole("textbox", { name: "Message" }), "Build a researcher");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(api.createProject).toHaveBeenCalledWith({ description: "" }));
    expect(window.location.hash).toBe("#/projects/created-project/chat");
    expect(takePendingFactoryPrompt()).toBe("Build a researcher");
  });

  it("opens an existing Project chat as soon as that Project is chosen", async () => {
    const api = apiFor([alpha]);
    const user = userEvent.setup();
    renderLanding(api);
    await user.click(await screen.findByRole("button", { name: "Choose project" }));
    await user.click(await screen.findByRole("option", { name: /^Alpha/ }));
    expect(api.createProject).not.toHaveBeenCalled();
    expect(window.location.hash).toBe("#/projects/project-1/chat");
    expect(takePendingFactoryPrompt()).toBeUndefined();
  });

  it("opens Builder with the existing Agent focus, not its Runtime conversation", async () => {
    const api = apiFor([alpha]);
    const user = userEvent.setup();
    renderLanding(api);
    await user.click(await screen.findByRole("button", { name: "Choose project" }));
    await user.click(await screen.findByRole("option", { name: /Reviewer/ }));
    expect(api.createProject).not.toHaveBeenCalled();
    expect(window.location.hash).toBe("#/projects/project-1/chat?target=agent:agent-1");
    expect(takePendingFactoryPrompt()).toBeUndefined();
  });

  it("does not create a fixture Project during landing bootstrap", async () => {
    const api = apiFor([]);
    renderLanding(api);
    await screen.findByRole("textbox", { name: "Message" });
    expect(api.createProject).not.toHaveBeenCalled();
  });
});
