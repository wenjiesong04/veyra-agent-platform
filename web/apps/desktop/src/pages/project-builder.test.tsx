import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BuilderConversationSnapshot, BuilderResolveRequest, EditProposal, EditTargetKind, FactorySession } from "@veyra/api-contracts";
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

function setup(kind: EditTargetKind = "agent", proposals: EditProposal[] = [], focused = true, locale: "zh" | "en" = "en") {
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
    createValidationRepairProposal: vi.fn(),
    addProjectResource: vi.fn(),
    commandEditProposal: vi.fn().mockResolvedValue(editProposal(kind, { state: "rejected" })),
    resolveBuilderIntent: vi.fn().mockImplementation(async (_projectId: string, input: BuilderResolveRequest) => {
      const draft = await getDraft();
      return { schema_version: "1.0", intent: "edit", create_kind: null, status: "resolved", message: "I will propose a change to Review.", instruction: input.content, plan: ["Update the saved Draft"], targets: [{ kind, target_id: `${kind}-1`, name: "Review", revision: draft.revision, etag: draft.etag }] };
    }),
  };
  window.localStorage.setItem("veyra.language", locale);
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
    await waitFor(() => expect(screen.queryByRole("complementary", { name: "Workbench" })).not.toBeInTheDocument());
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "Discuss this project" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(api.resolveBuilderIntent).toHaveBeenLastCalledWith("project-1", expect.objectContaining({ focus: null })));
  });

  it.each([
    ["en", "Message", "Send", "Thinking…"],
    ["zh", "消息", "发送", "正在思考…"],
  ] as const)("shows the sent message immediately while waiting for a Builder reply (%s)", async (locale, textbox, send, thinking) => {
    const { api } = setup("agent", [], false, locale);
    let finish!: (value: Awaited<ReturnType<NonNullable<LocalProjectApi["resolveBuilderIntent"]>>>) => void;
    api.resolveBuilderIntent.mockImplementationOnce(() => new Promise((resolve) => {
      finish = resolve;
    }));
    await screen.findByRole("textbox", { name: textbox });
    fireEvent.change(screen.getByRole("textbox", { name: textbox }), { target: { value: "Create a gift wrap agent" } });
    fireEvent.click(screen.getByRole("button", { name: send }));
    expect(await screen.findByText("Create a gift wrap agent")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: textbox })).toHaveValue("");
    expect(screen.getByText(thinking)).toBeInTheDocument();
    expect(document.querySelector(".agent-conversation.is-empty")).not.toBeInTheDocument();
    expect(screen.queryByText("I understood the request.")).not.toBeInTheDocument();
    finish({
      schema_version: "1.0",
      intent: "discuss",
      create_kind: null,
      status: "resolved",
      message: "I understood the request.",
      instruction: "",
      plan: [],
      targets: [],
    });
    expect(await screen.findByText("I understood the request.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText(thinking)).not.toBeInTheDocument());
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
    expect(document.querySelector(".agent-convo-column .builder-workspace-dock")).toBeInTheDocument();
    expect(api.commandEditProposal).not.toHaveBeenCalled();
  });

  it("uses the deterministic Project Resource proposal and shows pin, readiness, and permissions", async () => {
    const { api } = setup("agent");
    const knowledge = vi.fn().mockRejectedValue(new LocalApiClientError("No Knowledge match", { status: 422, code: "knowledge_mention_unresolved" }));
    const plan = {
      reference: "veyra.tool.filesystem.read@1.0.0",
      name: "Filesystem Read",
      bound_content_hash: "a".repeat(64),
      catalog_content_hash: "a".repeat(64),
      binding_status: "current" as const,
      readiness: "ready" as const,
      availability: "ready" as const,
      runtime_status: "supported" as const,
      required_permissions: {
        network_hosts: [],
        tools: ["veyra.tool.filesystem.read"],
        filesystem_read_roots: ["project"],
        filesystem_write_roots: [],
        shell_workspace_only: false,
      },
      blocking_reasons: [],
      project_resource_changed: false as const,
      automatic_upgrade: false as const,
    };
    const resource = vi.fn().mockResolvedValue(editProposal("agent", { instruction: "Let this Agent read Project files", resource_binding: plan }));
    Object.assign(api, { createKnowledgeBindingProposal: knowledge, createResourceBindingProposal: resource });
    api.resolveBuilderIntent.mockResolvedValueOnce({
      schema_version: "1.0",
      intent: "edit",
      create_kind: null,
      status: "resolved",
      message: "I will propose a capability change.",
      instruction: "Model-normalized text without a Resource identity",
      plan: ["Add file reading"],
      targets: [{ kind: "agent", target_id: "agent-1", name: "Review", revision: 1, etag: '"etag-1"' }],
    });
    await ready();
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "Let this Agent read Project files" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    const summary = await screen.findByRole("region", { name: "Project Resource binding" });
    expect(resource).toHaveBeenCalledWith("project-1", {
      agent_id: "agent-1",
      instruction: "Let this Agent read Project files",
      expected_revision: 1,
      expected_etag: '"etag-1"',
    });
    expect(within(summary).getByText(plan.reference)).toBeInTheDocument();
    expect(within(summary).getByText(plan.bound_content_hash)).toBeInTheDocument();
    expect(within(summary).getByText("Ready")).toBeInTheDocument();
    expect(within(summary).getByText(/filesystem_read_roots/)).toBeInTheDocument();
    expect(api.createEditProposal).not.toHaveBeenCalled();
    expect(api.commandEditProposal).not.toHaveBeenCalled();
  });

  it.each([
    ["resource_mention_ambiguous", "Several Project Resources match. Choose an exact version:"],
    ["resource_mention_unbound", "filesystem.read exists in the global Catalog but is not in this Project."],
  ])("shows %s without falling back to model-generated Resource identity", async (code, message) => {
    const { api } = setup("agent");
    Object.assign(api, {
      createKnowledgeBindingProposal: vi.fn().mockRejectedValue(new LocalApiClientError("No Knowledge match", { status: 422, code: "knowledge_mention_unresolved" })),
      createResourceBindingProposal: vi.fn().mockRejectedValue(new LocalApiClientError("Cannot select Resource", {
        status: 422,
        code,
        details: { candidates: "Filesystem Read (veyra.tool.filesystem.read@1.0.0)" },
      })),
    });
    await ready();
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "Let this Agent read Project files" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText(new RegExp(message.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
    expect(api.createEditProposal).not.toHaveBeenCalled();
    expect(api.commandEditProposal).not.toHaveBeenCalled();
  });

  it("falls through an unrelated Resource intent to the existing Knowledge adapter", async () => {
    const { api } = setup("agent");
    const resource = vi.fn().mockRejectedValue(new LocalApiClientError("No Resource match", { status: 422, code: "resource_mention_unresolved" }));
    const knowledge = vi.fn().mockResolvedValue(editProposal("agent", {
      instruction: "Use thesis notes",
      knowledge_binding: {
        reference: "01a0ae99-45da-755f-862f-f78823dcf760@1.0.0",
        name: "Thesis notes",
        source_file_hash: "a".repeat(64),
        index_status: "indexed",
        chunk_count: 1,
        failure_reason: null,
        runnable: true,
        required_action: null,
      },
    }));
    Object.assign(api, { createResourceBindingProposal: resource, createKnowledgeBindingProposal: knowledge });
    await ready();
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "Use thesis notes" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByRole("region", { name: "Knowledge binding" });
    expect(resource).toHaveBeenCalledTimes(1);
    expect(knowledge).toHaveBeenCalledTimes(1);
    expect(api.createEditProposal).not.toHaveBeenCalled();
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
    await screen.findByText("Validated");
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

  it("shows typed post-apply validation failure and a repair proposal without a traceback", async () => {
    const failed = {
      schema_version: "1.0" as const,
      valid: true,
      source_hash: "a".repeat(64),
      behavior_hash: "b".repeat(64),
      lock_hash: "c".repeat(64),
      runtime_ready: false,
      runtime_ready_scope: "agent_dependencies" as const,
      dependency_summary: { total: 1, ready: 0, attention: 1 },
      dependencies: [{
        reference: "veyra.tool.filesystem.read@1.0.0",
        kind: "tool" as const,
        name: "Filesystem Read",
        status: "lock_mismatch" as const,
        detail: "Agent lock does not match the Project pinned content hash.",
        locked_hash: "b".repeat(64),
        bound_content_hash: "a".repeat(64),
        used_by: ["bound_tool"],
        bound_by: [],
      }],
    };
    const repair = editProposal("agent", {
      instruction: "Repair lock_mismatch for veyra.tool.filesystem.read@1.0.0",
      proposal_id: "repair-1",
      validation_repair: {
        code: "lock_mismatch",
        kind: "tool",
        reference: "veyra.tool.filesystem.read@1.0.0",
        name: "Filesystem Read",
        repairable: true,
        automatic_upgrade: false,
        project_resource_changed: false,
        locked_hash: "b".repeat(64),
        bound_content_hash: "a".repeat(64),
        target_kind: "agent",
        impact: "Align the Agent lock to the current Project pin.",
      },
    });
    const { api } = setup("agent", [editProposal()]);
    api.validate.mockResolvedValue(failed);
    api.createValidationRepairProposal.mockResolvedValue(repair);
    await ready();
    api.commandEditProposal.mockResolvedValueOnce(editProposal("agent", { state: "applied", applied_revision: 2 }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm apply proposal" }));
    await screen.findByText("Validation failed");
    expect(screen.getByText("Resource lock mismatch")).toBeInTheDocument();
    expect(screen.getByText(/Expected Project pin:/)).toBeInTheDocument();
    expect(screen.queryByText(/Traceback/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Create repair proposal" }));
    await screen.findByRole("region", { name: "Validation repair" });
    expect(api.createValidationRepairProposal).toHaveBeenCalledWith("project-1", {
      agent_id: "agent-1",
      reference: "veyra.tool.filesystem.read@1.0.0",
      code: "lock_mismatch",
      expected_revision: 1,
      expected_etag: '"etag-1"',
    });
    expect(api.saveDraft).not.toHaveBeenCalled();
    api.commandEditProposal.mockResolvedValueOnce({ ...repair, state: "applied", applied_revision: 3 });
    api.validate.mockResolvedValue({ ...failed, valid: true, runtime_ready: true, dependency_summary: { total: 1, ready: 1, attention: 0 }, dependencies: [{ ...failed.dependencies[0], status: "ready", detail: "ok" }] });
    fireEvent.click(screen.getByRole("button", { name: "Confirm apply proposal" }));
    await screen.findByText("Validated");
  });

  it("explains a non-repairable unbound Tool instead of adding a Project Resource", async () => {
    const failed = {
      schema_version: "1.0" as const,
      valid: true,
      source_hash: "a".repeat(64),
      behavior_hash: "b".repeat(64),
      lock_hash: "c".repeat(64),
      runtime_ready: false,
      runtime_ready_scope: "agent_dependencies" as const,
      dependency_summary: { total: 1, ready: 0, attention: 1 },
      dependencies: [{
        reference: "veyra.tool.filesystem.read@1.0.0",
        kind: "tool" as const,
        name: "Filesystem Read",
        status: "resource_unbound" as const,
        detail: "Tool is not bound to this Project.",
        used_by: ["bound_tool"],
        bound_by: [],
      }],
    };
    const { api } = setup("agent", [editProposal()]);
    api.validate.mockResolvedValue(failed);
    api.createValidationRepairProposal.mockReset();
    api.addProjectResource.mockReset();
    await ready();
    api.commandEditProposal.mockResolvedValueOnce(editProposal("agent", { state: "applied", applied_revision: 2 }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm apply proposal" }));
    await screen.findByText("Validation failed");
    expect(screen.getByText("Not bound to this Project")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create repair proposal" })).not.toBeInTheDocument();
    expect(api.createValidationRepairProposal).not.toHaveBeenCalled();
    expect(api.addProjectResource).not.toHaveBeenCalled();
  });

  it("offers a permission repair without expanding grants before confirm", async () => {
    const failed = {
      schema_version: "1.0" as const,
      valid: true,
      source_hash: "a".repeat(64),
      behavior_hash: "b".repeat(64),
      lock_hash: "c".repeat(64),
      runtime_ready: false,
      runtime_ready_scope: "agent_dependencies" as const,
      dependency_summary: { total: 1, ready: 0, attention: 1 },
      dependencies: [{
        reference: "veyra.tool.filesystem.read@1.0.0",
        kind: "tool" as const,
        name: "Filesystem Read",
        status: "permission_denied" as const,
        detail: "Missing required Tool permission.",
        required_permissions: {
          network_hosts: [],
          tools: ["veyra.tool.filesystem.read"],
          filesystem_read_roots: ["${project.root}"],
          filesystem_write_roots: [],
          shell_workspace_only: false,
        },
        used_by: ["bound_tool"],
        bound_by: [],
      }],
    };
    const repair = editProposal("agent", {
      instruction: "Repair permission_denied for veyra.tool.filesystem.read@1.0.0",
      proposal_id: "repair-permissions",
      validation_repair: {
        code: "permission_denied",
        kind: "tool",
        reference: "veyra.tool.filesystem.read@1.0.0",
        name: "Filesystem Read",
        repairable: true,
        automatic_upgrade: false,
        project_resource_changed: false,
        required_permissions: failed.dependencies[0].required_permissions,
        target_kind: "agent",
        impact: "Grant only the missing required permissions.",
      },
    });
    const { api } = setup("agent", [editProposal()]);
    api.validate.mockResolvedValue(failed);
    api.createValidationRepairProposal.mockResolvedValue(repair);
    await ready();
    api.commandEditProposal.mockResolvedValueOnce(editProposal("agent", { state: "applied", applied_revision: 2 }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm apply proposal" }));
    await screen.findByText("Permission missing");
    fireEvent.click(screen.getByRole("button", { name: "Create repair proposal" }));
    await screen.findByRole("region", { name: "Validation repair" });
    expect(api.createValidationRepairProposal).toHaveBeenCalledWith("project-1", {
      agent_id: "agent-1",
      reference: "veyra.tool.filesystem.read@1.0.0",
      code: "permission_denied",
      expected_revision: 1,
      expected_etag: '"etag-1"',
    });
    expect(api.saveDraft).not.toHaveBeenCalled();
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

function factoryReviewSession(): FactorySession {
  return {
    schema_version: "1.0",
    session_id: "session-1",
    project_id: "project-1",
    state: "review",
    ready: true,
    next_prompt: "Review the Blueprint.",
    resource_plan: [],
    blueprint: { schema_version: "1.0", goal: "Wrap gifts" },
    diagnostics: [],
    missing_capabilities: [],
    candidate: { name: "礼物包装顾问", slug: "gift-wrapping-advisor" },
    run_availability: "requires_configuration",
    executes_drafts: false,
    revision: 2,
    created_at: "2026-09-18T00:00:00Z",
    updated_at: "2026-09-18T00:00:00Z",
    messages: [],
  };
}

function durableSnapshot(overrides: Partial<BuilderConversationSnapshot> = {}): BuilderConversationSnapshot {
  const conversation = {
    conversation_id: "conv-1",
    project_id: "project-1",
    title: "帮我生成礼物包装 Agent",
    status: "active",
    created_at: "2026-09-18T00:00:00Z",
    updated_at: "2026-09-18T00:00:01Z",
    last_activity_at: "2026-09-18T00:00:01Z",
    last_operation_status: "failed" as const,
    ...overrides.conversation,
  };
  return {
    schema_version: "1.0",
    conversation,
    messages: overrides.messages ?? [
      { message_id: "m-user", conversation_id: conversation.conversation_id, sequence: 0, role: "user", kind: "user", content: "帮我生成礼物包装 Agent", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:00Z" },
      { message_id: "m-fail", conversation_id: conversation.conversation_id, sequence: 1, role: "system", kind: "failure", content: "Agent 结构生成失败\nStage: blueprint_generation\nProvider: Kimi K3\nHTTP: 400", operation_id: "op-1", payload: { error_code: "factory_request_invalid", http_status: "400" }, created_at: "2026-09-18T00:00:01Z" },
    ],
    operations: overrides.operations ?? [
      { operation_id: "op-1", conversation_id: conversation.conversation_id, kind: "create_agent", status: "failed", retry_of: null, error_code: "factory_request_invalid", proposal_id: null, run_id: null, factory_session_id: null, created_at: "2026-09-18T00:00:00Z", updated_at: "2026-09-18T00:00:01Z", diagnostic: { http_status: "400" }, has_request: true, target_kind: "agent", events: [], receipts: [] },
    ],
    resolution: overrides.resolution ?? null,
    factory_session: overrides.factory_session === undefined ? null : overrides.factory_session,
  };
}

describe("Durable Project Chat", () => {
  it("persists the turn on the server without sending client history as truth", async () => {
    const { api } = setup("agent", [], false);
    const snapshot = durableSnapshot({
      conversation: { ...durableSnapshot().conversation, last_operation_status: "waiting" },
      messages: [
        { message_id: "m-user", conversation_id: "conv-1", sequence: 0, role: "user", kind: "user", content: "帮我生成礼物包装 Agent", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:00Z" },
        { message_id: "m-asst", conversation_id: "conv-1", sequence: 1, role: "assistant", kind: "assistant", content: "我理解为创建一个新的礼物包装 Agent。", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:01Z" },
        { message_id: "m-plan", conversation_id: "conv-1", sequence: 2, role: "assistant", kind: "plan", content: "收集礼物类型\n输出包装方案", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:01Z" },
      ],
      operations: [{ ...durableSnapshot().operations[0], status: "waiting", error_code: null }],
      resolution: { schema_version: "1.0", intent: "create", create_kind: "agent", status: "resolved", message: "我理解为创建一个新的礼物包装 Agent。", instruction: "Create a gift wrap agent", plan: ["收集礼物类型"], targets: [] },
      factory_session: factoryReviewSession(),
    });
    const submitBuilderTurn = vi.fn().mockResolvedValue(snapshot);
    Object.assign(api, {
      submitBuilderTurn,
      getBuilderConversation: vi.fn().mockResolvedValue(snapshot),
      recordBuilderConversation: vi.fn().mockResolvedValue(snapshot),
    });
    await screen.findByRole("textbox", { name: "Message" });
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "帮我生成礼物包装 Agent" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("我理解为创建一个新的礼物包装 Agent。");
    expect(submitBuilderTurn).toHaveBeenCalledWith("project-1", expect.objectContaining({
      content: "帮我生成礼物包装 Agent",
      locale: "en",
      retry_of: undefined,
    }), expect.objectContaining({ onEvent: expect.any(Function) }));
    expect(submitBuilderTurn.mock.calls[0][1]).not.toHaveProperty("history");
    expect(api.resolveBuilderIntent).not.toHaveBeenCalled();
    expect(screen.queryByText("收集礼物类型")).not.toBeInTheDocument();
    expect(screen.getByText(/Build Agent/)).toBeInTheDocument();
  });

  it("restores the persisted conversation after remount without a spinner", async () => {
    const snapshot = durableSnapshot();
    const { api, wrapper } = setup("agent", [], false);
    const getBuilderConversation = vi.fn().mockResolvedValue(snapshot);
    Object.assign(api, {
      submitBuilderTurn: vi.fn(),
      getBuilderConversation,
    });
    cleanup();
    window.location.hash = "#/projects/project-1/chat?conversation=conv-1";
    render(wrapper(<ProjectChatPage projectId="project-1" conversationId="conv-1" />));
    expect(await screen.findByText("帮我生成礼物包装 Agent")).toBeInTheDocument();
    expect(screen.getByText(/Agent 结构生成失败/)).toBeInTheDocument();
    expect(getBuilderConversation).toHaveBeenCalledWith("project-1", "conv-1");
    expect(screen.queryByText("Thinking…")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled();
  });

  it("does not render harness receipts as chat bubbles and restores Build details", async () => {
    const snapshot = durableSnapshot({
      conversation: { ...durableSnapshot().conversation, last_operation_status: "waiting" },
      messages: [
        { message_id: "m-user", conversation_id: "conv-1", sequence: 0, role: "user", kind: "user", content: "帮我生成礼物包装 Agent", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:00Z" },
        { message_id: "m-asst", conversation_id: "conv-1", sequence: 1, role: "assistant", kind: "assistant", content: "我理解为创建一个新的礼物包装 Agent。", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:01Z" },
      ],
      operations: [{
        ...durableSnapshot().operations[0],
        status: "waiting",
        error_code: null,
        receipts: [{
          receipt_id: "receipt-1",
          operation_id: "op-1",
          conversation_id: "conv-1",
          project_id: "project-1",
          invocation_kind: "semantic_plan",
          sequence: 2,
          status: "success",
          started_at: "2026-09-18T00:00:02Z",
          completed_at: "2026-09-18T00:00:10Z",
          harness_mode: "create_agent",
          policy_version: "builder-policy-v1",
          policy_hash: "policyhashpolicyhashpolicyhashpolicyhashpolicyhashpolicyhashpol",
          output_contract: "AgentSemanticPlanV1",
          schema_version: "1.0",
          schema_hash: "schemahashschemahashschemahashschemahashschemahashschemahashsch",
          structured_mode: "strict_json_schema",
          project_snapshot_hash: "projecthashprojecthashprojecthashprojecthashprojecthashprojectha",
          catalog_snapshot_hash: "cataloghashcataloghashcataloghashcataloghashcataloghashcatalogha",
          included_categories: ["project_agents_metadata", "catalog_capabilities"],
          excluded_categories: ["knowledge_contents", "project_file_contents", "secrets"],
          history_message_count: 1,
          context_size_bytes: 100,
          request_size_bytes: 200,
          provider_id: "moonshot",
          model: "kimi-k3",
          endpoint_kind: "chat_completions",
          provider_profile_status: "known",
          provider_profile_source: "probe",
          schema_profile: "mfjs",
          failure_stage: null,
          error_code: null,
          safe_provider_error_type: null,
          safe_provider_error_param: null,
          provider_request_id: null,
          fallback_from: null,
          fallback_to: null,
        }],
      }],
      factory_session: factoryReviewSession(),
    });
    const { api, wrapper } = setup("agent", [], false);
    Object.assign(api, {
      submitBuilderTurn: vi.fn(),
      getBuilderConversation: vi.fn().mockResolvedValue(snapshot),
    });
    cleanup();
    window.location.hash = "#/projects/project-1/chat?conversation=conv-1";
    render(wrapper(<ProjectChatPage projectId="project-1" conversationId="conv-1" />));
    expect(await screen.findByText("帮我生成礼物包装 Agent")).toBeInTheDocument();
    expect(screen.queryByText(/Moonshot/)).not.toBeInTheDocument();
    expect(screen.queryByText(/policyhashpolicyhash/)).not.toBeInTheDocument();
    const activity = screen.getByRole("button", { name: /Build Agent/ });
    if (activity.getAttribute("aria-expanded") === "false") fireEvent.click(activity);
    fireEvent.click(screen.getByRole("button", { name: /Build details/ }));
    expect(screen.getByText("Moonshot · Kimi K3")).toBeInTheDocument();
  });

  it("retries as a new operation on the same conversation", async () => {
    const failed = durableSnapshot();
    const retried = durableSnapshot({
      conversation: { ...failed.conversation, last_operation_status: "waiting" },
      messages: [
        ...failed.messages,
        { message_id: "m-asst", conversation_id: "conv-1", sequence: 2, role: "assistant", kind: "assistant", content: "我理解为创建一个新的礼物包装 Agent。", operation_id: "op-2", payload: {}, created_at: "2026-09-18T00:00:02Z" },
      ],
      operations: [
        failed.operations[0],
        { ...failed.operations[0], operation_id: "op-2", status: "waiting", retry_of: "op-1", error_code: null },
      ],
      factory_session: factoryReviewSession(),
      resolution: { schema_version: "1.0", intent: "create", create_kind: "agent", status: "resolved", message: "我理解为创建一个新的礼物包装 Agent。", instruction: "Create a gift wrap agent", plan: [], targets: [] },
    });
    const { api, wrapper } = setup("agent", [], false);
    const submitBuilderTurn = vi.fn().mockResolvedValue(retried);
    Object.assign(api, {
      submitBuilderTurn,
      getBuilderConversation: vi.fn().mockResolvedValue(failed),
      recordBuilderConversation: vi.fn().mockResolvedValue(retried),
    });
    cleanup();
    render(wrapper(<ProjectChatPage projectId="project-1" conversationId="conv-1" />));
    await screen.findByRole("button", { name: "Retry" });
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(submitBuilderTurn).toHaveBeenCalledWith("project-1", expect.objectContaining({
      conversation_id: "conv-1",
      retry_of: "op-1",
    }), expect.objectContaining({ onEvent: expect.any(Function) })));
    expect(submitBuilderTurn.mock.calls[0][1].content).toBeUndefined();
    expect(await screen.findByText("我理解为创建一个新的礼物包装 Agent。")).toBeInTheDocument();
    expect(screen.getByText(/Agent 结构生成失败/)).toBeInTheDocument();
  });

  it("puts copy and time on every message and retry only on the last turn", async () => {
    const failed = durableSnapshot();
    const reviewed = durableSnapshot({
      conversation: { ...failed.conversation, last_operation_status: "waiting" },
      messages: [
        failed.messages[0],
        failed.messages[1],
        { message_id: "m-asst", conversation_id: "conv-1", sequence: 2, role: "assistant", kind: "assistant", content: "我理解为创建一个新的礼物包装 Agent。", operation_id: "op-2", payload: {}, created_at: "2026-09-18T00:00:02Z" },
        { message_id: "m-plan", conversation_id: "conv-1", sequence: 3, role: "assistant", kind: "plan", content: "收集礼物类型\n输出包装方案", operation_id: "op-2", payload: {}, created_at: "2026-09-18T00:00:02Z" },
      ],
      operations: [
        failed.operations[0],
        { ...failed.operations[0], operation_id: "op-2", status: "waiting", retry_of: "op-1", error_code: null, factory_session_id: "session-1" },
      ],
      factory_session: factoryReviewSession(),
    });
    const { api, wrapper } = setup("agent", [], false);
    Object.assign(api, {
      submitBuilderTurn: vi.fn(),
      getBuilderConversation: vi.fn().mockResolvedValue(reviewed),
    });
    cleanup();
    window.location.hash = "#/projects/project-1/chat?conversation=conv-1";
    render(wrapper(<ProjectChatPage projectId="project-1" conversationId="conv-1" />));
    expect(await screen.findByText("我理解为创建一个新的礼物包装 Agent。")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Copy" })).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(screen.queryByText("系统")).not.toBeInTheDocument();
  });

  it("opens the workbench from server review state instead of a fake timer", async () => {
    let finish!: (value: BuilderConversationSnapshot) => void;
    const snapshot = durableSnapshot({
      conversation: { ...durableSnapshot().conversation, last_operation_status: "waiting" },
      messages: [
        { message_id: "m-user", conversation_id: "conv-1", sequence: 0, role: "user", kind: "user", content: "帮我生成礼物包装 Agent", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:00Z" },
        { message_id: "m-asst", conversation_id: "conv-1", sequence: 1, role: "assistant", kind: "assistant", content: "我理解为创建一个新的礼物包装 Agent。", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:01Z" },
      ],
      operations: [{ ...durableSnapshot().operations[0], status: "waiting", error_code: null, factory_session_id: "session-1" }],
      factory_session: factoryReviewSession(),
      resolution: { schema_version: "1.0", intent: "create", create_kind: "agent", status: "resolved", message: "我理解为创建一个新的礼物包装 Agent。", instruction: "Create", plan: ["收集礼物类型"], targets: [] },
    });
    const { api } = setup("agent", [], false);
    Object.assign(api, {
      submitBuilderTurn: vi.fn().mockImplementation(() => new Promise((resolve) => { finish = resolve; })),
      getBuilderConversation: vi.fn(),
      recordBuilderConversation: vi.fn().mockResolvedValue(snapshot),
    });
    await screen.findByRole("textbox", { name: "Message" });
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "帮我生成礼物包装 Agent" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("帮我生成礼物包装 Agent")).toBeInTheDocument();
    expect(screen.getByText("Thinking…")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Review proposal" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create Draft" })).not.toBeInTheDocument();
    finish(snapshot);
    expect(await screen.findByRole("heading", { name: "Review proposal" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create Draft" })).toBeEnabled();
  });

  it("records Reject without creating an Agent", async () => {
    const reviewed = durableSnapshot({
      conversation: { ...durableSnapshot().conversation, last_operation_status: "waiting" },
      messages: [
        { message_id: "m-user", conversation_id: "conv-1", sequence: 0, role: "user", kind: "user", content: "帮我生成礼物包装 Agent", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:00Z" },
        { message_id: "m-asst", conversation_id: "conv-1", sequence: 1, role: "assistant", kind: "assistant", content: "我理解为创建一个新的礼物包装 Agent。", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:01Z" },
      ],
      operations: [{ ...durableSnapshot().operations[0], status: "waiting", error_code: null, factory_session_id: "session-1" }],
      factory_session: factoryReviewSession(),
      resolution: { schema_version: "1.0", intent: "create", create_kind: "agent", status: "resolved", message: "我理解为创建一个新的礼物包装 Agent。", instruction: "Create", plan: [], targets: [] },
    });
    const rejected = durableSnapshot({
      ...reviewed,
      conversation: { ...reviewed.conversation, last_operation_status: "rejected" },
      messages: [
        ...reviewed.messages,
        { message_id: "m-reject", conversation_id: "conv-1", sequence: 2, role: "system", kind: "reject", content: "Rejected the Blueprint. No Agent was created.", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:02Z" },
      ],
      operations: [{ ...reviewed.operations[0], status: "rejected" }],
    });
    const { api } = setup("agent", [], false);
    const recordBuilderConversation = vi.fn().mockResolvedValue(rejected);
    const applyFactoryDraft = vi.fn();
    Object.assign(api, {
      submitBuilderTurn: vi.fn().mockResolvedValue(reviewed),
      recordBuilderConversation,
      applyFactoryDraft,
    });
    await screen.findByRole("textbox", { name: "Message" });
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "帮我生成礼物包装 Agent" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByRole("button", { name: "Reject" });
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(recordBuilderConversation).toHaveBeenCalledWith("project-1", "conv-1", expect.objectContaining({
      kind: "reject",
      operation_id: "op-1",
    })));
    expect(applyFactoryDraft).not.toHaveBeenCalled();
    expect(await screen.findByText("Rejected")).toBeInTheDocument();
    expect(screen.queryByText("Rejected the Blueprint. No Agent was created.")).not.toBeInTheDocument();
  });

  it("applies the Semantic Plan candidate name and shows one result", async () => {
    const reviewed = durableSnapshot({
      conversation: { ...durableSnapshot().conversation, last_operation_status: "waiting" },
      messages: [
        { message_id: "m-user", conversation_id: "conv-1", sequence: 0, role: "user", kind: "user", content: "创建一个中英文翻译 Agent。", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:00Z" },
        { message_id: "m-asst", conversation_id: "conv-1", sequence: 1, role: "assistant", kind: "assistant", content: "我会创建一个中英文翻译 Agent。", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:01Z" },
      ],
      operations: [{ ...durableSnapshot().operations[0], status: "waiting", error_code: null, factory_session_id: "session-1" }],
      factory_session: factoryReviewSession(),
      resolution: { schema_version: "1.0", intent: "create", create_kind: "agent", status: "resolved", message: "我会创建一个中英文翻译 Agent。", instruction: "Create", plan: [], targets: [] },
    });
    const created = {
      session: { ...factoryReviewSession(), state: "completed" as const },
      agent: { agent_id: "agent-new", name: "礼物包装顾问", slug: "gift-wrapping-advisor" },
    };
    const finished = durableSnapshot({
      conversation: { ...reviewed.conversation, last_operation_status: "succeeded" },
      messages: [
        ...reviewed.messages,
        { message_id: "m-result", conversation_id: "conv-1", sequence: 2, role: "assistant", kind: "result", content: "礼物包装顾问已经创建并通过结构验证。", operation_id: "op-1", payload: { agent_id: "agent-new", agent_name: "礼物包装顾问" }, created_at: "2026-09-18T00:00:03Z" },
      ],
      operations: [{ ...reviewed.operations[0], status: "succeeded" }],
      factory_session: created.session,
    });
    const { api } = setup("agent", [], false);
    const recordBuilderConversation = vi.fn().mockResolvedValue(finished);
    const applyFactoryDraft = vi.fn().mockResolvedValue(created);
    Object.assign(api, {
      submitBuilderTurn: vi.fn().mockResolvedValue(reviewed),
      recordBuilderConversation,
      applyFactoryDraft,
      getDraft: vi.fn().mockResolvedValue({ source: { agent_id: "agent-new" }, revision: 1, etag: '"etag"' }),
      validate: vi.fn().mockResolvedValue({ valid: true, source_hash: "a".repeat(64) }),
    });
    await screen.findByRole("textbox", { name: "Message" });
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "创建一个中英文翻译 Agent。" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByRole("button", { name: "Create Draft" });
    fireEvent.click(screen.getByRole("button", { name: "Create Draft" }));
    await waitFor(() => expect(applyFactoryDraft).toHaveBeenCalledWith("project-1", "session-1", { confirm: true, name: "礼物包装顾问" }));
    expect(await screen.findByText("礼物包装顾问已经创建并通过结构验证。")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Open Studio" })[0]).toHaveAttribute("href", "#/projects/project-1/agents/agent-new/design");
    expect(screen.queryByRole("button", { name: "Create Draft" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(screen.getAllByText("礼物包装顾问已经创建并通过结构验证。")).toHaveLength(1);
  });

  it("shows a typed missing-capability blocker without creating an Agent", async () => {
    const snapshot = durableSnapshot({
      conversation: { ...durableSnapshot().conversation, last_operation_status: "failed", title: "GitHub Issue Agent" },
      messages: [
        { message_id: "m-user", conversation_id: "conv-1", sequence: 0, role: "user", kind: "user", content: "创建一个可以调用 GitHub 读取仓库 Issue 的 Agent。", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:00Z" },
        { message_id: "m-asst", conversation_id: "conv-1", sequence: 1, role: "assistant", kind: "assistant", content: "我会创建一个读取 GitHub Issue 的 Agent。", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:01Z" },
      ],
      operations: [{
        ...durableSnapshot().operations[0],
        status: "failed",
        error_code: "factory_missing_capability",
        factory_session_id: "session-1",
        events: [
          { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.operation.started", label: "Started", summary: "", facts: {}, created_at: "2026-09-18T00:00:00Z" },
          { event_id: "e2", operation_id: "op-1", sequence: 1, kind: "builder.intent.resolved", label: "Understanding request", summary: "", facts: { intent: "create", create_kind: "agent" }, created_at: "2026-09-18T00:00:01Z" },
          { event_id: "e3", operation_id: "op-1", sequence: 2, kind: "builder.capabilities.resolved", label: "Resolving capabilities", summary: "", facts: { missing_count: "1" }, created_at: "2026-09-18T00:00:02Z" },
          { event_id: "e4", operation_id: "op-1", sequence: 3, kind: "builder.operation.failed", label: "Failed", summary: "Requested capability is not bound", facts: {}, created_at: "2026-09-18T00:00:03Z" },
        ],
      }],
      factory_session: {
        ...factoryReviewSession(),
        state: "missing_capability",
        blueprint: null,
        candidate: { name: "GitHub Issue Agent" },
        missing_capabilities: [{
          kind: "tool",
          reference: "read GitHub issues",
          reason: "Requested capability is not bound to this Project",
          proposal: { action: "quarantined_resource_draft", executable: false },
        }],
        run_availability: "unavailable",
      },
    });
    const { api, wrapper } = setup("agent", [], false);
    Object.assign(api, {
      submitBuilderTurn: vi.fn(),
      getBuilderConversation: vi.fn().mockResolvedValue(snapshot),
      addProjectResource: vi.fn(),
    });
    cleanup();
    window.location.hash = "#/projects/project-1/chat?conversation=conv-1";
    render(wrapper(<ProjectChatPage projectId="project-1" conversationId="conv-1" />));
    expect(await screen.findByRole("heading", { name: "Missing capabilities" })).toBeInTheDocument();
    expect(screen.getByText(/read GitHub issues/)).toBeInTheDocument();
    expect(screen.queryByText(/invalid missing-capability/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Create Draft" })).not.toBeInTheDocument();
    expect(api.addProjectResource).not.toHaveBeenCalled();
  });

  it("collapses a completed Activity after refresh", async () => {
    const completed = durableSnapshot({
      conversation: { ...durableSnapshot().conversation, last_operation_status: "succeeded", title: "礼物包装顾问" },
      messages: [
        { message_id: "m-user", conversation_id: "conv-1", sequence: 0, role: "user", kind: "user", content: "创建一个中英文翻译 Agent。", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:00Z" },
        { message_id: "m-asst", conversation_id: "conv-1", sequence: 1, role: "assistant", kind: "assistant", content: "我会创建一个中英文翻译 Agent。", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:01Z" },
        { message_id: "m-result", conversation_id: "conv-1", sequence: 2, role: "assistant", kind: "result", content: "礼物包装顾问已经创建并通过结构验证。", operation_id: "op-1", payload: { agent_id: "agent-new" }, created_at: "2026-09-18T00:00:03Z" },
      ],
      operations: [{
        ...durableSnapshot().operations[0],
        status: "succeeded",
        error_code: null,
        events: [
          { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.operation.started", label: "Started", summary: "", facts: {}, created_at: "2026-09-18T00:00:00Z" },
          { event_id: "e2", operation_id: "op-1", sequence: 1, kind: "builder.proposal.ready", label: "Preparing review", summary: "", facts: {}, created_at: "2026-09-18T00:00:01Z" },
          { event_id: "e3", operation_id: "op-1", sequence: 2, kind: "builder.operation.completed", label: "Completed", summary: "", facts: {}, created_at: "2026-09-18T00:00:03Z" },
        ],
      }],
    });
    const { api, wrapper } = setup("agent", [], false);
    Object.assign(api, {
      submitBuilderTurn: vi.fn(),
      getBuilderConversation: vi.fn().mockResolvedValue(completed),
    });
    cleanup();
    window.location.hash = "#/projects/project-1/chat?conversation=conv-1";
    render(wrapper(<ProjectChatPage projectId="project-1" conversationId="conv-1" />));
    const toggle = await screen.findByRole("button", { name: /Build Agent · completed/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("系统")).not.toBeInTheDocument();
  });

  it("keeps a running Activity expanded on the current server stage", async () => {
    const running = durableSnapshot({
      conversation: { ...durableSnapshot().conversation, last_operation_status: "in_progress" },
      messages: [
        { message_id: "m-user", conversation_id: "conv-1", sequence: 0, role: "user", kind: "user", content: "创建一个中英文翻译 Agent。", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:00Z" },
        { message_id: "m-asst", conversation_id: "conv-1", sequence: 1, role: "assistant", kind: "assistant", content: "我会创建一个中英文翻译 Agent。", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:01Z" },
      ],
      operations: [{
        ...durableSnapshot().operations[0],
        status: "in_progress",
        error_code: null,
        events: [
          { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.operation.started", label: "Started", summary: "", facts: {}, created_at: "2026-09-18T00:00:00Z" },
          { event_id: "e2", operation_id: "op-1", sequence: 1, kind: "builder.intent.resolved", label: "Understanding request", summary: "", facts: { intent: "create", create_kind: "agent" }, created_at: "2026-09-18T00:00:01Z" },
          { event_id: "e3", operation_id: "op-1", sequence: 2, kind: "builder.semantic_plan.started", label: "Planning Agent", summary: "", facts: {}, created_at: "2026-09-18T00:00:02Z" },
        ],
      }],
    });
    const { api, wrapper } = setup("agent", [], false);
    Object.assign(api, {
      submitBuilderTurn: vi.fn(),
      getBuilderConversation: vi.fn().mockResolvedValue(running),
    });
    cleanup();
    window.location.hash = "#/projects/project-1/chat?conversation=conv-1";
    render(wrapper(<ProjectChatPage projectId="project-1" conversationId="conv-1" />));
    const toggle = await screen.findByRole("button", { name: /Building Agent/ });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByText("Planning Agent").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(screen.queryByText("系统")).not.toBeInTheDocument();
  });

  it("starts an explicit Test Agent run from the completed workbench", async () => {
    const completed = durableSnapshot({
      conversation: { ...durableSnapshot().conversation, last_operation_status: "succeeded", title: "中英文翻译 Agent" },
      messages: [
        { message_id: "m-user", conversation_id: "conv-1", sequence: 0, role: "user", kind: "user", content: "创建一个中英文翻译 Agent。", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:00Z" },
        { message_id: "m-asst", conversation_id: "conv-1", sequence: 1, role: "assistant", kind: "assistant", content: "我会创建一个中英文翻译 Agent。", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:01Z" },
        { message_id: "m-result", conversation_id: "conv-1", sequence: 2, role: "assistant", kind: "result", content: "中英文翻译 Agent已经创建并通过结构验证。", operation_id: "op-1", payload: { agent_id: "agent-1" }, created_at: "2026-09-18T00:00:03Z" },
      ],
      operations: [{
        ...durableSnapshot().operations[0],
        status: "succeeded",
        error_code: null,
        events: [
          { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.operation.started", label: "Started", summary: "", facts: {}, created_at: "2026-09-18T00:00:00Z" },
          { event_id: "e2", operation_id: "op-1", sequence: 1, kind: "builder.operation.completed", label: "Completed", summary: "", facts: {}, created_at: "2026-09-18T00:00:03Z" },
        ],
      }],
    });
    const tested = {
      ...completed,
      operations: [
        ...completed.operations,
        {
          operation_id: "op-test",
          conversation_id: "conv-1",
          kind: "test_agent",
          target_kind: "agent" as const,
          status: "succeeded" as const,
          retry_of: null,
          error_code: null,
          proposal_id: null,
          run_id: "run-1",
          factory_session_id: null,
          created_at: "2026-09-20T00:00:00Z",
          updated_at: "2026-09-20T00:00:01Z",
          diagnostic: {},
          has_request: false,
          events: [
            { event_id: "t1", operation_id: "op-test", sequence: 0, kind: "builder.test_run.started" as const, label: "Testing Agent", summary: "", facts: {}, created_at: "2026-09-20T00:00:00Z" },
            { event_id: "t2", operation_id: "op-test", sequence: 1, kind: "builder.test_run.completed" as const, label: "Test succeeded", summary: "", facts: { run_id: "run-1" }, created_at: "2026-09-20T00:00:01Z" },
            { event_id: "t3", operation_id: "op-test", sequence: 2, kind: "builder.operation.completed" as const, label: "Completed", summary: "", facts: {}, created_at: "2026-09-20T00:00:01Z" },
          ],
          receipts: [],
          run_observation: {
            run_id: "run-1",
            agent_id: "agent-1",
            version_id: "version-1",
            status: "unverified",
            runtime_model_id: "translator-model",
            runtime_model_source: "default",
            output_summary: "你好，世界",
            failure_code: null,
            failed_node: null,
            tool_failure: null,
            knowledge_failure: null,
            approval_required: false,
            duration_ms: 15,
            evidence_count: 0,
            classification: "none" as const,
            explanation: "测试成功。",
            repair_proposal_id: null,
            repair_code: null,
            next_action: null,
          },
        },
      ],
    };
    const { api, wrapper } = setup("agent", [], false);
    const startBuilderTestRun = vi.fn().mockResolvedValue(tested);
    Object.assign(api, {
      submitBuilderTurn: vi.fn(),
      getBuilderConversation: vi.fn().mockResolvedValue(completed),
      startBuilderTestRun,
      runtimeReadiness: vi.fn().mockResolvedValue({
        schema_version: "1.0",
        project_id: "project-1",
        agent_id: "agent-1",
        ready: true,
        profile_source: "default",
        model: { required: true, configured: true, model_id: "translator-model", model_base_url: "", model_api_key_env: "" },
        dependency_summary: { total: 0, ready: 0, attention: 0 },
        dependencies: [],
        tool_checks: [],
        checks: [],
      }),
      getDraft: vi.fn().mockResolvedValue(editDraft({ ...editAgent, inputs: { text: "string" } })),
    });
    cleanup();
    window.location.hash = "#/projects/project-1/chat?conversation=conv-1";
    render(wrapper(<ProjectChatPage projectId="project-1" conversationId="conv-1" />));
    expect(await screen.findByRole("button", { name: /Build Agent · completed/ })).toBeInTheDocument();
    expect(document.querySelector(".agent-convo-column .builder-workspace-dock")).toBeInTheDocument();
    expect(document.querySelector(".agent-convo-workspace")).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Workbench" })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("tab", { name: "Test" }));
    expect(screen.getByRole("tab", { name: "Test" })).toHaveAttribute("aria-selected", "true");
    fireEvent.change(await screen.findByLabelText("Test input"), { target: { value: "Hello world" } });
    fireEvent.click(screen.getByRole("button", { name: "Test Agent" }));
    await waitFor(() => expect(startBuilderTestRun).toHaveBeenCalledWith("project-1", "conv-1", {
      agent_id: "agent-1",
      inputs: { text: "Hello world" },
      locale: "en",
    }));
    expect(await screen.findByRole("button", { name: /Test Agent · completed/ })).toBeInTheDocument();
    expect(screen.getByText("你好，世界")).toBeInTheDocument();
    expect(screen.getByText(/translator-model/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View run detail" })).toHaveAttribute("href", "#/projects/project-1/agents/agent-1/run?run_id=run-1");
    expect(screen.queryByText("run.created")).not.toBeInTheDocument();
    expect(screen.queryByText("Kimi K3")).not.toBeInTheDocument();
  });

  it("does not show Test Agent while the build proposal is still in review", async () => {
    const reviewed = durableSnapshot({
      conversation: { ...durableSnapshot().conversation, last_operation_status: "waiting" },
      messages: [
        { message_id: "m-user", conversation_id: "conv-1", sequence: 0, role: "user", kind: "user", content: "创建一个翻译 Agent", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:00Z" },
        { message_id: "m-asst", conversation_id: "conv-1", sequence: 1, role: "assistant", kind: "assistant", content: "方案已准备好。", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:01Z" },
      ],
      operations: [{
        ...durableSnapshot().operations[0],
        status: "waiting",
        error_code: null,
        events: [
          { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.proposal.ready", label: "Preparing review", summary: "", facts: {}, created_at: "2026-09-18T00:00:01Z" },
        ],
      }],
      factory_session: factoryReviewSession(),
    });
    const { api, wrapper } = setup("agent", [], false);
    Object.assign(api, {
      submitBuilderTurn: vi.fn(),
      getBuilderConversation: vi.fn().mockResolvedValue(reviewed),
      startBuilderTestRun: vi.fn(),
    });
    cleanup();
    window.location.hash = "#/projects/project-1/chat?conversation=conv-1";
    render(wrapper(<ProjectChatPage projectId="project-1" conversationId="conv-1" />));
    expect(await screen.findByRole("button", { name: "Create Draft" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Workbench" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("button", { name: "Test Agent" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Test" }));
    expect(await screen.findByText(/After the Agent is created and validated/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Test Agent" })).not.toBeInTheDocument();
  });
});
