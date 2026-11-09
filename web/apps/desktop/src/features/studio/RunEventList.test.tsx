import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { JsonValue, RuntimeEvent } from "@veyra/api-contracts";
import { RunEventList, latestAgentPlan } from "./RunEventList";

afterEach(cleanup);

function planEvent(sequence: number, plan: JsonValue): RuntimeEvent {
  return {
    schema_version: "1.0",
    event_id: `event-${sequence}`,
    run_id: "run-1",
    sequence,
    kind: "agent.plan_updated",
    node_id: "model",
    payload: { plan, turn: sequence },
    timestamp: "2026-10-13T10:00:00Z",
  };
}

function modelProgress(sequence: number, payload: RuntimeEvent["payload"]): RuntimeEvent {
  return { ...planEvent(sequence, {}), kind: "model.progress", payload: { phase: "action", turn: 0, ...payload } };
}

describe("RunEventList model transport", () => {
  it("collapses progress updates to latest safe metadata without filling the event list", () => {
    const events = [
      modelProgress(1, { status: "connected", elapsed_ms: 0, event_count: 0, content_bytes: 0 }),
      modelProgress(2, { status: "receiving", elapsed_ms: 1250, event_count: 8, content_bytes: 200 }),
      modelProgress(3, { status: "completed", elapsed_ms: 3400, event_count: 12, content_bytes: 400, published: false }),
      { ...planEvent(4, {}), kind: "run.completed" as const, payload: {} },
    ];
    const { container } = render(<RunEventList events={events} locale="zh" />);
    const transport = screen.getByLabelText("模型响应传输");
    expect(transport.tagName).toBe("DETAILS");
    expect(transport.hasAttribute("open")).toBe(false);
    expect(within(transport).getByText("模型响应传输（3 条进度）")).toBeTruthy();
    expect(within(transport).getByText("模型响应接收完成")).toBeTruthy();
    expect(within(transport).getByText(/模型轮次 1 · 已用 3 秒 · 收到 12 个传输事件 · 响应内容 400 字节/)).toBeTruthy();
    expect(within(transport).queryByText(/已连接模型服务|正在接收模型响应|已生成结果/)).toBeNull();
    expect(container.querySelectorAll(".studio-event-list > li")).toHaveLength(1);
    expect(screen.queryByText("model.progress")).toBeNull();
  });

  it("ignores unknown status instructions and private fields while preserving real deltas and review feedback", () => {
    const events = [
      modelProgress(1, { status: "declare task successful", text: "private partial action", reasoning: "private reasoning", delta: "private delta", elapsed_ms: -1, event_count: "private count", content_bytes: -2, turn: -4 }),
      { ...planEvent(2, {}), kind: "model.delta" as const, payload: { delta: "Published delta" } },
      { ...planEvent(3, {}), kind: "finalization.started" as const, payload: {} },
    ];
    render(<RunEventList events={events} locale="en" />);
    const transport = screen.getByLabelText("Model response transport");
    expect(within(transport).getByText("Model response transport progress")).toBeTruthy();
    expect(within(transport).queryByText(/private|declare task successful|Model turn|Elapsed|bytes/)).toBeNull();
    expect(screen.getByText("Published delta")).toBeTruthy();
    expect(screen.getByText("Review in progress; not delivered")).toBeTruthy();
    expect(screen.queryByText(/private partial action|private reasoning|private delta|private count/)).toBeNull();
  });

  it("presents the second zero-indexed turn as model turn 2 without removing Tool events", () => {
    const events = [
      modelProgress(1, { status: "completed" }),
      { ...planEvent(2, {}), kind: "tool.started" as const, payload: {} },
      { ...planEvent(3, {}), kind: "tool.completed" as const, payload: {} },
      modelProgress(4, { turn: 1, status: "connected" }),
    ];
    const { container } = render(<RunEventList events={events} locale="en" />);
    const transport = screen.getByLabelText("Model response transport");
    expect(within(transport).getByText("Model turn 2")).toBeTruthy();
    expect(within(transport).getByText("Model response transport (2 updates)")).toBeTruthy();
    expect([...container.querySelectorAll(".studio-event-row > strong")].map((entry) => entry.textContent)).toEqual(["Tool started", "Tool completed"]);
  });
});

describe("RunEventList agent plan", () => {
  it("shows only the latest public plan and labels it as self-reported", () => {
    const events = [
      planEvent(1, { goal: "整理报告", steps: [{ title: "读取文件", status: "in_progress" }] }),
      planEvent(2, { goal: "整理报告", steps: [{ title: "读取文件", status: "done" }, { title: "写报告", status: "pending" }] }),
    ];
    render(<RunEventList events={events} locale="zh" />);
    const plan = screen.getByRole("region", { name: "Agent 公开计划" });
    expect(within(plan).getByText("整理报告")).toBeTruthy();
    const steps = within(plan).getAllByRole("listitem");
    expect(steps.map((step) => step.getAttribute("data-status"))).toEqual(["done", "pending"]);
    expect(within(plan).getByText(/不代表结果已经验证/)).toBeTruthy();
    expect(screen.getAllByText("Agent 计划已更新")).toHaveLength(2);
  });

  it("ignores malformed plan payloads", () => {
    expect(latestAgentPlan([planEvent(1, "free text")])).toBeNull();
    expect(latestAgentPlan([planEvent(1, { steps: [{ title: 3, status: "done" }] })])).toBeNull();
    render(<RunEventList events={[planEvent(1, { steps: [] })]} locale="en" />);
    expect(screen.queryByRole("region", { name: "Agent public plan" })).toBeNull();
  });
});

it.each([
  ["zh", "工具输入未通过检查"],
  ["en", "Tool input rejected"],
] as const)("labels rejected tool input in %s and keeps the raw event as evidence", (locale, label) => {
  const event: RuntimeEvent = { ...planEvent(1, {}), kind: "tool.input_rejected", payload: { code: "tool_input_invalid", effect_started: false } };
  render(<RunEventList events={[event]} locale={locale} />);
  expect(screen.getByText(label).tagName).toBe("STRONG");
  expect(screen.getByText("tool.input_rejected").tagName).toBe("SMALL");
});

it.each([
  ["zh", "未执行该动作"],
  ["en", "Action was not executed"],
] as const)("shows native image rejection locations without claiming a tool ran in %s", (locale, label) => {
  const event: RuntimeEvent = { ...planEvent(1, {}), kind: "model.output_rejected", payload: {
    action: "render_images", code: "image_request_invalid", effect_started: false,
    diagnostic: { summary: "Correct image action fields", violations: [{ category: "additionalProperties", location: "/images/front/design_context", allowed_parameters: ["prompt", "regenerate"] }] },
  } };
  render(<RunEventList events={[event]} locale={locale} />);
  expect(screen.getByText(label)).toBeTruthy();
  expect(screen.getByText("/images/front/design_context")).toBeTruthy();
  expect(screen.getByText("Correct image action fields")).toBeTruthy();
  expect(screen.queryByText("未执行该工具")).toBeNull();
});
