import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import type { AgentRunResponse, WorkflowRunResponse } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { RunDetail, RunEvidence } from "./RunDetail";

afterEach(cleanup);

const agentRun: AgentRunResponse = {
  schema_version: "1.0", run_id: "run-1", project_id: "project-1", agent_id: "agent-1", version_id: "version-1",
  status: "waiting", result: null, error: null, created_at: "2026-10-12T00:00:00Z", finished_at: null,
  events: [{ schema_version: "1.0", event_id: "event-old", run_id: "run-1", sequence: 1, kind: "approval.requested", node_id: "model",
    payload: { prompt: "First approval", request_id: "request-old" }, timestamp: "2026-10-12T00:00:00Z" }],
};

it.each([true, false])("shows only recorded timeout phase and threshold (valid: %s)", (valid) => {
  const timedOut: AgentRunResponse = {
    ...agentRun, status: "failed", error: { code: "runtime_timeout", message: "Raw timeout" },
    events: [{ ...agentRun.events![0], kind: "node.failed", payload: { code: "runtime_timeout", provider_diagnostic: valid ? { timeout_phase: "read", timeout_seconds: 90 } : { timeout_phase: "untrusted-value", timeout_seconds: -1 } } }],
  };
  render(<ThemeProvider><RunEvidence run={timedOut} locale="zh" /></ThemeProvider>);
  expect(screen.getByText(/模型服务请求超时，未获得完整响应/)).toBeInTheDocument();
  const alert = screen.getByRole("alert");
  expect(alert).toHaveTextContent("runtime_timeout");
  if (valid) expect(alert).toHaveTextContent("读取响应阶段 · 超时阈值 90 秒");
  else expect(alert).not.toHaveTextContent(/读取响应阶段|超时阈值|untrusted-value/);
  expect(screen.queryByText("Raw timeout")).not.toBeInTheDocument();
});

it.each(["agent", "workflow"] as const)("extends %s budget on the same Run with a bound stable request, without automatic replay", async (kind) => {
  const context = { budget: { scope: "run_model_turns", used: 14, limit: 16, remaining: 2 }, required_remaining: 4, phase: "pre_render", max_additional_turns: 32, suggested_additional_turns: 8 };
  const { agent_id: _agentId, ...base } = agentRun;
  const budgetRun: AgentRunResponse | WorkflowRunResponse = kind === "agent"
    ? { ...agentRun, events: [{ ...agentRun.events![0], payload: { kind: "budget", prompt: "More turns needed", request_id: "budget-1", context } }] }
    : { ...base, workflow_id: "workflow-1", children: [], waiting: { kind: "budget", node_id: "call", prompt: "More turns needed", request_id: "budget-1", child_run_id: "child-1", context } };
  const send = vi.fn().mockRejectedValue(new Error("Response unknown"));
  const api = { commandAgentRun: send, commandWorkflowRun: send, getAgentRun: vi.fn().mockResolvedValue(budgetRun), getWorkflowRun: vi.fn().mockResolvedValue(budgetRun) } as unknown as LocalProjectApi;
  render(<ThemeProvider><RunDetail api={api} projectId="project-1" runId="run-1" locale="en" {...(kind === "agent" ? { agentId: "agent-1" } : { workflowId: "workflow-1" })} /></ThemeProvider>);
  const user = userEvent.setup();
  await screen.findByText("Waiting for additional turns");
  expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByText("Response unknown");
  expect(send).toHaveBeenCalledTimes(1);
  expect(send.mock.calls[0].slice(0, 4)).toEqual(["project-1", kind === "agent" ? "agent-1" : "workflow-1", "run-1", { command: "extend_budget", expected_request_id: "budget-1", additional_turns: 8 }]);
  const firstKey = send.mock.calls[0][4].idempotencyKey;
  await user.click(screen.getByRole("button", { name: "Continue" }));
  expect(send).toHaveBeenCalledTimes(2);
  expect(send.mock.calls[1][4].idempotencyKey).toBe(firstKey);
  await user.click(screen.getByRole("button", { name: "Stop" }));
  expect(send.mock.calls[2][3]).toEqual({ command: "stop", expected_request_id: "budget-1" });
});

it.each(["agent", "workflow"] as const)("binds %s Run Detail actions to the displayed request and refreshes errors without replay", async (kind) => {
  const { agent_id: _agentId, ...base } = agentRun;
  const workflowRun: WorkflowRunResponse = { ...base, workflow_id: "workflow-1", children: [], waiting: { kind: "approval", node_id: "call", prompt: "First approval", request_id: "request-old" } };
  const first = kind === "agent" ? agentRun : workflowRun;
  const second: AgentRunResponse | WorkflowRunResponse = kind === "agent"
    ? { ...agentRun, events: [{ ...agentRun.events![0], event_id: "event-new", sequence: 2, payload: { prompt: "Second approval", request_id: "request-new" } }] }
    : { ...workflowRun, waiting: { ...workflowRun.waiting!, prompt: "Second approval", request_id: "request-new" } };
  let current = first;
  const send = vi.fn().mockImplementation(async () => {
    if (current === first) { current = second; throw new Error("Request changed"); }
    return current;
  });
  const get = vi.fn().mockImplementation(async () => current);
  const api = { commandAgentRun: send, commandWorkflowRun: send, getAgentRun: get, getWorkflowRun: get } as unknown as LocalProjectApi;
  render(<ThemeProvider><RunDetail api={api} projectId="project-1" runId="run-1" locale="en" {...(kind === "agent" ? { agentId: "agent-1" } : { workflowId: "workflow-1" })} /></ThemeProvider>);
  const user = userEvent.setup();
  await screen.findByText("First approval");
  await user.click(screen.getByRole("button", { name: "Approve" }));
  expect(await screen.findByText("Second approval")).toBeInTheDocument();
  expect(send).toHaveBeenCalledTimes(1);
  expect(send).toHaveBeenLastCalledWith("project-1", kind === "agent" ? "agent-1" : "workflow-1", "run-1", { command: "approve", expected_request_id: "request-old" });
  await user.click(screen.getByRole("button", { name: "Reject" }));
  expect(send).toHaveBeenLastCalledWith("project-1", kind === "agent" ? "agent-1" : "workflow-1", "run-1", { command: "reject", expected_request_id: "request-new" });
});

it.each([
  ["agent", "zh", "等待输入"],
  ["agent", "en", "Waiting for input"],
  ["workflow", "zh", "等待输入"],
  ["workflow", "en", "Waiting for input"],
] as const)("labels %s input waiting in %s without offering approval commands", async (kind, locale, label) => {
  const { agent_id: _agentId, ...base } = agentRun;
  const inputEvent = { ...agentRun.events![0], event_id: "event-input", sequence: 2, payload: { kind: "input", prompt: "Choose a design", request_id: "input-1" } };
  const run: AgentRunResponse | WorkflowRunResponse = kind === "agent"
    ? { ...agentRun, events: [...agentRun.events!, inputEvent] }
    : { ...base, workflow_id: "workflow-1", children: [], waiting: { kind: "input", node_id: "input", prompt: "Choose a design", request_id: "input-1" } };
  const send = vi.fn();
  const api = { getAgentRun: vi.fn().mockResolvedValue(run), getWorkflowRun: vi.fn().mockResolvedValue(run), commandAgentRun: send, commandWorkflowRun: send } as unknown as LocalProjectApi;
  render(<ThemeProvider><RunDetail api={api} projectId="project-1" runId="run-1" locale={locale} {...(kind === "agent" ? { agentId: "agent-1" } : { workflowId: "workflow-1" })} /></ThemeProvider>);
  expect(await screen.findByText(label)).toBeInTheDocument();
  expect(screen.queryByText(locale === "zh" ? "等待审批" : "Waiting for approval")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: locale === "zh" ? "批准" : "Approve" })).not.toBeInTheDocument();
  expect(send).not.toHaveBeenCalled();
});

it.each([
  ["agent", "zh", "等待审批"],
  ["agent", "en", "Waiting for approval"],
  ["workflow", "zh", "等待审批"],
  ["workflow", "en", "Waiting for approval"],
] as const)("keeps %s tool approval distinct from an earlier input request in %s", async (kind, locale, label) => {
  const earlierInput = { ...agentRun.events![0], payload: { kind: "input", prompt: "Choose a design", request_id: "input-old" } };
  const approval = { ...agentRun.events![0], event_id: "event-approval", sequence: 2, payload: { kind: "tool", prompt: "Write notes.txt?", request_id: "approval-current" } };
  const { agent_id: _agentId, ...base } = agentRun;
  const run: AgentRunResponse | WorkflowRunResponse = kind === "agent"
    ? { ...agentRun, events: [earlierInput, approval] }
    : { ...base, workflow_id: "workflow-1", children: [], events: [earlierInput], waiting: { kind: "approval", node_id: "call", prompt: "Write notes.txt?", request_id: "approval-current" } };
  const api = { getAgentRun: vi.fn().mockResolvedValue(run), getWorkflowRun: vi.fn().mockResolvedValue(run), commandAgentRun: vi.fn(), commandWorkflowRun: vi.fn() } as unknown as LocalProjectApi;
  render(<ThemeProvider><RunDetail api={api} projectId="project-1" runId="run-1" locale={locale} {...(kind === "agent" ? { agentId: "agent-1" } : { workflowId: "workflow-1" })} /></ThemeProvider>);
  expect(await screen.findByText(label)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: locale === "zh" ? "批准" : "Approve" })).toBeInTheDocument();
  expect(screen.queryByText(locale === "zh" ? "等待输入" : "Waiting for input")).not.toBeInTheDocument();
});

it("does not replace a completed status because a historical input event remains", () => {
  const run: AgentRunResponse = { ...agentRun, status: "unverified", events: [{ ...agentRun.events![0], payload: { kind: "input", prompt: "Old question" } }] };
  render(<ThemeProvider><RunEvidence run={run} locale="zh" /></ThemeProvider>);
  expect(screen.getByText("未验证")).toBeInTheDocument();
  expect(screen.queryByText("等待输入")).not.toBeInTheDocument();
});

it("prioritizes the readable result and discloses full immutable identities and execution evidence", async () => {
  const completed: AgentRunResponse = { ...agentRun, status: "unverified", result: { report: "## Reconciliation\n\n| Order | Difference |\n| --- | ---: |\n| O002 | -0.10 |" }, finished_at: "2026-10-12T00:00:40Z", events: [{ ...agentRun.events![0], kind: "tool.completed", payload: { receipt: "original-receipt" } }] };
  render(<ThemeProvider><RunEvidence run={completed} locale="en" /></ThemeProvider>);
  const user = userEvent.setup();
  expect(screen.getByRole("heading", { level: 1, name: "Run detail" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: completed.run_id })).not.toBeInTheDocument();
  expect(screen.getByText("Unverified")).toBeVisible();
  expect(screen.getByRole("table")).toBeVisible();
  expect(screen.getByRole("cell", { name: "O002" })).toBeVisible();
  expect(screen.getByText(/Elapsed 40 s/)).toBeInTheDocument();
  const information = screen.getByText("Run information", { selector: "summary span" }).closest("details")!;
  const execution = screen.getByText("Execution record", { selector: "summary span" }).closest("details")!;
  expect(information).not.toHaveAttribute("open");
  expect(execution).not.toHaveAttribute("open");
  await user.click(screen.getByText("Run information", { selector: "summary span" }));
  expect(screen.getByText(completed.run_id)).toBeVisible();
  expect(screen.getByText(completed.version_id)).toBeVisible();
  expect(screen.getByText(completed.created_at)).toBeVisible();
  await user.click(screen.getByText("Execution record", { selector: "summary span" }));
  await user.click(screen.getByText("View evidence", { selector: "summary" }));
  expect(screen.getByText(/original-receipt/)).toBeVisible();
  expect(completed.status).toBe("unverified");
});

it("loads evaluation history only when expanded and keeps editing state when collapsed", async () => {
  const completed: AgentRunResponse = { ...agentRun, status: "unverified", result: { result: "done" }, events: [] };
  const history = vi.fn().mockResolvedValue({ schema_version: "1.0", reports: [] });
  const api = { getAgentRun: vi.fn().mockResolvedValue(completed), getAgentRunEvaluations: history, evaluateAgentRun: vi.fn() } as unknown as LocalProjectApi;
  render(<ThemeProvider><RunDetail api={api} projectId="project-1" agentId="agent-1" runId="run-1" locale="en" /></ThemeProvider>);
  const user = userEvent.setup();
  const disclosure = await screen.findByText("Result acceptance");
  expect(history).not.toHaveBeenCalled();
  await user.click(disclosure);
  await screen.findByText("No evaluation reports yet.");
  expect(history).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole("button", { name: "Add condition" }));
  await user.clear(screen.getByRole("textbox", { name: "Condition name 1" }));
  await user.type(screen.getByRole("textbox", { name: "Condition name 1" }), "Saved edit");
  await user.click(disclosure);
  await user.click(disclosure);
  expect(screen.getByRole("textbox", { name: "Condition name 1" })).toHaveValue("Saved edit");
  expect(history).toHaveBeenCalledTimes(1);
  expect(api.evaluateAgentRun).not.toHaveBeenCalled();
});
