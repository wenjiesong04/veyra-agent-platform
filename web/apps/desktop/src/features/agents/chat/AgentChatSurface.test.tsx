import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentRunResponse, AgentSource, DraftResponse } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import type { LocalProjectApi } from "../../../api/local-client";
import { AgentChatSurface } from "./AgentChatSurface";

const source: AgentSource = { schema_version: "1.0", agentspec_version: "26.1", component_type: "Flow", agent_id: "agent-1", slug: "reviewer", name: "Reviewer", description: "Reviews the supplied request.", inputs: { request: "string" }, outputs: { answer: "string" }, nodes: [], transitions: [], extensions: { veyra: { runtime_profile: "guarded-local", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: true, checks: [] } } }, ui: { positions: {} }, lock: {} };
const draft: DraftResponse = { schema_version: "1.0", draft_id: "draft-1", revision: 1, etag: "etag-1", source_file_hash: "source-hash", source };
const run: AgentRunResponse = { schema_version: "1.0", run_id: "run-1", project_id: "project-1", agent_id: "agent-1", version_id: "version-1", status: "verified", result: { answer: "Reviewed" }, error: null, created_at: "2026-08-28T00:00:00Z", finished_at: "2026-08-28T00:00:01Z" };

function renderSurface(api: LocalProjectApi) { return render(<ThemeProvider storageKey="agent-chat-test-theme"><AgentChatSurface api={api} projectId="project-1" agentId="agent-1" locale="en" /></ThemeProvider>); }
const resultCode = () => screen.getByText((content, element) => element?.tagName === "CODE" && content.includes("Reviewed"));

describe("AgentChatSurface", () => {
  afterEach(cleanup);
  it("loads the real draft, submits exact input, and renders the Runtime result", async () => {
    const runAgent = vi.fn().mockResolvedValue(run); const getAgentRun = vi.fn().mockResolvedValue(run);
    renderSurface({ getDraft: vi.fn().mockResolvedValue(draft), runAgent, getAgentRun } as unknown as LocalProjectApi);
    const user = userEvent.setup(); await user.type(await screen.findByRole("textbox", { name: "request" }), "Check this"); await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(runAgent).toHaveBeenCalledWith("project-1", "agent-1", { inputs: { request: "Check this" } }));
    await waitFor(() => expect(resultCode()).toBeInTheDocument()); expect(screen.getByText("Verified")).toBeInTheDocument(); expect(getAgentRun).toHaveBeenCalledWith("project-1", "agent-1", "run-1");
  });

  it("shows that Runtime support is unavailable without inventing an answer", async () => {
    renderSurface({ getDraft: vi.fn().mockResolvedValue(draft) } as unknown as LocalProjectApi);
    expect(await screen.findByText("The local Runtime does not support starting this Agent yet.")).toBeInTheDocument(); expect(screen.getByRole("button", { name: "Send" })).toBeDisabled(); expect(screen.queryByText("Runtime result")).not.toBeInTheDocument();
  });

  it("renders the Runtime's runtime_not_supported response as a governed error", async () => {
    const unsupported = { ...run, status: "failed" as const, result: null, error: { code: "runtime_not_supported", message: "This Agent cannot run in the local Runtime." } };
    renderSurface({ getDraft: vi.fn().mockResolvedValue(draft), runAgent: vi.fn().mockResolvedValue(unsupported) } as unknown as LocalProjectApi);
    const user = userEvent.setup(); await user.type(await screen.findByRole("textbox", { name: "request" }), "Try it"); await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("This Agent cannot run in the local Runtime.")).toBeInTheDocument(); expect(screen.getByText("runtime_not_supported")).toBeInTheDocument(); expect(screen.queryByText("Runtime result")).not.toBeInTheDocument();
  });

  it("clears submitted input and output instead of retaining a fake chat history", async () => {
    renderSurface({ getDraft: vi.fn().mockResolvedValue(draft), runAgent: vi.fn().mockResolvedValue(run) } as unknown as LocalProjectApi);
    const user = userEvent.setup(); await user.type(await screen.findByRole("textbox", { name: "request" }), "Reset me"); await user.click(screen.getByRole("button", { name: "Send" })); await waitFor(() => expect(resultCode()).toBeInTheDocument()); await user.click(screen.getByRole("button", { name: "Clear & reset" }));
    expect(screen.queryByText((content, element) => element?.tagName === "CODE" && content.includes("Reviewed"))).not.toBeInTheDocument(); expect(screen.queryByText((content, element) => element?.tagName === "CODE" && content.includes("Reset me"))).not.toBeInTheDocument(); expect(screen.getByRole("textbox", { name: "request" })).toHaveValue("");
  });

  it("keeps a loading state until the real draft arrives", () => {
    renderSurface({ getDraft: vi.fn(() => new Promise(() => undefined)) } as unknown as LocalProjectApi);
    expect(screen.getByRole("status")).toHaveTextContent("Loading Agent draft…");
  });
});
