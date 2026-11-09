import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentSource, KnowledgeDocumentResponse, KnowledgeProcessing, ProjectSummaryResponse } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../api/project-workspace";
import { LocalApiClientError, type LocalProjectApi } from "../api/local-client";
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
  vi.restoreAllMocks();
  window.location.hash = "";
});

describe("ProjectKnowledgePage", () => {
  it.each<KnowledgeProcessing["index_status"]>(["not_indexed", "indexed", "stale", "failed"])("explicitly builds from %s without rebinding and reloads index truth", async (index_status) => {
    const processing: KnowledgeProcessing = { origin: "upload", filename: "thesis.txt", media_type: "text/plain", uploaded_content_hash: "c".repeat(64), content_hash: "c".repeat(64), ingest_status: "ingested", parse_status: "parsed", index_status, chunk_count: index_status === "indexed" ? 7 : null, failure_reason: index_status === "stale" ? "Content changed; explicitly rebuild" : index_status === "failed" ? "Knowledge index is invalid; explicitly rebuild the index." : null, updated_at: "2026-09-15T00:00:00Z" };
    const indexed = { ...project.knowledge![0], text: "Thesis", processing: { ...processing, index_status: "indexed", chunk_count: 2, failure_reason: null } };
    const buildKnowledgeIndex = vi.fn().mockResolvedValue(indexed);
    const getProject = vi.fn().mockResolvedValue({ ...project, knowledge: [{ ...project.knowledge![0], processing }] });
    const getKnowledge = vi.fn().mockResolvedValue({ ...project.knowledge![0], processing, text: "Thesis" });
    const saveDraft = vi.fn();
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      getProject, getKnowledge, buildKnowledgeIndex, saveDraft,
    } as unknown as LocalProjectApi;
    render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ProjectKnowledgePage projectId="project-1" knowledgeId="knowledge-1" /></ProjectWorkspaceProvider></ThemeProvider>);
    const action = await screen.findByRole("button", { name: index_status === "not_indexed" ? "Build index" : "Rebuild index" });
    expect(buildKnowledgeIndex).not.toHaveBeenCalled();
    if (index_status === "indexed") expect(screen.getByText("7")).toBeInTheDocument();
    if (index_status === "stale") {
      expect(screen.getByText("Content changed; explicitly rebuild")).toBeInTheDocument();
      expect(screen.getByText("Content changed; rebuild the index. The old index is no longer valid.")).toBeInTheDocument();
    }
    if (index_status === "failed") expect(screen.getByRole("alert")).toHaveTextContent(processing.failure_reason!);
    await userEvent.setup().click(action);
    expect(buildKnowledgeIndex).toHaveBeenCalledWith("project-1", "knowledge-1");
    expect(await screen.findByText("ingested / parsed / indexed")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(saveDraft).not.toHaveBeenCalled();
    expect(screen.queryByText("Content changed; explicitly rebuild")).not.toBeInTheDocument();
    getKnowledge.mockResolvedValue(indexed);
    await userEvent.setup().click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByText("ingested / parsed / indexed")).toBeInTheDocument();
    expect(buildKnowledgeIndex).toHaveBeenCalledTimes(1);
    expect(getKnowledge).toHaveBeenCalledTimes(2);
  });

  it("blocks duplicate builds and reads backend detail on a fresh mount", async () => {
    const processing: KnowledgeProcessing = { origin: "project_document", filename: "document.md", media_type: "text/markdown", uploaded_content_hash: null, content_hash: "b".repeat(64), ingest_status: "ingested", parse_status: "parsed", index_status: "not_indexed", chunk_count: null, failure_reason: null, updated_at: "2026-09-15T00:00:00Z" };
    const document: KnowledgeDocumentResponse = { ...project.knowledge![0], schema_version: "1.0", project_id: project.project_id, text: "Original preview", processing };
    const indexed: KnowledgeDocumentResponse = { ...document, text: "Backend build preview", processing: { ...processing, index_status: "indexed", chunk_count: 4 } };
    let finishBuild!: (value: KnowledgeDocumentResponse) => void;
    const buildKnowledgeIndex = vi.fn().mockImplementation(() => new Promise<KnowledgeDocumentResponse>((resolve) => { finishBuild = resolve; }));
    const getKnowledge = vi.fn().mockResolvedValue(document);
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      getProject: vi.fn().mockResolvedValue({ ...project, knowledge: [document] }),
      getKnowledge, buildKnowledgeIndex,
    } as unknown as LocalProjectApi;
    const page = <ThemeProvider><ProjectWorkspaceProvider api={api}><ProjectKnowledgePage projectId="project-1" knowledgeId="knowledge-1" /></ProjectWorkspaceProvider></ThemeProvider>;
    const view = render(page);
    const user = userEvent.setup();
    await user.dblClick(await screen.findByRole("button", { name: "Build index" }));
    expect(screen.getByRole("button", { name: "Building…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Refresh" })).toBeDisabled();
    expect(screen.getByText("ingested / parsed / not_indexed")).toBeInTheDocument();
    expect(screen.queryByText(/ingested \/ parsed \/ indexing/)).not.toBeInTheDocument();
    expect(buildKnowledgeIndex).toHaveBeenCalledTimes(1);
    finishBuild(indexed);
    expect(await screen.findByRole("button", { name: "Rebuild index" })).toBeEnabled();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("Backend build preview")).toBeInTheDocument();
    view.unmount();
    getKnowledge.mockResolvedValue({ ...indexed, processing: { ...indexed.processing!, chunk_count: 5 } });
    render(page);
    expect(await screen.findByRole("button", { name: "Rebuild index" })).toBeEnabled();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.queryByText("4")).not.toBeInTheDocument();
    expect(getKnowledge).toHaveBeenLastCalledWith("project-1", "knowledge-1");
    expect(buildKnowledgeIndex).toHaveBeenCalledTimes(1);
  });

  it("does not claim indexed when Build fails", async () => {
    const processing = { origin: "upload", filename: "thesis.txt", media_type: "text/plain", uploaded_content_hash: "c".repeat(64), content_hash: "c".repeat(64), ingest_status: "ingested", parse_status: "parsed", index_status: "not_indexed", chunk_count: null, failure_reason: null, updated_at: "2026-09-15T00:00:00Z" };
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      getProject: vi.fn().mockResolvedValue({ ...project, knowledge: [{ ...project.knowledge![0], processing }] }),
      getKnowledge: vi.fn().mockResolvedValue({ ...project.knowledge![0], processing, text: "Thesis" }),
      buildKnowledgeIndex: vi.fn().mockRejectedValue(new LocalApiClientError("Knowledge exceeds index size limit", { status: 422, code: "knowledge_index_too_large" })),
    } as unknown as LocalProjectApi;
    render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ProjectKnowledgePage projectId="project-1" knowledgeId="knowledge-1" /></ProjectWorkspaceProvider></ThemeProvider>);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Build index" }));
    expect(await screen.findByText("knowledge_index_too_large: Knowledge exceeds index size limit")).toBeInTheDocument();
    expect(screen.getByText("ingested / parsed / not_indexed")).toBeInTheDocument();
    expect(screen.queryByText("ingested / parsed / indexed")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Build index" })).toBeEnabled();
  });

  it("deletes only after success and uses the returned Project", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const deleteKnowledge = vi.fn().mockResolvedValue({ project: { ...project, knowledge: [], knowledge_count: 0 } });
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      getProject: vi.fn().mockResolvedValue(project), deleteKnowledge,
    } as unknown as LocalProjectApi;
    render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ProjectKnowledgePage projectId="project-1" /></ProjectWorkspaceProvider></ThemeProvider>);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Delete Brand" }));
    expect(deleteKnowledge).toHaveBeenCalledWith("project-1", "knowledge-1");
    expect(await screen.findByText("No Knowledge yet")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Brand/ })).not.toBeInTheDocument();
  });

  it.each(["knowledge_in_use", "local_internal_error"])("keeps the list on %s and explains the error", async (code) => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const deleteKnowledge = vi.fn().mockRejectedValue(new LocalApiClientError("Delete failed", { status: code === "knowledge_in_use" ? 409 : 500, code, details: { agent_id: "agent-1", name: "Reviewer", version_id: "version-1" } }));
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      getProject: vi.fn().mockResolvedValue(project), deleteKnowledge,
    } as unknown as LocalProjectApi;
    render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ProjectKnowledgePage projectId="project-1" /></ProjectWorkspaceProvider></ThemeProvider>);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Delete Brand" }));
    expect(await screen.findByText(code === "knowledge_in_use" ? /This Knowledge is still used by an Agent.*Reviewer.*version-1/ : "Delete failed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Brand/ })).toBeInTheDocument();
    expect(screen.queryByText("No Knowledge yet")).not.toBeInTheDocument();
  });

  it("uploads the selected file without binding and navigates to its real identity", async () => {
    const ingestKnowledge = vi.fn().mockResolvedValue({ ...project.knowledge![0], text: "Thesis" });
    const saveDraft = vi.fn();
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      getProject: vi.fn().mockResolvedValue(project), ingestKnowledge, saveDraft,
    } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ProjectKnowledgePage projectId="project-1" /></ProjectWorkspaceProvider></ThemeProvider>);
    const file = new File(["Thesis"], "thesis.txt", { type: "text/plain" });
    await user.upload(await screen.findByLabelText("Knowledge file"), file);
    await user.click(screen.getByRole("button", { name: "Upload and parse" }));
    await waitFor(() => expect(ingestKnowledge).toHaveBeenCalledWith("project-1", file));
    expect(saveDraft).not.toHaveBeenCalled();
    expect(window.location.hash).toBe("#/projects/project-1/knowledge/knowledge-1");
  });

  it("shows backend ingest facts without claiming retrieval indexing", async () => {
    const processing = { origin: "upload", filename: "thesis.txt", media_type: "text/plain", uploaded_content_hash: "c".repeat(64), content_hash: "c".repeat(64), ingest_status: "ingested", parse_status: "parsed", index_status: "not_indexed", failure_reason: null, updated_at: "2026-09-15T00:00:00Z" };
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      getProject: vi.fn().mockResolvedValue({ ...project, knowledge: [{ ...project.knowledge![0], processing }] }),
      getKnowledge: vi.fn().mockResolvedValue({ ...project.knowledge![0], processing, text: "Thesis" }),
    } as unknown as LocalProjectApi;
    render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ProjectKnowledgePage projectId="project-1" knowledgeId="knowledge-1" /></ProjectWorkspaceProvider></ThemeProvider>);
    expect(await screen.findByText("ingested / parsed / not_indexed")).toBeInTheDocument();
    expect(screen.getByText(/No retrieval index yet/)).toBeInTheDocument();
    expect(screen.getByText(/upload · thesis.txt/)).toBeInTheDocument();
  });

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
