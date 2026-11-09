import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { JsonObject, RuntimeEvent } from "@veyra/api-contracts";
import { FinalizationFeedback } from "./FinalizationFeedback";
import { loopTimelineLabel } from "./studio-run-ui";

const event: RuntimeEvent = { schema_version: "1.0", event_id: "fixture", run_id: "run", sequence: 1, timestamp: "2026-10-13T12:00:00Z", node_id: "model", kind: "finalization.rejected", payload: { evidence_kind: "model_assessment", findings: [{ reason: "缺少尺寸数据", evidence: "当前输入未提供尺寸" }] } };
afterEach(cleanup);

describe("Finalization feedback", () => {
  it("names blind evidence assessment without claiming candidate acceptance", () => {
    const started: RuntimeEvent = { ...event, kind: "finalization.started", payload: { phase: "evidence" } };
    const { rerender } = render(<FinalizationFeedback events={[started]} locale="zh" />);
    expect(screen.getByText("正在核对原始资料，尚未交付")).toBeInTheDocument();
    expect(screen.queryByText("交付检查已通过")).not.toBeInTheDocument();
    rerender(<FinalizationFeedback events={[started, { ...event, kind: "finalization.failed", payload: { phase: "evidence", code: "agent_finalization_review_invalid", message: "Invalid source quote" } }]} locale="zh" />);
    expect(screen.getByText("原始资料核对")).toBeInTheDocument();
    expect(screen.getByText("Invalid source quote")).toBeInTheDocument();
  });
  it("shows concrete feedback without claiming independent verification", () => {
    render(<FinalizationFeedback events={[event]} locale="zh" />);
    expect(screen.getByText("候选尚未交付")).toBeInTheDocument();
    expect(screen.getByText("缺少尺寸数据")).toBeInTheDocument();
    expect(screen.getByText("当前输入未提供尺寸")).toBeInTheDocument();
    expect(screen.getByText("模型评审，非独立事实验证")).toBeInTheDocument();
  });

  it("does not leave an old rejection as current after acceptance", () => {
    render(<FinalizationFeedback events={[event, { ...event, sequence: 2, kind: "finalization.accepted", payload: { evidence_kind: "deterministic" } }]} locale="zh" />);
    expect(screen.getByText("交付检查已通过")).toBeInTheDocument();
    expect(screen.queryByText("缺少尺寸数据")).not.toBeInTheDocument();
  });

  it("distinguishes image generation from delivery", () => {
    expect(loopTimelineLabel("node.completed", { phase: "image" }, "zh")).toBe("图片候选已生成");
    expect(loopTimelineLabel("finalization.completed", {}, "zh")).toBe("审查意见已返回");
  });

  it("replaces old feedback with the concrete review failure stage", () => {
    render(<FinalizationFeedback events={[event, { ...event, sequence: 2, kind: "finalization.failed", payload: { phase: "pre_render", code: "runtime_timeout", published: false, provider_diagnostic: { timeout_seconds: 180, timeout_phase: "read" } } }]} locale="zh" />);
    expect(screen.getByText("审查未完成，候选尚未交付")).toBeInTheDocument();
    expect(screen.getByText("出图前审查")).toBeInTheDocument();
    expect(screen.getByText("审查请求超时。")).toBeInTheDocument();
    expect(screen.getByText(/超时阈值 180 秒/)).toBeInTheDocument();
    expect(screen.queryByText("缺少尺寸数据")).not.toBeInTheDocument();
    expect(screen.queryByText("规则检查")).not.toBeInTheDocument();
  });

  it.each(["zh", "en"] as const)("shows validated incomplete coverage directly in %s", (locale) => {
    render(<FinalizationFeedback events={[{ ...event, kind: "finalization.failed", payload: {
      phase: "candidate", code: "agent_finalization_review_invalid", message: "Finalization review must assess every declared criterion",
      diagnostic: { category: "coverage", expected_count: 13, received_count: 9, missing_criteria: [9, 10, 11, 12] },
    } }]} locale={locale} />);
    expect(screen.getByText(locale === "zh"
      ? "应有 13 项，收到 9 项，仍缺 4 项，候选未交付。"
      : "Expected 13 checks, received 9; 4 checks are missing. Candidate not delivered.")).toBeInTheDocument();
    expect(screen.getByText(locale === "zh" ? "缺失检查项：10、11、12、13" : "Missing checks: 10, 11, 12, 13")).toBeInTheDocument();
    expect(screen.queryByText("Finalization review must assess every declared criterion")).not.toBeInTheDocument();
    expect(screen.queryByText("交付检查已通过")).not.toBeInTheDocument();
  });

  it("does not interpret malformed or unknown diagnostics as coverage counts", () => {
    const base: JsonObject = { category: "coverage", expected_count: 13, received_count: 9, missing_criteria: [9, 10, 11, 12], raw: "PRIVATE_RAW_DIAGNOSTIC" };
    const malformed: JsonObject[] = [
      { expected_count: Infinity },
      { expected_count: Number.MAX_SAFE_INTEGER + 1 },
      { received_count: 9.5 },
      { received_count: -1 },
      { expected_count: "13" },
      { received_count: 10 },
      { missing_criteria: [9, 9, 11, 12] },
      { missing_criteria: [9, 10, 11, 13] },
      { category: "unknown" },
      { missing_criteria: null },
    ];
    for (const invalid of malformed) {
      const { unmount } = render(<FinalizationFeedback events={[{ ...event, kind: "finalization.failed", payload: {
        code: "agent_finalization_review_invalid", message: "Original review failure", diagnostic: { ...base, ...invalid },
      } }]} locale="zh" />);
      expect(screen.getByText("Original review failure")).toBeInTheDocument();
      expect(screen.queryByText(/应有.*收到.*仍缺/)).not.toBeInTheDocument();
      expect(screen.queryByText(/缺失检查项/)).not.toBeInTheDocument();
      expect(screen.queryByText(/PRIVATE_RAW_DIAGNOSTIC/)).not.toBeInTheDocument();
      unmount();
    }
  });

  it.each(["connected", "receiving", "receiving_result", "completed"])("shows %s progress without treating partial content as acceptance", (status) => {
    render(<FinalizationFeedback events={[event, { ...event, sequence: 2, kind: "finalization.progress", payload: { phase: "pre_render", status, elapsed_ms: 24000, event_count: 8, content_bytes: 100, published: false } }]} locale="zh" />);
    expect(screen.getByText("正在审查，尚未交付")).toBeInTheDocument();
    expect(screen.getByText("已用 24 秒")).toBeInTheDocument();
    expect(screen.queryByText("交付检查已通过")).not.toBeInTheDocument();
    expect(screen.queryByText("缺少尺寸数据")).not.toBeInTheDocument();
  });

  it("does not show an old rejection after a newer assessment completed", () => {
    render(<FinalizationFeedback events={[event, { ...event, sequence: 2, kind: "finalization.completed", payload: { phase: "pre_render", status: "pass" } }]} locale="zh" />);
    expect(screen.queryByText("缺少尺寸数据")).not.toBeInTheDocument();
    expect(screen.queryByText("交付检查已通过")).not.toBeInTheDocument();
  });

  it("does not leave progress active after the Run has stopped", () => {
    render(<FinalizationFeedback events={[{ ...event, kind: "finalization.progress", payload: { status: "receiving", published: false } }, { ...event, sequence: 2, kind: "run.cancelled", node_id: null, payload: {} }]} locale="zh" />);
    expect(screen.queryByText("正在审查，尚未交付")).not.toBeInTheDocument();
  });
});
