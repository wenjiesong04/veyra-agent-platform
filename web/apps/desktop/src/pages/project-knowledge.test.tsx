import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentSource, ProjectSummaryResponse } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../api/project-workspace";
import type { LocalProjectApi } from "../api/local-client";
import { ProjectKnowledgePage } from "./project-knowledge";

const source = {
  schema_version: "1.0",
  agentspec_version: "26.1",
  component_type: "Flow",
  agent_id: "agent-1",
  slug: "reviewer",
  name: "Reviewer",
  description: "",
  inputs: { request: "string" },
  outputs: { result: "string" },
  nodes: [{ id: "start", component_type: "Start" }, { id: "out", component_type: "Output", output_name: "result" }],
  transitions: [{ from: "start", port: "next", to: "out" }],
  extensions: { veyra: { runtime_profile: "guarded", secret_refs: [], permissions: { network_hosts: [], tools: [], filesystem_read_roots: [], filesystem_write_roots: [], shell_workspace_only: false }, verification: { required: false, checks: [] } } },
  ui: { positions: { start: { x: 0, y: 0 }, out: { x: 200, y: 0 } } },
  lock: {},
} as AgentSource;

const project: ProjectSummaryResponse = {
  schema_version: "1.0",
  project_id: "project-1",
  root_path: "/tmp/project-1",
  name: "Project",
  description: "",
  pinned: false,
  pinned_at: null,
  indexed_at: "2026-01-01T00:00:00Z",
  manifest_hash: "hash",
  default_agent_id: "agent-1",
  agent_count: 1,
  agents: [{ agent_id: "agent-1", slug: "reviewer", name: "Reviewer", description: "", pinned: false, source_path: "agents/reviewer/agent.vagent.yaml", source_file_hash: "agent-hash" }],
  knowledge: [{ knowledge_id: "knowledge-1", slug: "brand", name: "Brand", description: "", version: "1.0.0", source_path: "knowledge/brand/document.md", source_file_hash: "b".repeat(64) }],
  knowledge_count: 1,
};

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

describe("ProjectKnowledgePage", () => {
  it("binds a sidebar Knowledge document to a selected Agent", async () => {
    const saveDraft = vi.fn().mockResolvedValue({ source });
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      getProject: vi.fn().mockResolvedValue(project),
      getKnowledge: vi.fn().mockResolvedValue({ ...project.knowledge![0], text: "Use recyclable paper." }),
      getDraft: vi.fn().mockResolvedValue({ source, revision: 2, etag: "etag-2" }),
      saveDraft,
    } as unknown as LocalProjectApi;
    const user = userEvent.setup();

    render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ProjectKnowledgePage projectId="project-1" knowledgeId="knowledge-1" /></ProjectWorkspaceProvider></ThemeProvider>);
    await user.click(await screen.findByRole("button", { name: "Bind and open Studio" }));

    await waitFor(() => expect(saveDraft).toHaveBeenCalled());
    expect(saveDraft.mock.calls[0]?.[2]).toEqual(expect.objectContaining({ expected_revision: 2, source: expect.objectContaining({ lock: { "knowledge-1@1.0.0": "b".repeat(64) } }) }));
    expect(window.location.hash).toBe("#/projects/project-1/agents/agent-1/design");
  });
});
