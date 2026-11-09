import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import type { JsonValue, RuntimeEvent } from "@veyra/api-contracts";
import { ExecutionBudget } from "./ExecutionBudget";

afterEach(cleanup);

function event(payload: Record<string, JsonValue>, kind: RuntimeEvent["kind"] = "node.started"): RuntimeEvent {
  return { schema_version: "1.0", event_id: "fixture", run_id: "run", sequence: 1, node_id: "model", kind, payload, timestamp: "2026-10-14T10:00:00Z" };
}

it("shows the latest cumulative budget including review requests", () => {
  render(<ExecutionBudget events={[
    event({ budget: { scope: "run_model_turns", limit: 16, used: 10, remaining: 6 } }),
    event({ budget: { scope: "run_model_turns", limit: 16, used: 11, remaining: 5 } }, "finalization.started"),
  ]} locale="zh" />);
  expect(screen.getByText("模型轮次: 11 / 16")).toBeInTheDocument();
  expect(screen.getByText("剩余 5")).toBeInTheDocument();
  expect(screen.getByText(/不是金额或图片请求上限/)).toBeInTheDocument();
});

it("shows required delivery reserve without inventing an estimate", () => {
  render(<ExecutionBudget events={[event({ budget: { scope: "run_model_turns", limit: 16, used: 14, remaining: 2 }, required_remaining: 4 }, "agent.budget_insufficient")]} locale="en" />);
  expect(screen.getByRole("status")).toHaveTextContent("at least 4 more turns");
});

it("does not invent budgets for historical or malformed events", () => {
  render(<ExecutionBudget events={[event({}), event({ budget: { scope: "run_model_turns", used: "14", limit: 16, remaining: 2 } })]} locale="zh" />);
  expect(screen.queryByRole("region")).not.toBeInTheDocument();
});
