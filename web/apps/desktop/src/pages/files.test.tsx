import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProjectFileRecord, ProjectSummaryResponse } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../api/project-workspace";
import type { LocalProjectApi } from "../api/local-client";
import { FilesPage } from "./files";
import { projectFileId } from "../features/projects/agent-tree";

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
    agent_count: 0,
    agents: [],
  };
}

function file(path: string, kind: ProjectFileRecord["kind"] = "resource"): ProjectFileRecord {
  return { path, kind, byte_length: 12 };
}

function renderPage(api: LocalProjectApi, fileId?: string) {
  return render(
    <ThemeProvider>
      <ProjectWorkspaceProvider api={api}>
        <FilesPage fileId={fileId} />
      </ProjectWorkspaceProvider>
    </ThemeProvider>,
  );
}

afterEach(() => cleanup());

describe("FilesPage", () => {
  it("lists indexed Project files instead of fixture rows", async () => {
    const summary = project();
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [summary] }),
      listProjectFiles: vi.fn().mockResolvedValue({
        schema_version: "1.0",
        project_id: "project-1",
        files: [file("project.vproject.yaml", "manifest"), file("resources/note.md")],
      }),
    } as unknown as LocalProjectApi;
    renderPage(api);
    expect(await screen.findByText("resources/note.md")).toBeInTheDocument();
    expect(screen.queryByText("review-agent.vagent.yaml")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /note.md/ })).toHaveAttribute(
      "href",
      `#/files/${encodeURIComponent(projectFileId("project-1", "resources/note.md"))}`,
    );
  });

  it("previews UTF-8 content for one indexed file", async () => {
    const summary = project();
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [summary] }),
      listProjectFiles: vi.fn().mockResolvedValue({ schema_version: "1.0", project_id: "project-1", files: [] }),
      getProjectFile: vi.fn().mockResolvedValue({
        schema_version: "1.0",
        project_id: "project-1",
        path: "resources/note.md",
        kind: "resource",
        byte_length: 5,
        text: "hello",
      }),
    } as unknown as LocalProjectApi;
    renderPage(api, projectFileId("project-1", "resources/note.md"));
    expect(await screen.findByText("hello")).toBeInTheDocument();
    expect(screen.getByText("resource")).toBeInTheDocument();
  });
});
