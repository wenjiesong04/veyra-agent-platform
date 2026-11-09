import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import type { AgentRunResponse } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { BudgetContinuation, budgetRequest } from "./BudgetContinuation";
import { RunApprovalBar } from "./RunApprovalBar";
import { approvalCard } from "../agents/app-activity";

afterEach(cleanup);

const run: AgentRunResponse = {
  schema_version: "1.0", run_id: "run-1", project_id: "project-1", agent_id: "agent-1", version_id: "version-1",
  status: "waiting", result: null, error: null, created_at: "2026-10-15T00:00:00Z", finished_at: null,
  events: [{ schema_version: "1.0", event_id: "event-1", run_id: "run-1", sequence: 1, kind: "approval.requested", node_id: "model",
    payload: { kind: "budget", request_id: "budget-1", context: { budget: { scope: "run_model_turns", used: 14, limit: 16, remaining: 2 }, required_remaining: 4, phase: "pre_render", max_additional_turns: 32, suggested_additional_turns: 8 } }, timestamp: "2026-10-15T00:00:00Z" }],
};

it("presents budget continuation, validates integer turns and never offers tool approval", async () => {
  const onContinue = vi.fn();
  const onCommand = vi.fn();
  render(<ThemeProvider><RunApprovalBar run={run} locale="en" onCommand={onCommand} onExtendBudget={onContinue} /></ThemeProvider>);
  const user = userEvent.setup();
  const input = screen.getByRole("spinbutton", { name: "Additional model turns" });
  expect(input).toHaveValue(8);
  expect(screen.getByText(/Used 14 \/ 16/)).toBeInTheDocument();
  expect(approvalCard(run)).toBeNull();
  expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  for (const invalid of ["0", "1", "33", "1.5"]) {
    await user.clear(input); await user.type(input, invalid);
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
  }
  await user.clear(input); await user.type(input, "4");
  await user.click(screen.getByRole("button", { name: "Continue" }));
  expect(onContinue).toHaveBeenCalledExactlyOnceWith(4);
  expect(onCommand).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Stop" }));
  expect(onCommand).toHaveBeenCalledExactlyOnceWith("stop");
});

it("resets the amount only for a different request and disables both controls while pending", () => {
  const props = { locale: "en" as const, onContinue: vi.fn(), onStop: vi.fn() };
  const view = render(<ThemeProvider><BudgetContinuation run={run} {...props} /></ThemeProvider>);
  const next = { ...run, events: [{ ...run.events![0], payload: { ...run.events![0].payload, request_id: "budget-2", context: { budget: { scope: "run_model_turns", used: 16, limit: 16, remaining: 0 }, required_remaining: 1, max_additional_turns: 10, suggested_additional_turns: 5 } } }] };
  view.rerender(<ThemeProvider><BudgetContinuation run={next} {...props} disabled /></ThemeProvider>);
  expect(screen.getByRole("spinbutton")).toHaveValue(5);
  expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Stop" })).toBeDisabled();
});

it("keeps Stop available at the host limit and refuses incomplete requests", () => {
  const hostLimit = { ...run, events: [{ ...run.events![0], payload: { ...run.events![0].payload, context: { budget: { scope: "run_model_turns", used: 256, limit: 256, remaining: 0 }, required_remaining: 4, max_additional_turns: 0, suggested_additional_turns: 0 } } }] };
  const view = render(<ThemeProvider><BudgetContinuation run={hostLimit} locale="en" onContinue={vi.fn()} onStop={vi.fn()} /></ThemeProvider>);
  expect(screen.getByText(/host's cumulative turn limit/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Stop" })).toBeEnabled();
  const malformed = { ...run, events: [{ ...run.events![0], payload: { ...run.events![0].payload, request_id: null } }] };
  expect(budgetRequest(malformed)).toBeNull();
  view.rerender(<ThemeProvider><BudgetContinuation run={malformed} locale="en" onContinue={vi.fn()} onStop={vi.fn()} /></ThemeProvider>);
  expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
  expect(screen.getByRole("alert")).toHaveTextContent("incomplete");
});
