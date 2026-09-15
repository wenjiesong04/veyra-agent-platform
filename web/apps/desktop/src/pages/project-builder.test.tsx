import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BuilderResolveRequest, EditProposal, EditTargetKind } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { LocalApiClientError, type LocalProjectApi } from "../api/local-client";
import { ProjectWorkspaceProvider, useProjectWorkspace } from "../api/project-workspace";
import { editAgent, editDraft, editProject, editProposal, editWorkflow } from "../test/edit-proposals";
import { ProjectChatPage } from "./project-chat";
import { StudioPage } from "./studio";

afterEach(() => { cleanup(); window.localStorage.clear(); window.location.hash = ""; });

function TreeProbe() {
  const { projects } = useProjectWorkspace();
  return <output aria-label="Project tree">{projects[0]?.agents[0]?.name}</output>;
}

function setup(kind: EditTargetKind = "agent", proposals: EditProposal[] = [], focused = true) {
  const source = kind === "agent" ? editAgent : editWorkflow;
  const project = { ...editProject, agent_count: 1, agents: [{ agent_id: "agent-1", slug: "review", name: "Review", description: "", pinned: false, source_path: "agents/review/agent.vagent.yaml", source_file_hash: "hash" }], workflows: [{ workflow_id: "workflow-1", slug: "review", name: "Review", description: "", source_path: "workflows/review/workflow.vworkflow.yaml", source_file_hash: "hash" }] };
  const getDraft = vi.fn().mockResolvedValue(editDraft(source));
  const validate = vi.fn().mockResolvedValue(editProposal(kind).validation);
  const api = {
    listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }),
    getProject: vi.fn().mockResolvedValue(project), getDraft, getWorkflowDraft: getDraft,
    validate, validateWorkflow: validate, saveDraft: vi.fn(), saveWorkflowDraft: vi.fn(),
    reloadDraft: vi.fn().mockResolvedValue(editDraft(source, 2)), reloadWorkflowDraft: vi.fn().mockResolvedValue(editDraft(source, 2)),
    listEditProposals: vi.fn().mockResolvedValue({ schema_version: "1.0", proposals }),
    createEditProposal: vi.fn().mockResolvedValue(editProposal(kind)),
    commandEditProposal: vi.fn().mockResolvedValue(editProposal(kind, { state: "rejected" })),
    resolveBuilderIntent: vi.fn().mockImplementation(async (_projectId: string, input: BuilderResolveRequest) => {
      const draft = await getDraft();
      return { schema_version: "1.0", intent: "edit", create_kind: null, status: "resolved", message: "I will propose a change to Review.", instruction: input.content, plan: ["Update the saved Draft"], targets: [{ kind, target_id: `${kind}-1`, name: "Review", revision: draft.revision, etag: draft.etag }] };
    }),
  };
  window.localStorage.setItem("veyra.language", "en");
  window.location.hash = `#/projects/project-1/chat${focused ? `?target=${kind}:${kind}-1` : ""}`;
  const wrapper = (child: React.ReactNode) => <ThemeProvider storageKey="builder-test"><ProjectWorkspaceProvider api={api as unknown as LocalProjectApi}><TreeProbe />{child}</ProjectWorkspaceProvider></ThemeProvider>;
  const page = render(wrapper(<ProjectChatPage projectId="project-1" />));
  return { api, source, project, page, wrapper };
}

async function ready() { await waitFor(() => expect(screen.getByRole("button", { name: "Refresh proposals" })).toBeEnabled()); }
async function propose() {
  await ready();
  fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "Rename the draft" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByRole("button", { name: "Confirm apply proposal" });
}

describe("Project Chat Builder", () => {
  it("adopts a same-project scope change before resolving the next message", async () => {
    const { api } = setup("agent", [], false);
    await screen.findByRole("textbox", { name: "Message" });
    fireEvent.click(screen.getByRole("button", { name: "Choose project" }));
    fireEvent.click(screen.getByRole("option", { name: /Review/ }));
    await ready();
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "Update its description" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(api.resolveBuilderIntent).toHaveBeenCalledWith("project-1", expect.objectContaining({ focus: { kind: "agent", target_id: "agent-1" } })));
    await screen.findByRole("button", { name: "Confirm apply proposal" });
    fireEvent.click(screen.getByRole("button", { name: "Choose project" }));
    expect(screen.getByRole("option", { name: /Review/ })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("option", { name: /^Project / }));
    await waitFor(() => expect(screen.queryByRole("complementary", { name: "Edit proposal" })).not.toBeInTheDocument());
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "Discuss this project" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(api.resolveBuilderIntent).toHaveBeenLastCalledWith("project-1", expect.objectContaining({ focus: null })));
  });

  it("keeps the original Chat layout and resolves natural language without a target picker", async () => {
    const { api } = setup("agent", [], false);
    await screen.findByRole("textbox", { name: "Message" });
    expect(document.querySelector(".agent-convo-hero")).toBeInTheDocument();
    expect(document.querySelector(".agent-convo-dock .agent-convo-composer")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Attach files" })).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Build target" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "Give Review a quality check" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Will modify: Agent · Review");
    expect(api.resolveBuilderIntent).toHaveBeenCalledWith("project-1", expect.objectContaining({ content: "Give Review a quality check", focus: null }));
    expect(document.querySelector(".agent-conversation.is-canvas > .agent-convo-canvas")).toBeInTheDocument();
    expect(api.commandEditProposal).not.toHaveBeenCalled();
  });

  it.each(["clarification", "unsupported", "discuss"])("keeps %s in Chat without proposing or creating", async (mode) => {
    const { api } = setup("agent", [], false);
    api.resolveBuilderIntent.mockResolvedValueOnce({ schema_version: "1.0", intent: mode === "discuss" ? "discuss" : "clarify", status: mode === "discuss" ? "resolved" : mode, create_kind: null, message: "Which Review do you mean?", instruction: "", plan: [], targets: [] });
    await screen.findByRole("textbox", { name: "Message" });
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "Change Review" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Which Review do you mean?");
    expect(api.createEditProposal).not.toHaveBeenCalled();
    expect(api.commandEditProposal).not.toHaveBeenCalled();
    if (mode === "clarification") {
      fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "The Agent" } });
      fireEvent.click(screen.getByRole("button", { name: "Send" }));
      await screen.findByText("Will modify: Agent · Review");
      expect(api.resolveBuilderIntent).toHaveBeenLastCalledWith("project-1", expect.objectContaining({ content: "The Agent", history: [{ role: "user", content: "Change Review" }, { role: "assistant", content: "Which Review do you mean?" }] }));
    }
  });

  it.each(["agent", "workflow"] as const)("proposes, applies, validates and undoes %s using real Draft reads", async (kind) => {
    const { api, source, project, page, wrapper } = setup(kind);
    await propose();
    expect(api.createEditProposal).toHaveBeenCalledWith("project-1", { target_kind: kind, target_id: `${kind}-1`, instruction: "Rename the draft", expected_revision: 1, expected_etag: '"etag-1"' });
    expect(screen.getByText("Source changes")).toBeInTheDocument();
    expect(screen.getByText("Permission changes")).toBeInTheDocument();
    expect(api.saveDraft).not.toHaveBeenCalled();
    expect(api.commandEditProposal).not.toHaveBeenCalled();
    api.commandEditProposal.mockResolvedValueOnce(editProposal(kind, { state: "applied", applied_revision: 2 }));
    api.getDraft.mockResolvedValue(editDraft({ ...source, name: "Server Draft" }, 2));
    api.getProject.mockResolvedValue({ ...project, agents: [{ ...project.agents[0], name: "Server Draft" }] });
    fireEvent.click(screen.getByRole("button", { name: "Confirm apply proposal" }));
    await screen.findByRole("region", { name: "Post-apply validation" });
    expect(api.validate).toHaveBeenCalledWith("project-1", `${kind}-1`);
    expect(screen.getByLabelText("Project tree")).toHaveTextContent("Server Draft");
    expect(api.commandEditProposal).toHaveBeenCalledWith("project-1", "proposal-1", { command: "apply", confirm: true });
    expect(screen.getByRole("link", { name: "Open real Canvas in Studio" })).toHaveAttribute("href", kind === "agent" ? "#/projects/project-1/agents/agent-1/design" : "#/projects/project-1/workflows/workflow-1");
    api.commandEditProposal.mockResolvedValueOnce(editProposal(kind, { state: "undone", applied_revision: 2 }));
    api.getDraft.mockResolvedValue(editDraft(source, 3));
    fireEvent.click(screen.getByRole("button", { name: "Confirm undo application" }));
    await screen.findByText(/Undone ·/);
    expect(api.validate).toHaveBeenCalledTimes(2);
    expect(api.saveDraft).not.toHaveBeenCalled();
    page.rerender(wrapper(<StudioPage projectId="project-1" {...(kind === "agent" ? { agentId: "agent-1" } : { workflowId: "workflow-1" })} />));
    fireEvent.click(await screen.findByRole("tab", { name: "Form" }));
    expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("Review");
    expect(screen.queryByRole("button", { name: "Propose edits" })).not.toBeInTheDocument();
  });

  it.each(["generate", "apply", "undo"] as const)("blocks on %s conflict and only resumes after explicit reload", async (action) => {
    const { api } = setup("agent", action === "generate" ? [] : [editProposal("agent", action === "undo" ? { state: "applied", applied_revision: 1 } : {})]);
    const failure = new LocalApiClientError("Draft conflict", { code: "draft_conflict", status: 409 });
    await ready();
    if (action === "generate") {
      api.createEditProposal.mockRejectedValueOnce(failure);
      fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "Change it" } });
      fireEvent.click(screen.getByRole("button", { name: "Send" }));
    } else {
      api.commandEditProposal.mockRejectedValueOnce(failure);
      fireEvent.click(screen.getByRole("button", { name: action === "apply" ? "Confirm apply proposal" : "Confirm undo application" }));
    }
    await screen.findByText("Draft conflict");
    expect(api.saveDraft).not.toHaveBeenCalled();
    expect(api.reloadDraft).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Reload Draft" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Reload Draft" })).not.toBeInTheDocument());
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "Propose again" } });
    api.getDraft.mockResolvedValue(editDraft(editAgent, 2));
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(api.createEditProposal).toHaveBeenLastCalledWith("project-1", expect.objectContaining({ expected_revision: 2, expected_etag: '"etag-2"' })));
  });

  it("allows stale rejection without touching or validating the Draft", async () => {
    const { api } = setup("agent", [editProposal("agent", { stale: true })]);
    await ready();
    expect(screen.getByRole("button", { name: "Confirm apply proposal" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Reject proposal" }));
    await screen.findByText(/Rejected ·/);
    expect(api.getDraft).toHaveBeenCalledTimes(1);
    expect(api.validate).not.toHaveBeenCalled();
    expect(api.saveDraft).not.toHaveBeenCalled();
  });

  it("refreshes the review baseline when resolution observes a newer saved Draft", async () => {
    const { api } = setup();
    await ready();
    api.getDraft.mockResolvedValue(editDraft(editAgent, 2));
    api.createEditProposal.mockResolvedValueOnce(editProposal("agent", { base_revision: 2, base_etag: '"etag-2"' }));
    await propose();
    await waitFor(() => expect(screen.getByRole("button", { name: "Confirm apply proposal" })).toBeEnabled());
    expect(api.createEditProposal).toHaveBeenCalledWith("project-1", expect.objectContaining({ expected_revision: 2, expected_etag: '"etag-2"' }));
    expect(api.commandEditProposal).not.toHaveBeenCalled();
    expect(api.reloadDraft).not.toHaveBeenCalled();
  });

  it("refreshes inventory when resolution finds an object added since Chat opened", async () => {
    const { api, project } = setup("workflow", [], false);
    api.getProject.mockResolvedValue({ ...project, workflows: [{ ...project.workflows[0], workflow_id: "workflow-new", name: "New workflow" }] });
    api.resolveBuilderIntent.mockResolvedValueOnce({ schema_version: "1.0", intent: "edit", create_kind: null, status: "resolved", message: "Will edit New workflow", instruction: "Update it", plan: [], targets: [{ kind: "workflow", target_id: "workflow-new", name: "New workflow", revision: 1, etag: '"etag-1"' }] });
    api.createEditProposal.mockResolvedValueOnce(editProposal("workflow", { target_id: "workflow-new" }));
    fireEvent.change(await screen.findByRole("textbox", { name: "Message" }), { target: { value: "Update New workflow" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Will modify: Workflow · New workflow");
    expect(api.createEditProposal).toHaveBeenCalledWith("project-1", expect.objectContaining({ target_id: "workflow-new" }));
    expect(api.commandEditProposal).not.toHaveBeenCalled();
  });

  it("does not claim validation when the post-apply Draft read fails", async () => {
    const { api } = setup("agent", [editProposal()]);
    await ready();
    api.commandEditProposal.mockResolvedValueOnce(editProposal("agent", { state: "applied", applied_revision: 2 }));
    api.getDraft.mockRejectedValueOnce(new Error("Draft unavailable"));
    fireEvent.click(screen.getByRole("button", { name: "Confirm apply proposal" }));
    await screen.findByText("Draft unavailable");
    expect(screen.getByRole("button", { name: "Reload Draft" })).toBeEnabled();
    expect(screen.queryByRole("region", { name: "Post-apply validation" })).not.toBeInTheDocument();
    expect(api.validate).not.toHaveBeenCalled();
    expect(api.saveDraft).not.toHaveBeenCalled();
  });
});
