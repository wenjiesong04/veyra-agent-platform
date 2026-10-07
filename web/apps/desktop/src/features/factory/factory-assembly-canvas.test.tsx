import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FactorySession } from "@veyra/api-contracts";
import { FactoryAssemblyCanvas } from "./factory-assembly-canvas";

HTMLCanvasElement.prototype.getContext = vi.fn(() => null) as unknown as HTMLCanvasElement["getContext"];

afterEach(() => cleanup());

function reviewSession(): FactorySession {
  return {
    schema_version: "1.0",
    session_id: "session-1",
    project_id: "project-1",
    state: "review",
    ready: true,
    next_prompt: "",
    resource_plan: [],
    diagnostics: [],
    missing_capabilities: [],
    candidate: { name: "礼品包装设计师" },
    run_availability: "design_only",
    executes_drafts: false,
    revision: 1,
    created_at: "2026-09-27T00:00:00Z",
    updated_at: "2026-09-27T00:00:00Z",
    messages: [],
    blueprint: {
      nodes: [
        { id: "start", component_type: "Start" },
        { id: "analyze_item", component_type: "Model" },
        { id: "route_decision", component_type: "HumanApproval" },
        { id: "finalize_design", component_type: "Model" },
        { id: "refine_design", component_type: "Model" },
        { id: "output", component_type: "Output" },
      ],
      transitions: [
        { from: "start", port: "next", to: "analyze_item" },
        { from: "analyze_item", port: "next", to: "route_decision" },
        { from: "route_decision", port: "approved", to: "finalize_design" },
        { from: "route_decision", port: "rejected", to: "refine_design" },
        { from: "finalize_design", port: "next", to: "output" },
        { from: "refine_design", port: "next", to: "output" },
      ],
      ui_suggestions: {
        labels: { analyze_item: "物品识别与需求分析" },
        notes: { note_intro: { text: "用户上传想要包装的物品。\n预算、场合和风格都要写清楚。", width: 80, color: "amber" } },
      },
    },
  };
}

describe("Factory review canvas", () => {
  it("shows a blocked plan without a live clock, stage pulse, or creation actions", () => {
    const onApply = vi.fn();
    const onGenerate = vi.fn();
    render(
      <FactoryAssemblyCanvas
        locale="zh"
        session={{ ...reviewSession(), state: "ready", blocked_reason: "product_fidelity_invalid" }}
        busy={null}
        phase="planning"
        live
        stageStartedAt="2026-09-27T00:00:00Z"
        canGenerate
        canApply
        studioHref={null}
        createdAgentId={null}
        drafted={false}
        focusChild={false}
        embedded
        onClose={() => undefined}
        onGenerate={onGenerate}
        onApply={onApply}
        onRevise={() => undefined}
        onReject={() => undefined}
      />,
    );
    expect(screen.getByRole("heading", { name: "方案暂时无法生成" })).toBeInTheDocument();
    expect(screen.getByText(/尚未创建 Agent 或 Workflow/)).toBeInTheDocument();
    expect(screen.getByText(/可补充你希望它如何工作，再重新发送/)).toBeInTheDocument();
    expect(screen.getByText("方案未完整保留你的要求，因此没有创建。")).toBeInTheDocument();
    expect(screen.getByText("查看阻塞原因").closest("details")).not.toHaveAttribute("open");
    expect(screen.queryByText(/已进行|这一步仍在进行/)).not.toBeInTheDocument();
    expect(screen.queryByText("正在生成方案")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "方案画布" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "审查并创建草稿" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "生成 Blueprint" })).not.toBeInTheDocument();
    expect(document.querySelector('[data-current="true"]')).toBeNull();
    expect(onApply).not.toHaveBeenCalled();
    expect(onGenerate).not.toHaveBeenCalled();
  });

  it("keeps a failed operation still and explains the next step", () => {
    render(
      <FactoryAssemblyCanvas
        locale="en"
        session={null}
        busy={null}
        phase="failed"
        live
        stageStartedAt="2026-09-27T00:00:00Z"
        canGenerate={false}
        canApply={false}
        studioHref={null}
        createdAgentId={null}
        drafted={false}
        focusChild={false}
        embedded
        onClose={() => undefined}
        onApply={() => undefined}
      />,
    );
    expect(screen.getByRole("heading", { name: "Plan generation failed" })).toBeInTheDocument();
    expect(screen.getByText(/Review the error above, address its cause/)).toBeInTheDocument();
    expect(screen.queryByText(/Running|Compiling the Agent/)).not.toBeInTheDocument();
    expect(document.querySelector('[data-current="true"]')).toBeNull();
  });

  it("shows a historical blocking reason without relying on the current session", () => {
    render(<FactoryAssemblyCanvas locale="zh" session={null} busy={null} phase="blocked"
      planSummary={{ blocked_reason: "State requirement cannot be represented" }}
      canGenerate={false} canApply={false} studioHref={null} createdAgentId={null} drafted={false} focusChild={false} embedded
      onClose={() => undefined} onApply={() => undefined} />);
    expect(screen.getByText("查看阻塞原因")).toBeInTheDocument();
    expect(screen.getByText("当前无法按要求保存和恢复任务状态。")).toBeInTheDocument();
  });

  it("shows product shape and execution plan on review", () => {
    render(
      <FactoryAssemblyCanvas
        locale="zh"
        session={{
          ...reviewSession(),
          execution_kind: "workflow",
          target_kind: "workflow",
          product_shape: "AGENT_WORKFLOW",
          proposal_preview: {
            product_shape: { shape: "AGENT_WORKFLOW", status: "decided", reason: "structure" },
            agents: [{ id: "analyzer", name: "Analyzer" }],
            workflow: true,
            stages: [{ id: "identify", summary: "识别商品" }],
            flow: [{ id: "identify", kind: "agent_call", why: "Vision reasoning", source: "多图" }],
            business_approvals: ["business-approval"],
            tool_approvals: [],
            missing_required: [{ capability: "image_generation" }],
            models: [{ slot: "image", required: ["image_generation"], optional: [], reason: "最终生成包装效果图", source: "用户需求", status: "needs_setup", selected_model_profile_id: null, issue: { code: "model_capability_missing", message: "No image model", missing: ["image_generation"], unknown: [], unsupported: [] } }],
            persistent_state: { entity: "SecondhandItem" },
          },
        }}
        busy={null}
        canGenerate={false}
        canApply
        studioHref={null}
        createdAgentId={null}
        drafted={false}
        focusChild={false}
        embedded
        onClose={() => undefined}
        onApply={() => undefined}
        onRevise={() => undefined}
        onReject={() => undefined}
      />,
    );
    expect(screen.getByRole("region", { name: "产品形态" })).toBeInTheDocument();
    expect(screen.getByText("AGENT_WORKFLOW")).toBeInTheDocument();
    expect(screen.getByText(/识别商品/)).toBeInTheDocument();
    expect(screen.getByText(/业务审批/)).toBeInTheDocument();
    expect(screen.getByText(/为什么需要：最终生成包装效果图/)).toBeInTheDocument();
    expect(screen.getByText(/缺少模型能力：图片生成/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "配置兼容模型" }).getAttribute("href")).toContain("requiredCapability=image_generation");
    expect(screen.getByRole("button", { name: "修改方案" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "取消" })).toBeEnabled();
  });

  it("renders the review canvas", () => {
    render(
      <FactoryAssemblyCanvas
        locale="zh"
        session={reviewSession()}
        busy={null}
        canGenerate={false}
        canApply={false}
        studioHref={null}
        createdAgentId={null}
        drafted={false}
        focusChild={false}
        embedded
        onClose={() => undefined}
        onApply={() => undefined}
      />,
    );
    expect(screen.getByRole("region", { name: "方案画布" })).toBeInTheDocument();
    expect(screen.getByText("物品识别与需求分析")).toBeInTheDocument();
    expect(screen.getByText(/用户上传想要包装的物品/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zoom In" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Zoom Out" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Fit View" })).toBeEnabled();
    expect(document.querySelector(".canvas-note__scroll")).toBeInTheDocument();
    expect(document.querySelector(".canvas-note__scroll")).toHaveClass("nowheel");
    const note = document.querySelector(".react-flow__node-noteNode") as HTMLElement;
    expect(Number.parseFloat(note.style.width)).toBeGreaterThanOrEqual(260);
    expect(note.style.pointerEvents).toBe("all");
    expect(Number.parseFloat(note.style.height)).toBeLessThanOrEqual(280);
    const noteTop = Number.parseFloat(note.style.transform.match(/translate\(([-\d.]+)px,\s*([-\d.]+)px\)/)?.[2] ?? "0");
    const flowTops = [...document.querySelectorAll(".react-flow__node-agentNode")].map((node) => Number.parseFloat((node as HTMLElement).style.transform.match(/translate\(([-\d.]+)px,\s*([-\d.]+)px\)/)?.[2] ?? "0"));
    expect(noteTop + Number.parseFloat(note.style.height)).toBeLessThan(Math.min(...flowTops));
  });

  it("shows an Agent capability proposal instead of a DAG", () => {
    render(
      <FactoryAssemblyCanvas
        locale="zh"
        session={{
          ...reviewSession(),
          execution_kind: "loop",
          target_kind: "agent",
          candidate: { name: "Translation Agent" },
          resource_plan: [
            {
              reference: "veyra.tool.web.search@1.0.0",
              kind: "tool",
              availability: "ready",
              runtime_status: "supported",
              name: "Web Search",
              bind_status: "will_bind",
            },
            {
              reference: "veyra.tool.filesystem.read@1.0.0",
              kind: "tool",
              availability: "ready",
              runtime_status: "supported",
              name: "Filesystem Read",
              bind_status: "already_bound",
            },
            {
              reference: "veyra.tool.http.request@1.0.0",
              kind: "tool",
              availability: "ready",
              runtime_status: "supported",
              name: "HTTP Request",
              bind_status: "requires_configuration",
            },
            {
              reference: "capability.image_generation",
              kind: "capability",
              availability: "unavailable",
              runtime_status: "runtime_not_supported",
              name: "Image Generation",
              bind_status: "missing",
              capability: "image_generation",
              reason: "Missing capability: Image Generation",
            },
          ],
          blueprint: {
            goal: "把中文翻译成自然英语",
            inputs: { text: "string" },
            outputs: { translation: "string" },
            nodes: [{ id: "model", component_type: "Model", system_prompt: "Translate into natural English." }],
            ui_suggestions: { bindings: {} },
          },
        }}
        busy={null}
        canGenerate={false}
        canApply={false}
        studioHref={null}
        createdAgentId={null}
        drafted={false}
        focusChild={false}
        embedded
        onClose={() => undefined}
        onApply={() => undefined}
      />,
    );
    expect(screen.getByRole("region", { name: "Agent 方案" })).toBeInTheDocument();
    expect(screen.getByText("Translation Agent")).toBeInTheDocument();
    expect(screen.getByText(/将创建 Agent/)).toBeInTheDocument();
    expect(screen.getByText(/将加入 Project/)).toBeInTheDocument();
    expect(screen.getByText(/已在 Project 中/)).toBeInTheDocument();
    expect(screen.getByText(/还需配置工具/)).toBeInTheDocument();
    expect(screen.getByText(/缺失能力/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "方案画布" })).not.toBeInTheDocument();
  });

  it("offers a Factory draft for generatable missing capabilities only", () => {
    const onApproveFactory = vi.fn();
    render(
      <FactoryAssemblyCanvas
        locale="zh"
        session={{
          ...reviewSession(),
          execution_kind: "loop",
          target_kind: "agent",
          candidate: { name: "Comparison Agent" },
          resource_plan: [
            {
              reference: "capability.structured_comparison_method",
              kind: "capability",
              availability: "unavailable",
              runtime_status: "runtime_not_supported",
              name: "Structured Comparison Method",
              bind_status: "missing",
              capability: "structured_comparison_method",
              factory_status: "generatable",
              factory_strategy: "skill_instruction",
            },
            {
              reference: "capability.image_generation",
              kind: "capability",
              availability: "unavailable",
              runtime_status: "runtime_not_supported",
              name: "Image Generation",
              bind_status: "missing",
              capability: "image_generation",
              factory_status: "unsupported",
              factory_strategy: "none",
            },
          ],
          resource_factory_plans: [
            {
              capability: "structured_comparison_method",
              status: "generatable",
              strategy: "skill_instruction",
              can_generate: true,
              reason: "Veyra can create a quarantined Skill",
              risk_level: "low",
              resource_kind: "skill",
              requirements: [],
              draft: { name: "Structured Comparison Method", kind: "skill" },
              snapshot_hash: "a".repeat(64),
            },
            {
              capability: "image_generation",
              status: "unsupported",
              strategy: "none",
              can_generate: false,
              reason: "No local Runtime exists for this capability",
              risk_level: "medium",
              requirements: [],
            },
          ],
          blueprint: {
            goal: "capability: structured_comparison_method",
            inputs: { request: "string" },
            outputs: { result: "string" },
            nodes: [{ id: "model", component_type: "Model", system_prompt: "Compare." }],
            ui_suggestions: { bindings: {} },
          },
        }}
        busy={null}
        canGenerate={false}
        canApply={false}
        studioHref={null}
        createdAgentId={null}
        drafted={false}
        focusChild={false}
        embedded
        onClose={() => undefined}
        onApply={() => undefined}
        onApproveFactory={onApproveFactory}
      />,
    );
    expect(screen.getByText(/Veyra 可以创建/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "审核草稿并发布" })).toBeEnabled();
    expect(screen.getByText("当前无法生成")).toBeInTheDocument();
  });
});
