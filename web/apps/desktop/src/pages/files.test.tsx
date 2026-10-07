import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProjectFileRecord, ProjectSummaryResponse } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../api/project-workspace";
import type { LocalProjectApi } from "../api/local-client";
import { FilesPage, ProjectFilesPanel } from "./files";
import { projectFileId } from "../features/projects/agent-tree";

function project(overrides: Partial<ProjectSummaryResponse> = {}): ProjectSummaryResponse {
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
    ...overrides,
  };
}

function file(path: string, kind: ProjectFileRecord["kind"] = "resource"): ProjectFileRecord {
  return { path, kind, byte_length: 12 };
}

function renderPage(api: LocalProjectApi, fileId?: string, projectId?: string) {
  return render(
    <ThemeProvider>
      <ProjectWorkspaceProvider api={api}>
        <FilesPage fileId={fileId} projectId={projectId} />
      </ProjectWorkspaceProvider>
    </ThemeProvider>,
  );
}

afterEach(() => cleanup());

describe("FilesPage", () => {
  it("clears the previous file when switching preview identity, including a failed new preview", async () => {
    let rejectPreview: (cause: Error) => void = () => {};
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project()] }),
      listProjectFiles: vi.fn().mockResolvedValue({ schema_version: "1.0", project_id: "project-1", files: [file("assets/a.csv", "asset"), file("assets/b.csv", "asset")] }),
      getProjectFile: vi.fn().mockImplementation((_id: string, path: string) => path === "assets/a.csv"
        ? Promise.resolve({ schema_version: "1.0", project_id: "project-1", path, kind: "asset", byte_length: 12, sha256: "a".repeat(64), text: "only-file-A" })
        : new Promise((_resolve, reject) => { rejectPreview = reject; })),
    } as unknown as LocalProjectApi;
    const view = renderPage(api, projectFileId("project-1", "assets/a.csv"));
    await screen.findByText("only-file-A");
    view.rerender(<ThemeProvider><ProjectWorkspaceProvider api={api}><FilesPage fileId={projectFileId("project-1", "assets/b.csv")} /></ProjectWorkspaceProvider></ThemeProvider>);
    await waitFor(() => expect(screen.queryByText("only-file-A")).not.toBeInTheDocument());
    rejectPreview(new Error("file-B-unavailable"));
    await screen.findByText("file-B-unavailable");
    expect(screen.queryByRole("link", { name: "Open Agent Studio" })).not.toBeInTheDocument();
  });

  it("requires an explicit target in the global list and refreshes only that Project after importing", async () => {
    const summaries = [project(), project({ project_id: "project-2", name: "Other Project" })];
    const imported: ProjectFileRecord[] = [];
    const materialize = vi.fn(async (id: string, input: { file: File; relative_path: string }) => {
      imported.push(file(input.relative_path, "asset"));
      return { schema_version: "1.0", project_id: id, status: "materialized", relative_path: input.relative_path, sha256: "a".repeat(64), size_bytes: input.file.size };
    });
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: summaries }),
      listProjectFiles: vi.fn(async (id: string) => ({ schema_version: "1.0", project_id: id, files: id === "project-2" ? [...imported] : [] })),
      materializeProjectFile: materialize,
    } as unknown as LocalProjectApi;
    renderPage(api);

    const target = await screen.findByRole("combobox", { name: "Save to Project" });
    expect(target).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Import Files" })).not.toBeInTheDocument();
    fireEvent.change(target, { target: { value: "project-2" } });
    const csv = new File(["order_id,amount\r\nDEMO-1,10.00\r\n"], "orders.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText("Choose files to import"), { target: { files: [csv] } });

    await screen.findByText("1 imported, 0 failed.");
    expect(materialize).toHaveBeenCalledWith("project-2", expect.objectContaining({ file: csv, relative_path: "assets/orders.csv" }));
    expect(screen.getByRole("link", { name: /orders.csv assets\/orders.csv asset/ })).toHaveAttribute("href", `#/files/${encodeURIComponent(projectFileId("project-2", "assets/orders.csv"))}`);
  });

  it("fixes the importer scope on a Project files route", async () => {
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project(), project({ project_id: "project-2" })] }),
      listProjectFiles: vi.fn().mockResolvedValue({ schema_version: "1.0", project_id: "project-2", files: [] }),
      materializeProjectFile: vi.fn(),
    } as unknown as LocalProjectApi;
    renderPage(api, undefined, "project-2");

    await screen.findByRole("button", { name: "Import Files" });
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(api.listProjectFiles).toHaveBeenCalledWith("project-2");
    expect(api.listProjectFiles).not.toHaveBeenCalledWith("project-1");
  });

  it("imports into ProjectFilesPanel and updates its indexed list", async () => {
    const indexed: ProjectFileRecord[] = [];
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project()] }),
      listProjectFiles: vi.fn(async () => ({ schema_version: "1.0", project_id: "project-1", files: [...indexed] })),
      materializeProjectFile: vi.fn(async (id: string, input: { file: File; relative_path: string }) => {
        indexed.push(file(input.relative_path, "asset"));
        return { schema_version: "1.0", project_id: id, status: "materialized", relative_path: input.relative_path, sha256: "a".repeat(64), size_bytes: input.file.size };
      }),
    } as unknown as LocalProjectApi;
    render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ProjectFilesPanel projectId="project-1" projectName="Indexed Project" /></ProjectWorkspaceProvider></ThemeProvider>);
    await screen.findByText("No Project files yet");

    fireEvent.change(screen.getByLabelText("Choose files to import"), { target: { files: [new File(["demo"], "notes.txt")] } });

    await waitFor(() => expect(screen.getByRole("link", { name: /notes.txt assets\/notes.txt asset/ })).toBeInTheDocument());
    expect(screen.getByText("1 Files")).toBeInTheDocument();
  });

  it("keeps an imported panel listing when its initial request returns late", async () => {
    let finishInitial!: (value: { schema_version: string; project_id: string; files: ProjectFileRecord[] }) => void;
    const indexed: ProjectFileRecord[] = [];
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project()] }),
      listProjectFiles: vi.fn(async () => ({ schema_version: "1.0", project_id: "project-1", files: [...indexed] })).mockImplementationOnce(() => new Promise((resolve) => { finishInitial = resolve; })),
      materializeProjectFile: vi.fn(async (id: string, input: { file: File; relative_path: string }) => {
        indexed.push(file(input.relative_path, "asset"));
        return { schema_version: "1.0", project_id: id, status: "materialized", relative_path: input.relative_path, sha256: "a".repeat(64), size_bytes: input.file.size };
      }),
    } as unknown as LocalProjectApi;
    render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ProjectFilesPanel projectId="project-1" projectName="Indexed Project" /></ProjectWorkspaceProvider></ThemeProvider>);
    fireEvent.change(screen.getByLabelText("Choose files to import"), { target: { files: [new File(["demo"], "notes.txt")] } });
    await screen.findByText("1 imported, 0 failed.");

    finishInitial({ schema_version: "1.0", project_id: "project-1", files: [] });

    await waitFor(() => expect(screen.getByText("1 Files")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /notes.txt assets\/notes.txt asset/ })).toBeInTheDocument();
  });

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

  it("offers a Project file as a prefilled Agent Studio input", async () => {
    const summary = project({
      default_agent_id: "agent-1",
      agent_count: 1,
      agents: [{ agent_id: "agent-1", slug: "reader", name: "Reader", description: "", pinned: false, source_path: "agents/reader/agent.vagent.yaml", source_file_hash: "hash" }],
    });
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

    const link = await screen.findByRole("link", { name: "Open Agent Studio" });
    expect(link).toHaveAttribute("href", "#/projects/project-1/agents/agent-1/design?file=resources%2Fnote.md");
  });
});
