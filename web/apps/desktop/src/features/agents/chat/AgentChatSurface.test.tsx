import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentRunResponse, AgentSource, AgentVersionSnapshot, RuntimeReadiness } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import type { LocalProjectApi } from "../../../api/local-client";
import "../../../app.css";
import { AgentChatSurface } from "./AgentChatSurface";

const source: AgentSource = { schema_version: "1.0", agentspec_version: "26.1", component_type: "Flow", agent_id: "agent-1", slug: "reviewer", name: "Reviewer", description: "Reviews the supplied request.", inputs: { request: "string" }, outputs: { answer: "string" }, nodes: [], transitions: [], extensions: { veyra: { runtime_profile: "guarded-local", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: true, checks: [] }, interaction_mode: "chat" } }, ui: { positions: {} }, lock: {} };
const version: AgentVersionSnapshot = { version_id: "version-1", agent_id: "agent-1", source_hash: "a".repeat(64), behavior_hash: "b".repeat(64), created_at: "2026-08-28T00:00:00Z", source, committed: true };
const run: AgentRunResponse = { schema_version: "1.0", run_id: "run-1", project_id: "project-1", agent_id: "agent-1", version_id: "version-1", status: "verified", result: { answer: "Reviewed" }, error: null, created_at: "2026-08-28T00:00:00Z", finished_at: "2026-08-28T00:00:01Z" };
const readyReadiness: RuntimeReadiness = { schema_version: "1.0", project_id: "project-1", agent_id: "agent-1", version_id: "version-1", ready: true, profile_source: "default", model: { required: true, configured: true, model_id: "test-model", model_base_url: "http://localhost", model_api_key_env: "" }, dependency_summary: { total: 0, ready: 0, attention: 0 }, dependencies: [], tool_checks: [], checks: [{ id: "model", ready: true, code: "ready", detail: "Ready" }] };

function versionsFor(next: AgentSource = source, committed = true): AgentVersionSnapshot {
  return { ...version, source: next, committed };
}

function renderSurface(api: LocalProjectApi) { return render(<ThemeProvider storageKey="agent-chat-test-theme"><AgentChatSurface api={api} projectId="project-1" agentId="agent-1" locale="en" /></ThemeProvider>); }
const resultText = () => screen.getByText("Reviewed");

function apiWith(overrides: Partial<LocalProjectApi> = {}, nextSource: AgentSource = source): LocalProjectApi {
  return {
    listAgentVersions: vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [versionsFor(nextSource)] }),
    runtimeReadiness: vi.fn().mockResolvedValue(readyReadiness),
    ...overrides,
  } as unknown as LocalProjectApi;
}

describe("AgentChatSurface", () => {
  afterEach(cleanup);
  it("sends only explicitly selected Project file paths through the declared chat input", async () => {
    const fileSource = { ...source, extensions: { veyra: { ...source.extensions.veyra, permissions: { network_hosts: [], tools: ["veyra.tool.filesystem.read"] } } } };
    const runAgent = vi.fn().mockResolvedValue(run);
    const api = apiWith({ runAgent, listProjectFiles: vi.fn().mockResolvedValue({ files: [{ path: "assets/orders.csv" }, { path: "assets/payments.csv" }, { path: "manifest.json" }] }) }, fileSource);
    const user = userEvent.setup();
    renderSurface(api);
    await user.type(await screen.findByRole("textbox", { name: "request" }), "Reconcile the selected materials");
    await user.click(screen.getByText("Choose Project files", { selector: "summary" }));
    await user.click(await screen.findByRole("checkbox", { name: "assets/orders.csv" }));
    expect(screen.queryByRole("checkbox", { name: "manifest.json" })).not.toBeInTheDocument();
    expect(runAgent).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(runAgent).toHaveBeenCalled());
    expect(runAgent.mock.calls[0][2]).toMatchObject({ inputs: { request: "Reconcile the selected materials\n\nSelected Project files (use the file-reading tool):\n- assets/orders.csv" }, source: "committed", version_id: "version-1" });
    expect(runAgent.mock.calls[0][2].inputs.request).not.toContain("payments.csv");
    await user.click(screen.getByRole("button", { name: "New conversation" }));
    expect(screen.getByRole("checkbox", { name: "assets/orders.csv" })).not.toBeChecked();
  });

  it("does not offer Project filesystem inputs to an Agent without the read permission", async () => {
    renderSurface(apiWith({ runAgent: vi.fn(), listProjectFiles: vi.fn().mockResolvedValue({ files: [{ path: "assets/orders.csv" }] }) }));
    await screen.findByRole("textbox", { name: "request" });
    expect(screen.queryByText("Choose Project files", { selector: "summary" })).not.toBeInTheDocument();
  });

  it("reads persisted structured assistant output only when all top-level keys are declared outputs", async () => {
    const nextSource: AgentSource = { ...source, outputs: { result: "object" } };
    const content = JSON.stringify({ result: { title: "Saved weekly plan", tasks: [{ name: "Review", completed: false }, { name: "Write", completed: true }] } });
    const conversation = {
      schema_version: "1.0" as const, conversation_id: "conversation-structured", project_id: "project-1", agent_id: "agent-1", agent_version_id: "version-1",
      title: "Plan", created_at: run.created_at, updated_at: run.created_at, initial_inputs: {},
      messages: [{ schema_version: "1.0" as const, message_id: "message-structured", conversation_id: "conversation-structured", sequence: 0, role: "assistant" as const, content, run_id: "old-run", created_at: run.created_at }],
    };
    const api = apiWith({
      runAgent: vi.fn(),
      listAgentConversations: vi.fn().mockResolvedValue({ schema_version: "1.0", conversations: [{ ...conversation, message_count: 1 }] }),
      getAgentConversation: vi.fn().mockResolvedValue(conversation),
    }, nextSource);
    const { container } = renderSurface(api);
    expect(await screen.findByText("Saved weekly plan")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Output items" })).toBeInTheDocument();
    expect(screen.queryByText(content)).not.toBeInTheDocument();
    expect(container.querySelector(".agent-chat-bubble.assistant pre")).toBeNull();
    expect(conversation.messages[0].content).toBe(content);
    expect(api.runAgent).not.toHaveBeenCalled();
  });

  it.each(["Ordinary assistant text", '{"title":"ordinary JSON answer"}', '{"answer":"Known","extra":"not declared"}', "{malformed}", "[]", "{}"]) (
    "retains a plain or non-contract JSON assistant answer as its original text: %s", async (content) => {
      const conversation = {
        schema_version: "1.0" as const, conversation_id: "conversation-text", project_id: "project-1", agent_id: "agent-1", agent_version_id: "version-1",
        title: "Text", created_at: run.created_at, updated_at: run.created_at, initial_inputs: {},
        messages: [{ schema_version: "1.0" as const, message_id: "message-text", conversation_id: "conversation-text", sequence: 0, role: "assistant" as const, content, run_id: "old-run", created_at: run.created_at }],
      };
      const { container } = renderSurface(apiWith({
        runAgent: vi.fn(),
        listAgentConversations: vi.fn().mockResolvedValue({ schema_version: "1.0", conversations: [{ ...conversation, message_count: 1 }] }),
        getAgentConversation: vi.fn().mockResolvedValue(conversation),
      }));
      expect(await screen.findByText(content)).toBeInTheDocument();
      expect(container.querySelector(".runtime-output-reading")).toBeNull();
    },
  );

  it("loads the committed version, submits exact input, and renders the Runtime result", async () => {
    const runAgent = vi.fn().mockResolvedValue(run); const getAgentRun = vi.fn().mockResolvedValue(run);
    renderSurface(apiWith({ runAgent, getAgentRun }));
    const user = userEvent.setup(); await user.type(await screen.findByRole("textbox", { name: "request" }), "Check this"); await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(runAgent).toHaveBeenCalledWith("project-1", "agent-1", { inputs: { request: "Check this" }, source: "committed", version_id: "version-1" }));
    await waitFor(() => expect(resultText()).toBeInTheDocument()); expect(screen.getByText("Completed")).toBeInTheDocument(); expect(getAgentRun).toHaveBeenCalledWith("project-1", "agent-1", "run-1");
    expect(screen.getByText("v1")).toBeInTheDocument();
    expect(screen.queryByLabelText("Result canvas")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Run canvas")).not.toBeInTheDocument();
  });

  it("shows that Runtime support is unavailable without inventing an answer", async () => {
    renderSurface(apiWith());
    expect(await screen.findByText("The local Runtime does not support starting this Agent yet.")).toBeInTheDocument(); expect(screen.getByRole("button", { name: "Send" })).toBeDisabled(); expect(screen.queryByText("Result")).not.toBeInTheDocument();
  });

  it("renders the Runtime's runtime_not_supported response as a governed error", async () => {
    const unsupported = { ...run, status: "failed" as const, result: null, error: { code: "runtime_not_supported", message: "This Agent cannot run in the local Runtime." } };
    renderSurface(apiWith({ runAgent: vi.fn().mockResolvedValue(unsupported) }));
    const user = userEvent.setup(); await user.type(await screen.findByRole("textbox", { name: "request" }), "Try it"); await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("This Agent cannot run in the local Runtime.")).toBeInTheDocument(); expect(screen.getByText("runtime_not_supported")).toBeInTheDocument(); expect(screen.queryByText("Reviewed")).not.toBeInTheDocument();
  });

  it("clears submitted input and output instead of retaining a fake chat history", async () => {
    renderSurface(apiWith({ runAgent: vi.fn().mockResolvedValue(run) }));
    const user = userEvent.setup(); await user.type(await screen.findByRole("textbox", { name: "request" }), "Reset me"); await user.click(screen.getByRole("button", { name: "Send" })); await waitFor(() => expect(resultText()).toBeInTheDocument()); await user.click(screen.getByRole("button", { name: "New conversation" }));
    expect(screen.queryByText("Reviewed")).not.toBeInTheDocument(); expect(screen.queryByText("Reset me", { selector: ".agent-chat-bubble.user p" })).not.toBeInTheDocument(); expect(screen.getByRole("textbox", { name: "request" })).toHaveValue("");
  });

  it("keeps a loading state until committed versions arrive", () => {
    renderSurface({ listAgentVersions: vi.fn(() => new Promise(() => undefined)) } as unknown as LocalProjectApi);
    expect(screen.getByRole("status")).toHaveTextContent("Loading Agent App…");
  });

  it("shows an empty state when the Agent has no committed version", async () => {
    renderSurface({
      getDraft: vi.fn(),
      listAgentVersions: vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [versionsFor(source, false)] }),
    } as unknown as LocalProjectApi);
    expect(await screen.findByText(/Complete the checks and commit a version to use this Agent/)).toBeInTheDocument();
    expect(screen.getByText("Validate the Draft and commit a usable version")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Studio" })).toBeInTheDocument();
  });

  it("does not read the draft for App runs", async () => {
    const getDraft = vi.fn();
    renderSurface(apiWith({ getDraft, runAgent: vi.fn().mockResolvedValue(run), getAgentRun: vi.fn().mockResolvedValue(run) }));
    await screen.findByRole("textbox", { name: "request" });
    expect(getDraft).not.toHaveBeenCalled();
  });

  it("blocks send when the runtime model is not configured", async () => {
    const readiness: RuntimeReadiness = {
      schema_version: "1.0",
      project_id: "project-1",
      agent_id: "agent-1",
      version_id: "version-1",
      ready: false,
      profile_source: "default",
      model: { required: true, configured: false, model_id: "kimi-k3", model_base_url: "", model_api_key_env: "" },
      dependency_summary: { total: 0, ready: 0, attention: 0 },
      dependencies: [],
      tool_checks: [],
      checks: [{ id: "model", ready: false, code: "runtime_not_configured", detail: "missing" }],
    };
    const runAgent = vi.fn();
    renderSurface(apiWith({ runAgent, runtimeReadiness: vi.fn().mockResolvedValue(readiness) }));
    expect(await screen.findByText("Runtime model is not configured.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(runAgent).not.toHaveBeenCalled();
  });

  it("explains missing image generation setup before an App run", async () => {
    const readiness: RuntimeReadiness = { ...readyReadiness, ready: false, checks: [{ id: "image_model", ready: false, code: "image_model_not_configured", detail: "Bind image_model" }] };
    const runAgent = vi.fn();
    renderSurface(apiWith({ runAgent, runtimeReadiness: vi.fn().mockResolvedValue(readiness) }));
    expect(await screen.findByText("An image generation model is needed.", { exact: false })).toBeInTheDocument();
    expect(screen.queryByText("image_model_not_configured")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(runAgent).not.toHaveBeenCalled();
  });

  it("blocks send when a resource still needs configuration", async () => {
    const readiness: RuntimeReadiness = {
      schema_version: "1.0",
      project_id: "project-1",
      agent_id: "agent-1",
      version_id: "version-1",
      ready: false,
      profile_source: "default",
      model: { required: true, configured: true, model_id: "kimi-k3", model_base_url: "http://127.0.0.1", model_api_key_env: "KEY" },
      dependency_summary: { total: 1, ready: 0, attention: 1 },
      dependencies: [],
      tool_checks: [{ node_id: "capability", reference: "veyra.tool.github.read@1.0.0", ready: false, code: "needs_configuration", detail: "GitHub connection required." }],
      checks: [{ id: "tools", ready: false, code: "needs_configuration", detail: "needs config" }],
    };
    const runAgent = vi.fn();
    renderSurface(apiWith({ runAgent, runtimeReadiness: vi.fn().mockResolvedValue(readiness) }));
    expect(await screen.findByText(/This Agent needs configuration before it can run/)).toBeInTheDocument();
    expect(runAgent).not.toHaveBeenCalled();
  });

  it("renders a form Agent without a chat composer", async () => {
    const formSource: AgentSource = {
      ...source,
      inputs: { topic: "string", audience: "string", length: "number" },
      extensions: { veyra: { ...source.extensions.veyra, interaction_mode: "form" } },
    };
    const runAgent = vi.fn().mockResolvedValue({ ...run, result: { answer: "Brief" } });
    renderSurface(apiWith({ runAgent, getAgentRun: vi.fn().mockResolvedValue({ ...run, result: { answer: "Brief" } }) }, formSource));
    expect(await screen.findByLabelText("topic")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "request" })).not.toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("topic"), "Packaging");
    await user.type(screen.getByLabelText("audience"), "Retail");
    await user.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => expect(runAgent).toHaveBeenCalledWith("project-1", "agent-1", expect.objectContaining({ source: "committed", version_id: "version-1" })));
  });

  it("renders hybrid fields plus a message composer", async () => {
    const hybridSource: AgentSource = {
      ...source,
      inputs: { item_image: "image", brand: "string", message: "string" },
      extensions: { veyra: { ...source.extensions.veyra, interaction_mode: "hybrid" } },
    };
    renderSurface(apiWith({}, hybridSource));
    expect(await screen.findByLabelText("item_image")).toBeInTheDocument();
    expect(screen.getByLabelText("brand")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "message" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Add task details and a message" })).toBeInTheDocument();
    expect(screen.getByText(/After the first run, you can keep adding messages/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/continue the conversation after a run/)).toBeInTheDocument();
  });

  it("uploads a pasted image into the one declared typed field and sends only its ArtifactRef on the committed run", async () => {
    const imageSource: AgentSource = {
      ...source,
      inputs: { message: "string", productimage: { type: "image", description: "Product photo", required: true } },
      extensions: { veyra: { ...source.extensions.veyra, interaction_mode: "hybrid" } },
    };
    const artifactId = "artifact-private-01";
    const artifact = {
      kind: "artifact" as const,
      artifact_id: artifactId,
      project_id: "project-1",
      sha256: "c".repeat(64),
      filename: "front.png",
      media_type: "image/png",
      size_bytes: 11,
      storage_ref: "objects/sha256/cc",
      source_kind: "upload" as const,
      created_at: "2026-09-29T00:00:00Z",
    };
    const runAgent = vi.fn().mockResolvedValue(run);
    const uploadArtifact = vi.fn().mockResolvedValue(artifact);
    renderSurface(apiWith({ runAgent, getAgentRun: vi.fn().mockResolvedValue(run), uploadArtifact, artifactContent: vi.fn().mockResolvedValue(new Blob(["png"], { type: "image/png" })) }, imageSource));
    const message = await screen.findByRole("textbox", { name: "message" });
    const file = new File(["pixel-bytes"], "front.png", { type: "image/png" });
    fireEvent.paste(message, {
      clipboardData: {
        items: [{ kind: "file", getAsFile: () => file }],
        files: [file],
        getData: (type: string) => type === "text/plain" ? "Review the attached product" : "",
      },
    });
    expect(message).toHaveValue("Review the attached product");
    await waitFor(() => expect(uploadArtifact).toHaveBeenCalledWith("project-1", file));
    expect(await screen.findByAltText("front.png")).toBeInTheDocument();
    expect(screen.getByText(/Uploaded; included when you send/)).toBeInTheDocument();
    expect(runAgent).not.toHaveBeenCalled();

    await userEvent.setup().click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(runAgent).toHaveBeenCalledWith("project-1", "agent-1", {
      inputs: {
        message: "Review the attached product",
        productimage: { kind: "artifact", artifact_id: artifactId, media_type: "image/png", filename: "front.png" },
      },
      source: "committed",
      version_id: "version-1",
    }));
    expect(screen.queryByText(artifactId)).not.toBeInTheDocument();
    expect(screen.getAllByAltText("front.png").length).toBeGreaterThan(0);
  });

  it("includes only a newly pasted artifact field on a hybrid follow-up and keeps prior artifacts out of raw message text", async () => {
    const multiSource: AgentSource = {
      ...source,
      inputs: { message: "string", photos: { type: "image", multiple: true, required: true } },
      extensions: { veyra: { ...source.extensions.veyra, interaction_mode: "hybrid" } },
    };
    const previousRef = { kind: "artifact" as const, artifact_id: "old-private-ref", media_type: "image/png", filename: "old.png" };
    const nextRef = { kind: "artifact" as const, artifact_id: "new-private-ref", media_type: "image/png", filename: "side.png" };
    const runAgent = vi.fn().mockResolvedValue({ ...run, conversation_id: "conversation-1" });
    const conversation = {
      schema_version: "1.0" as const,
      conversation_id: "conversation-1",
      project_id: "project-1",
      agent_id: "agent-1",
      agent_version_id: "version-1",
      title: JSON.stringify({ product: "Demo", photos: [previousRef] }),
      created_at: "2026-09-29T00:00:00Z",
      updated_at: "2026-09-29T00:00:00Z",
      initial_inputs: { message: "First view", photos: [previousRef] },
      messages: [{ schema_version: "1.0" as const, message_id: "message-old", conversation_id: "conversation-1", sequence: 0, role: "user" as const, content: JSON.stringify({ message: "First view", photos: [previousRef] }), run_id: "run-old", created_at: "2026-09-29T00:00:00Z" }],
    };
    const uploadArtifact = vi.fn().mockResolvedValue({
      kind: "artifact", artifact_id: nextRef.artifact_id, project_id: "project-1", sha256: "d".repeat(64), filename: nextRef.filename,
      media_type: nextRef.media_type, size_bytes: 12, storage_ref: "objects/sha256/dd", source_kind: "upload", created_at: "2026-09-29T00:00:00Z",
    });
    renderSurface(apiWith({
      runAgent,
      getAgentRun: vi.fn().mockResolvedValue({ ...run, conversation_id: "conversation-1" }),
      uploadArtifact,
      artifactContent: vi.fn().mockResolvedValue(new Blob(["png"], { type: "image/png" })),
      listAgentConversations: vi.fn().mockResolvedValue({ schema_version: "1.0", conversations: [{ ...conversation, message_count: 1 }] }),
      getAgentConversation: vi.fn().mockResolvedValue(conversation),
    }, multiSource));
    expect(await screen.findByRole("button", { name: "Multi-field run · image attachment" })).toBeInTheDocument();
    expect(await screen.findByText("First view")).toBeInTheDocument();
    const message = screen.getByRole("textbox", { name: "message" });
    const file = new File(["pixels"], "side.png", { type: "image/png" });
    fireEvent.paste(message, {
      clipboardData: {
        items: [{ kind: "file", getAsFile: () => file }], files: [file],
        getData: (type: string) => type === "text/plain" ? "Add this view" : "",
      },
    });
    expect(message).toHaveValue("Add this view");
    await waitFor(() => expect(uploadArtifact).toHaveBeenCalled());
    await userEvent.setup().click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(runAgent).toHaveBeenCalledWith("project-1", "agent-1", expect.objectContaining({
      conversation_id: "conversation-1",
      inputs: { message: "Add this view", photos: [previousRef, nextRef] },
      source: "committed",
      version_id: "version-1",
    })));
    expect(screen.queryByText("old-private-ref")).not.toBeInTheDocument();
    expect(screen.queryByText("new-private-ref")).not.toBeInTheDocument();
    expect(screen.getAllByAltText("old.png").length).toBeGreaterThan(0);
  });

  it("does not overwrite an existing single-image input when another image is pasted", async () => {
    const singleSource: AgentSource = {
      ...source,
      inputs: { message: "string", photo: { type: "image", required: true } },
      extensions: { veyra: { ...source.extensions.veyra, interaction_mode: "hybrid" } },
    };
    const existing = { kind: "artifact" as const, artifact_id: "keep-this-ref", media_type: "image/png", filename: "first.png" };
    const conversation = {
      schema_version: "1.0" as const, conversation_id: "conversation-1", project_id: "project-1", agent_id: "agent-1", agent_version_id: "version-1",
      title: "Existing photo", created_at: "2026-09-29T00:00:00Z", updated_at: "2026-09-29T00:00:00Z", initial_inputs: { message: "First", photo: existing },
      messages: [{ schema_version: "1.0" as const, message_id: "message-old", conversation_id: "conversation-1", sequence: 0, role: "user" as const, content: JSON.stringify({ message: "First", photo: existing }), run_id: "run-old", created_at: "2026-09-29T00:00:00Z" }],
    };
    const uploadArtifact = vi.fn();
    renderSurface(apiWith({
      uploadArtifact,
      listAgentConversations: vi.fn().mockResolvedValue({ schema_version: "1.0", conversations: [{ ...conversation, message_count: 1 }] }),
      getAgentConversation: vi.fn().mockResolvedValue(conversation),
    }, singleSource));
    const message = await screen.findByRole("textbox", { name: "message" });
    expect(await screen.findByText("first.png")).toBeInTheDocument();
    const file = new File(["pixels"], "second.png", { type: "image/png" });
    fireEvent.paste(message, { clipboardData: { items: [{ kind: "file", getAsFile: () => file }], files: [file], getData: () => "" } });
    expect(await screen.findByRole("alert")).toHaveTextContent(/accepts one file/);
    expect(uploadArtifact).not.toHaveBeenCalled();
    expect(screen.getByText("first.png")).toBeInTheDocument();
    expect(screen.queryByAltText("second.png")).not.toBeInTheDocument();
  });

  it("keeps long Agent descriptions out of the empty-state hero while retaining them in the header disclosure", async () => {
    const description = "A detailed description of this Agent. ".repeat(12);
    const longSource = { ...source, description };
    renderSurface(apiWith({}, longSource));
    await screen.findByRole("textbox", { name: "request" });
    const hero = document.querySelector(".agent-convo-hero");
    expect(hero?.textContent).toContain("Send real inputs to start a local run.");
    expect(hero?.textContent).not.toContain(description);
    expect(screen.getByText("Read full description")).toBeInTheDocument();
  });

  it("shows a product approval card on the same run", async () => {
    const waiting: AgentRunResponse = {
      ...run,
      status: "waiting",
      result: null,
      finished_at: null,
      events: [{
        schema_version: "1.0",
        event_id: "event-2",
        run_id: "run-1",
        sequence: 2,
        kind: "approval.requested",
        node_id: "loop",
        payload: { prompt: "Write notes.txt?", approval_summary: { action: "Write file", target: "notes.txt", tool: "veyra.tool.filesystem.write@1.0.0", reason: "This tool requires explicit approval before it can run." } },
        timestamp: "2026-08-28T00:00:02Z",
      }],
    };
    const commandAgentRun = vi.fn().mockResolvedValue({ ...run, status: "unverified", result: { answer: "Written" } });
    renderSurface(apiWith({
      runAgent: vi.fn().mockResolvedValue(waiting),
      getAgentRun: vi.fn().mockResolvedValue(waiting),
      commandAgentRun,
    }));
    const user = userEvent.setup();
    await user.type(await screen.findByRole("textbox", { name: "request" }), "Save it");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Write file")).toBeInTheDocument();
    expect(screen.getByText("notes.txt")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(commandAgentRun).toHaveBeenCalledWith("project-1", "agent-1", "run-1", { command: "approve" }));
  });

  it("cancels a running App run through the Runtime command", async () => {
    const running: AgentRunResponse = { ...run, status: "running", result: null, finished_at: null };
    const commandAgentRun = vi.fn().mockResolvedValue({ ...run, status: "cancelled", result: null });
    renderSurface(apiWith({
      runAgent: vi.fn().mockResolvedValue(running),
      getAgentRun: vi.fn().mockResolvedValue(running),
      commandAgentRun,
    }));
    const user = userEvent.setup();
    await user.type(await screen.findByRole("textbox", { name: "request" }), "Slow");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await user.click(await screen.findByRole("button", { name: "Stop" }));
    await waitFor(() => expect(commandAgentRun).toHaveBeenCalledWith("project-1", "agent-1", "run-1", { command: "stop" }));
  });

  it("retries a failed run as a new committed run", async () => {
    const failed: AgentRunResponse = { ...run, status: "failed", result: null, error: { code: "runtime_provider_error", message: "scripted failure" } };
    const runAgent = vi.fn().mockResolvedValue(failed);
    renderSurface(apiWith({ runAgent, getAgentRun: vi.fn().mockResolvedValue(failed) }));
    const user = userEvent.setup();
    await user.type(await screen.findByRole("textbox", { name: "request" }), "Fail please");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await user.click(await screen.findByRole("button", { name: "Retry" }));
    await waitFor(() => expect(runAgent).toHaveBeenCalledTimes(2));
    expect(runAgent.mock.calls[1][2]).toEqual({ inputs: { request: "Fail please" }, source: "committed", version_id: "version-1" });
  });

  it("opens a result canvas for structured Runtime output", async () => {
    const structured = { ...run, result: { title: "Brief", score: 4, notes: ["keep"] } };
    renderSurface(apiWith({ runAgent: vi.fn().mockResolvedValue(structured), getAgentRun: vi.fn().mockResolvedValue(structured) }));
    const user = userEvent.setup();
    await user.type(await screen.findByRole("textbox", { name: "request" }), "Summarize");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("complementary", { name: "Result canvas" })).toBeInTheDocument();
    expect(screen.getByText("Opened in canvas.")).toBeInTheDocument();
    expect(screen.getByText("Brief")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close canvas" }));
    expect(screen.queryByRole("complementary", { name: "Result canvas" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open in canvas" }));
    expect(screen.getByRole("complementary", { name: "Result canvas" })).toBeInTheDocument();
  });

  it("uploads an image input and renders an image result", async () => {
    const photoSource: AgentSource = {
      ...source,
      inputs: { photo: "image" },
      outputs: { picture: "image" },
      extensions: { veyra: { ...source.extensions.veyra, interaction_mode: "form" } },
    };
    const pictured = {
      ...run,
      result: { picture: { kind: "artifact", artifact_id: "art_out", media_type: "image/png", filename: "pack.png" } },
    };
    const uploadArtifact = vi.fn().mockResolvedValue({
      kind: "artifact",
      artifact_id: "art_in",
      project_id: "project-1",
      sha256: "a".repeat(64),
      filename: "item.png",
      media_type: "image/png",
      size_bytes: 12,
      storage_ref: "objects/sha256/aa",
      source_kind: "upload",
      created_at: "2026-08-28T00:00:00Z",
    });
    const artifactContent = vi.fn().mockResolvedValue(new Blob(["png"], { type: "image/png" }));
    const runAgent = vi.fn().mockResolvedValue(pictured);
    renderSurface(apiWith({
      runAgent,
      getAgentRun: vi.fn().mockResolvedValue(pictured),
      uploadArtifact,
      artifactContent,
    }, photoSource));
    const user = userEvent.setup();
    const file = new File(["png"], "item.png", { type: "image/png" });
    await user.upload(await screen.findByLabelText("photo"), file);
    await waitFor(() => expect(uploadArtifact).toHaveBeenCalled());
    await user.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => expect(runAgent).toHaveBeenCalledWith("project-1", "agent-1", {
      inputs: { photo: { kind: "artifact", artifact_id: "art_in", media_type: "image/png", filename: "item.png" } },
      source: "committed",
      version_id: "version-1",
    }));
    expect(await screen.findByAltText("pack.png")).toBeInTheDocument();
    expect(screen.getAllByAltText("item.png").length).toBeGreaterThan(0);
  });

  it("switches conversations without mixing their titles", async () => {
    const listAgentConversations = vi.fn().mockResolvedValue({
      schema_version: "1.0",
      conversations: [
        { schema_version: "1.0", conversation_id: "c-1", project_id: "project-1", agent_id: "agent-1", agent_version_id: "version-1", title: "First chat", message_count: 1, created_at: "2026-08-28T00:00:00Z", updated_at: "2026-08-28T00:00:01Z" },
        { schema_version: "1.0", conversation_id: "c-2", project_id: "project-1", agent_id: "agent-1", agent_version_id: "version-1", title: "Second chat", message_count: 1, created_at: "2026-08-28T00:00:02Z", updated_at: "2026-08-28T00:00:03Z" },
      ],
    });
    const getAgentConversation = vi.fn().mockImplementation(async (_project: string, _agent: string, conversationId: string) => ({
      schema_version: "1.0",
      conversation_id: conversationId,
      project_id: "project-1",
      agent_id: "agent-1",
      agent_version_id: "version-1",
      title: conversationId === "c-1" ? "First chat" : "Second chat",
      created_at: "2026-08-28T00:00:00Z",
      updated_at: "2026-08-28T00:00:01Z",
      messages: [{ schema_version: "1.0", message_id: `m-${conversationId}`, conversation_id: conversationId, sequence: 0, role: "user", content: conversationId === "c-1" ? "Hello one" : "Hello two", run_id: "run-1", created_at: "2026-08-28T00:00:00Z" }],
    }));
    renderSurface(apiWith({ listAgentConversations, getAgentConversation }));
    expect(await screen.findByText("Hello one")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Second chat" }));
    expect(await screen.findByText("Hello two")).toBeInTheDocument();
    expect(screen.queryByText("Hello one")).not.toBeInTheDocument();
  });

  it("never shows a raw UUID as the conversation title", async () => {
    const leaked = "01a0ca54-c517-787b-bd8d-d4034403f38c";
    renderSurface(apiWith({
      listAgentConversations: vi.fn().mockResolvedValue({
        schema_version: "1.0",
        conversations: [{
          schema_version: "1.0",
          conversation_id: leaked,
          project_id: "project-1",
          agent_id: "agent-1",
          agent_version_id: "version-1",
          title: leaked,
          message_count: 0,
          created_at: "2026-08-28T00:00:00Z",
          updated_at: "2026-08-28T00:00:01Z",
        }],
      }),
      getAgentConversation: vi.fn().mockResolvedValue({
        schema_version: "1.0",
        conversation_id: leaked,
        project_id: "project-1",
        agent_id: "agent-1",
        agent_version_id: "version-1",
        title: leaked,
        created_at: "2026-08-28T00:00:00Z",
        updated_at: "2026-08-28T00:00:01Z",
        messages: [],
      }),
      listAgentRuns: vi.fn().mockResolvedValue({
        schema_version: "1.0",
        runs: [{ ...run, run_id: "01a0ca53-a2bf-7b24-957a-86dcd8c8a0f8" }],
      }),
    }));
    expect(await screen.findByRole("link", { name: "Edit in Studio" })).toHaveAttribute("href", "#/projects/project-1/agents/agent-1/design");
    expect(screen.queryByText(leaked)).not.toBeInTheDocument();
    expect(screen.queryByText("01a0ca53-a2bf-7b24-957a-86dcd8c8a0f8")).not.toBeInTheDocument();
    expect(screen.getAllByText("New conversation").length).toBeGreaterThan(0);
  });

  it("keeps the composer inside the primary interaction column", async () => {
    render(
      <ThemeProvider storageKey="agent-chat-layout-theme">
        <div className="page-content agent-conversation-content">
          <AgentChatSurface api={apiWith()} projectId="project-1" agentId="agent-1" locale="en" />
        </div>
      </ThemeProvider>,
    );
    const composer = await screen.findByRole("textbox", { name: "request" });
    expect(composer.closest(".agent-conversation-main")).not.toBeNull();
    const appShell = document.querySelector(".agent-app-shell");
    expect(appShell).toHaveAttribute("data-primary-surface", "app");
    expect(window.getComputedStyle(appShell!).display).toBe("grid");
    expect(document.querySelector(".agent-app-body")?.className).toContain("has-sidebar");
    expect(document.querySelector(".agent-conversation")?.classList.contains("is-empty")).toBe(true);
  });
});

it("restores a waiting question from the selected committed conversation", async () => {
  const waiting = { ...run, status: "waiting" as const, result: null, finished_at: null, conversation_id: "conversation-waiting", events: [{ schema_version: "1.0" as const, event_id: "input-event", run_id: "run-1", sequence: 1, node_id: "model", kind: "approval.requested" as const, payload: { kind: "input", prompt: "Choose A, B or C", context: { choices: ["A", "B", "C"] } }, timestamp: "2026-08-28T00:00:00Z" }] };
  const conversation = { schema_version: "1.0" as const, conversation_id: "conversation-waiting", project_id: "project-1", agent_id: "agent-1", agent_version_id: "version-1", title: "Design choices", created_at: run.created_at, updated_at: run.created_at, initial_inputs: { request: "Create options" }, messages: [] };
  const getAgentRun = vi.fn().mockResolvedValue(waiting);
  renderSurface(apiWith({ listAgentRuns: vi.fn().mockResolvedValue({ schema_version: "1.0", runs: [waiting] }), getAgentRun,
    listAgentConversations: vi.fn().mockResolvedValue({ schema_version: "1.0", conversations: [{ ...conversation, message_count: 1 }] }),
    getAgentConversation: vi.fn().mockResolvedValue(conversation), commandAgentRun: vi.fn().mockResolvedValue(run) }));
  expect(await screen.findByRole("form", { name: "Provide task information" })).toBeInTheDocument();
  expect(getAgentRun).toHaveBeenCalledWith("project-1", "agent-1", "run-1");
  expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Your reply" })).toBeEnabled();
});
