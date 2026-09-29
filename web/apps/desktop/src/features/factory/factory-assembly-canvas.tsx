import { useEffect, useMemo, useState, type ReactNode } from "react";
import { LayoutPanelTop, X } from "lucide-react";
import { Background, ConnectionLineType, Controls, MarkerType, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { FactoryResourcePlanItem, FactorySession, FlowNode, JsonObject, ResourceFactoryPlan, StudioNoteColor } from "@veyra/api-contracts";
import { Alert, Button, IconButton, LinkButton, StatusBadge } from "@veyra/ui";
import { blueprintGraph, blueprintPresentation } from "./factory-blueprint";
import { runningClock, type WorkbenchPhase } from "../builder/workbench-phase";
import { CanvasEdgeActionsProvider, FlowEdge, type FlowEdgeData } from "../studio/canvas-edge";
import { studioNodeTypes } from "../studio/canvas-nodes";
import type { CanvasNodeData } from "../studio/graph";
import { centerNoteAboveGraph, labeledNodeSize, layoutExecutionGraph } from "../studio/graph-layout";
import { componentFor } from "../studio/registry";

type Locale = "zh" | "en";
type Busy = "message" | "generate" | "apply" | "draft" | null;

const copy = {
  zh: {
    canvas: "工作台",
    understanding: "正在理解需求",
    planning: "正在生成方案",
    compiling: "正在组装 Agent",
    validating: "正在验证结构",
    review: "审查方案",
    proposalHeading: "准备创建的内容",
    missing: "缺少能力",
    completed: "下一步",
    abandoned: "会话已放弃",
    plan: "将引用这些已登记资源",
    emptyPlan: "确认创建意图后，这里会显示正在构建的对象。",
    assembling: "正在根据规格编译 Agent 或 Workflow。",
    missingHint: "缺失能力会写入隔离 Catalog。它们不可执行，Factory 也不能再选用，直到人工审核并登记。",
    quarantine: "写入隔离草稿",
    quarantining: "正在写入…",
    quarantined: "已写入隔离 Catalog，不可执行、不可被 Factory 选用。",
    generate: "生成 Blueprint",
    generatingBtn: "正在生成…",
    apply: "审查并创建草稿",
    revise: "修改方案",
    reject: "取消",
    applying: "正在创建…",
    studio: "打开 Studio 检查草稿",
    created: "请检查草稿和所需配置，再在 Studio 运行校验与试运行。",
    noExecute: "Factory 不会执行草稿，也不会自动运行生成的工具代码。",
    waiting: "这一步仍在进行，不会因为等待被中断。",
    child: "将创建为当前 Agent 的子版本",
    diagnostics: "修复诊断",
    availability: "运行准备",
    reviewReady: "方案待确认",
  },
  en: {
    canvas: "Workbench",
    understanding: "Understanding the request",
    planning: "Generating the plan",
    compiling: "Assembling the Agent",
    validating: "Validating structure",
    review: "Review proposal",
    proposalHeading: "What Veyra is proposing to create",
    missing: "Missing capabilities",
    completed: "Next steps",
    abandoned: "Session abandoned",
    plan: "These registered catalog resources will be used",
    emptyPlan: "Once create intent is known, the object being built appears here.",
    assembling: "Compiling the Agent or Workflow from the specification.",
    missingHint: "Missing capabilities become quarantined catalog drafts. They are not executable and Factory cannot select them until they are reviewed and registered.",
    quarantine: "Create quarantined drafts",
    quarantining: "Writing drafts…",
    quarantined: "Wrote quarantined catalog drafts. They are not executable and Factory cannot select them.",
    generate: "Generate Blueprint",
    generatingBtn: "Generating…",
    apply: "Review and create Draft",
    revise: "Modify plan",
    reject: "Cancel",
    applying: "Creating…",
    studio: "Open Studio to review Draft",
    created: "Review the Draft and its setup, then validate and test-run it in Studio.",
    noExecute: "Factory never executes drafts and does not auto-run generated tool code.",
    waiting: "This step is still running and will not be cut off for waiting.",
    child: "Will be created as a child of the current Agent",
    diagnostics: "Repair diagnostics",
    availability: "Run setup",
    reviewReady: "Review ready",
  },
} as const;

const stageOrder: WorkbenchPhase[] = ["understanding", "planning", "compiling", "validating", "review", "completed"];

function stageLabel(state: WorkbenchPhase | FactorySession["state"], locale: Locale): string {
  const text = copy[locale];
  if (state === "missing_capability" || state === "missing") return text.missing;
  if (state === "abandoned") return text.abandoned;
  if (state === "collecting" || state === "ready" || state === "generating") return text.understanding;
  if (state in text) return text[state as keyof typeof text] as string;
  return text.understanding;
}

function availabilityTone(value: FactorySession["run_availability"]): "good" | "warn" | "bad" | "neutral" {
  return value === "ready" ? "good" : value === "unavailable" ? "bad" : "warn";
}

const flowComponentTypes = new Set<FlowNode["component_type"]>([
  "Start", "Agent", "Model", "AgentCall", "Tool", "CustomComponent", "Condition", "Transform", "HumanApproval", "Verifier", "Output",
]);

function flowComponentType(value: string): FlowNode["component_type"] {
  return flowComponentTypes.has(value as FlowNode["component_type"]) ? value as FlowNode["component_type"] : "Transform";
}

function noteColor(value: string): StudioNoteColor {
  if (value === "teal" || value === "amber" || value === "violet" || value === "slate") return value;
  return "amber";
}

export function noteFrame(text: string): { width: number; height: number } {
  const lines = text.split("\n");
  const longest = Math.max(...lines.map((line) => line.length), 1);
  const cjk = /[\u3400-\u9fff]/.test(text);
  const charWidth = cjk ? 13 : 7.2;
  const width = Math.round(Math.min(420, Math.max(260, longest * charWidth + 40)));
  const charsPerLine = Math.max(12, Math.floor((width - 36) / charWidth));
  const wrapped = lines.reduce((sum, line) => sum + Math.max(1, Math.ceil(Math.max(line.length, 1) / charsPerLine)), 0);
  return { width, height: Math.min(280, Math.max(148, 34 + wrapped * 18 + 12)) };
}

const reviewEdgeTypes = { flowEdge: FlowEdge };

function reviewCanvas(blueprint: JsonObject | null, locale: Locale = "zh"): { nodes: Node<CanvasNodeData>[]; edges: Edge<FlowEdgeData>[] } {
  const graph = blueprintGraph(blueprint);
  const presentation = blueprintPresentation(blueprint);
  const sized = graph.nodes.map((node) => {
    const componentType = flowComponentType(node.component_type);
    const component = componentFor(componentType);
    const title = presentation.labels[node.id] ?? (locale === "zh" ? component.labelZh : component.label);
    const size = labeledNodeSize(title, node.id, component.ports.length);
    return { node, componentType, title, size };
  });
  const layoutNodes = sized.map((item) => ({
    id: item.node.id,
    component_type: item.componentType,
    width: item.size.width,
    height: item.size.height,
  }));
  const positions = layoutExecutionGraph(layoutNodes, graph.transitions);
  const nodes: Node<CanvasNodeData>[] = sized.map((item) => ({
    id: item.node.id,
    type: "agentNode",
    position: positions[item.node.id] ?? { x: 0, y: 0 },
    draggable: false,
    connectable: false,
    selectable: false,
    width: item.size.width,
    height: item.size.height,
    style: { width: item.size.width, height: item.size.height },
    data: {
      flow: { id: item.node.id, component_type: item.componentType },
      title: item.title,
      readOnly: true,
      runState: "idle",
    },
  }));
  if (presentation.note) {
    const frame = noteFrame(presentation.note.text);
    nodes.push({
      id: "note_intro",
      type: "noteNode",
      position: centerNoteAboveGraph(layoutNodes, positions, frame.width, frame.height, 48),
      draggable: false,
      connectable: false,
      selectable: false,
      className: "nowheel nopan",
      width: frame.width,
      height: frame.height,
      style: { width: frame.width, height: frame.height, pointerEvents: "all" },
      data: {
        readOnly: true,
        note: { text: presentation.note.text, color: noteColor(presentation.note.color), width: frame.width, height: frame.height, manual_position: false },
      },
    });
  }
  const edges = graph.transitions.flatMap((edge) => {
    const source = nodes.find((node) => node.id === edge.from);
    const target = nodes.find((node) => node.id === edge.to);
    const sourceType = source?.data.flow?.component_type;
    if (!source || !target || !sourceType) return [];
    const ports = componentFor(sourceType).ports;
    const port = ports.includes(edge.port) ? edge.port : ports[0];
    if (!port) return [];
    return [{
      id: `${edge.from}:${edge.port}:${edge.to}`,
      source: edge.from,
      target: edge.to,
      sourceHandle: port,
      type: "flowEdge",
      data: { port: edge.port, readOnly: true },
      markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    }];
  });
  return { nodes, edges };
}

function BlueprintFlow({
  session,
  locale,
}: {
  session: FactorySession | null;
  locale: Locale;
}) {
  const canvas = useMemo(() => reviewCanvas(session?.blueprint ?? null, locale), [session?.blueprint, locale]);
  if (!canvas.nodes.length) return null;
  const zh = locale === "zh";
  return (
    <div className="factory-review-canvas studio-canvas" role="region" aria-label={zh ? "方案画布" : "Blueprint canvas"}>
      {isWorkflowProposal(session) ? <p className="factory-canvas-kicker">{zh ? "将创建 Workflow 编排。" : "This will create a Workflow."}</p> : null}
      <CanvasEdgeActionsProvider value={{
        locale,
        hoveredEdgeId: null,
        onSelect: () => undefined,
        onInsert: () => undefined,
        onDelete: () => undefined,
        onNoteChange: () => undefined,
      }}>
        <ReactFlow<Node<CanvasNodeData>, Edge<FlowEdgeData>>
          nodes={canvas.nodes}
          edges={canvas.edges}
          nodeTypes={studioNodeTypes}
          edgeTypes={reviewEdgeTypes}
          connectionLineType={ConnectionLineType.SmoothStep}
          nodesDraggable={false}
          nodesConnectable={false}
          edgesReconnectable={false}
          elementsSelectable={false}
          panOnDrag
          zoomOnScroll
          zoomOnPinch
          zoomOnDoubleClick
          minZoom={0.25}
          maxZoom={1.75}
          fitView
          fitViewOptions={{ padding: 0.2, minZoom: 0.25, maxZoom: 1 }}
          proOptions={{ hideAttribution: true }}
          deleteKeyCode={null}
        >
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </CanvasEdgeActionsProvider>
    </div>
  );
}

function bindStatusLabel(status: FactoryResourcePlanItem["bind_status"], locale: Locale): string | null {
  if (!status) return null;
  const zh = locale === "zh";
  if (status === "already_bound") return zh ? "已在 Project 中" : "Already in Project";
  if (status === "will_bind") return zh ? "将加入 Project" : "Will add to Project";
  if (status === "requires_configuration" || status === "needs_configuration") {
    return zh ? "需要配置" : "Needs configuration";
  }
  if (status === "missing") return zh ? "缺失能力" : "Missing capability";
  return zh ? "不可用" : "Unavailable";
}

function proposalBindLabel(item: FactoryResourcePlanItem, locale: Locale): string | null {
  if (item.bind_status === "requires_configuration" || item.bind_status === "needs_configuration") {
    if (item.kind === "capability" && /model/i.test(item.reference)) return locale === "zh" ? "还需配置模型" : "Model setup needed";
    if (item.kind === "tool") return locale === "zh" ? "还需配置工具" : "Tool setup needed";
  }
  return bindStatusLabel(item.bind_status, locale);
}

function resourceKindLabel(kind: string, locale: Locale): string {
  const labels: Record<string, { zh: string; en: string }> = {
    model: { zh: "模型", en: "Model" },
    tool: { zh: "工具", en: "Tool" },
    mcp_tool: { zh: "工具", en: "Tool" },
    component: { zh: "组件", en: "Component" },
    skill: { zh: "技能", en: "Skill" },
    knowledge: { zh: "知识资料", en: "Knowledge" },
    policy: { zh: "策略", en: "Policy" },
    capability: { zh: "能力", en: "Capability" },
  };
  return labels[kind]?.[locale] ?? kind;
}

function runAvailabilityLabel(value: FactorySession["run_availability"], locale: Locale): string {
  if (value === "ready") return locale === "zh" ? "资源已解析；仍需在 Studio 试运行" : "Resources resolved; test in Studio";
  if (value === "requires_configuration") return locale === "zh" ? "还需配置模型或工具" : "Model or Tool setup needed";
  if (value === "design_only") return locale === "zh" ? "当前仅可设计，不能试运行" : "Design only; test run unavailable";
  return locale === "zh" ? "缺少必要能力，当前不能运行" : "A required capability is unavailable";
}

function readableResourceReference(reference: string): string {
  const withoutVersion = reference.split("@")[0] ?? reference;
  return withoutVersion
    .replace(/^veyra\.(tool|component)\./, "")
    .replace(/^capability\./, "")
    .replace(/[._-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function readableCapabilityReference(reference: string): string {
  return /^(?:veyra\.|capability\.)/.test(reference) ? readableResourceReference(reference) : reference;
}

function ResourcePlan({ items, locale }: { items: FactoryResourcePlanItem[]; locale: Locale }) {
  if (!items.length) return null;
  return (
    <div className="factory-canvas-plan">
      <p className="factory-canvas-kicker">{copy[locale].plan}</p>
      {items.map((item) => {
        const bind = bindStatusLabel(item.bind_status, locale);
        return (
          <div className="draft-node" key={item.reference}>
            <span>{item.kind}</span>
            <div>
              <strong>{item.name || item.reference}</strong>
              <small>{item.availability} · {item.runtime_status}{bind ? ` · ${bind}` : ""}</small>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function isRecord(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isWorkflowProposal(session: FactorySession | null): boolean {
  if (!session) return false;
  if (session.execution_kind === "workflow" || session.target_kind === "workflow") return true;
  const nodes = session.blueprint && Array.isArray(session.blueprint.nodes) ? session.blueprint.nodes : [];
  return nodes.some((item) => isRecord(item) && item.component_type === "AgentCall");
}

function FactoryMissingAction({
  locale,
  plan,
  busy,
  onApprove,
}: {
  locale: Locale;
  plan: ResourceFactoryPlan;
  busy?: Busy;
  onApprove?: (capability: string) => void;
}) {
  const zh = locale === "zh";
  if (plan.status === "generatable" && plan.can_generate) {
    const draftName = typeof plan.draft?.name === "string" ? plan.draft.name : plan.capability.replaceAll("_", " ");
    const kindLabel = plan.strategy === "skill_instruction" ? (zh ? "技能" : "Skill") : (zh ? "工具包装" : "Tool wrapper");
    return (
      <div className="draft-note">
        <p>{zh ? "Veyra 可以创建" : "Veyra can create"}: {draftName} · {kindLabel}</p>
        {plan.strategy === "http_tool_wrapper" && plan.draft ? (
          <p>
            {zh ? "基础适配器" : "Base adapter"}: {String(plan.draft.spec && typeof plan.draft.spec === "object" && "base_adapter" in plan.draft.spec ? plan.draft.spec.base_adapter : "veyra.runtime.http.request")}
          </p>
        ) : null}
        {onApprove && plan.draft && !plan.published ? (
          <Button size="sm" disabled={Boolean(busy)} onClick={() => onApprove(plan.capability)}>
            {zh ? "审核草稿并发布" : "Review draft"}
          </Button>
        ) : null}
      </div>
    );
  }
  if (plan.status === "requires_user_configuration") {
    return <p>{zh ? "需要配置后才能生成：" : "Needs configuration: "}{(plan.requirements || []).join(", ")}</p>;
  }
  if (plan.status === "requires_external_integration") {
    return <p>{zh ? "需要已有外部集成" : "Requires an existing external integration"}</p>;
  }
  return <p>{zh ? "当前无法生成" : "Not currently generatable"}</p>;
}

function isLoopProposal(session: FactorySession | null): boolean {
  if (!session) return false;
  if (isWorkflowProposal(session)) return false;
  return session.execution_kind === "loop" || session.target_kind === "agent";
}

function CapabilityProposal({
  session,
  locale,
  busy,
  onApproveFactory,
}: {
  session: FactorySession;
  locale: Locale;
  busy?: Busy;
  onApproveFactory?: (capability: string) => void;
}) {
  const zh = locale === "zh";
  const blueprint = session.blueprint;
  const name = session.candidate?.name || (zh ? "Agent" : "Agent");
  const goal = typeof blueprint?.goal === "string" ? blueprint.goal : session.next_prompt;
  const inputs = isRecord(blueprint?.inputs) ? Object.keys(blueprint.inputs) : [];
  const outputs = isRecord(blueprint?.outputs) ? Object.keys(blueprint.outputs) : [];
  const nodes = Array.isArray(blueprint?.nodes) ? blueprint.nodes : [];
  const model = nodes.find((item) => isRecord(item) && (item.component_type === "Model" || item.component_type === "Agent"));
  const instructions = isRecord(model) && typeof model.system_prompt === "string" ? model.system_prompt : "";
  const ui = isRecord(blueprint?.ui_suggestions) ? blueprint.ui_suggestions : {};
  const bindings = isRecord(ui) && isRecord(ui.bindings) ? Object.values(ui.bindings) : [];
  const tools = bindings.flatMap((item) => {
    if (!isRecord(item)) return [];
    if (item.kind !== "tool" && item.kind !== "mcp_tool") return [];
    return typeof item.reference === "string" ? [item.reference] : [];
  });
  const resources = (session.resource_plan ?? []).filter((item) => item.bind_status);
  const toolNames = tools.map((reference) => resources.find((item) => item.reference === reference)?.name || readableResourceReference(reference));
  const factoryPlans = session.resource_factory_plans ?? [];
  return (
    <div className="factory-capability-proposal" role="region" aria-label={zh ? "Agent 方案" : "Agent proposal"}>
      <p className="factory-canvas-kicker">{zh ? "将创建 Agent，而不是固定 DAG。" : "This will create an Agent, not a fixed DAG."}</p>
      <section className="draft-note factory-proposal-summary">
        <span className="ui-eyebrow">{copy[locale].proposalHeading}</span>
        <strong>{name}</strong>
        {goal ? <p className="factory-proposal-goal">{goal}</p> : null}
        <div className="factory-proposal-contract">
          <p><span>{zh ? "输入" : "Inputs"}</span>{inputs.join(", ") || (zh ? "无" : "None")}</p>
          <p><span>{zh ? "输出" : "Outputs"}</span>{outputs.join(", ") || (zh ? "无" : "None")}</p>
          <p><span>{zh ? "使用工具" : "Tools"}</span>{toolNames.join(", ") || (zh ? "由模型自主处理，不绑定固定工具" : "No fixed Tool binding; the model may use permitted resources")}</p>
        </div>
        {resources.length ? (
          <div className="factory-proposal-resources">
            <strong>{zh ? "所需资源" : "Required resources"}</strong>
            {resources.map((item) => {
              const bind = proposalBindLabel(item, locale);
              const factory = factoryPlans.find((plan) => plan.capability === item.capability);
              return (
                <div className="factory-proposal-resource" key={item.reference}>
                  <div>
                    <strong>{item.name || readableResourceReference(item.reference)}</strong>
                    <small>{resourceKindLabel(item.kind, locale)}{bind ? ` · ${bind}` : ""}{item.source_count !== undefined ? (zh ? ` · ${item.source_count} 个来源` : ` · ${item.source_count} sources`) : ""}</small>
                  </div>
                  {item.reason || item.reference ? (
                    <details>
                      <summary>{zh ? "查看检查详情" : "Review details"}</summary>
                      {item.reason ? <p>{item.reason}</p> : null}
                      <code>{item.reference}</code>
                    </details>
                  ) : null}
                  {item.bind_status === "missing" && factory ? (
                    <FactoryMissingAction
                      locale={locale}
                      plan={factory}
                      busy={busy}
                      onApprove={onApproveFactory}
                    />
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : null}
        {session.missing_capabilities.length ? (
          <div className="factory-proposal-gaps" role="status">
            <strong>{zh ? "还需要处理" : "Needs attention"}</strong>
            {session.missing_capabilities.map((item) => (
              <div key={item.reference}>
                <span>{resourceKindLabel(item.kind, locale)}</span>
                <strong>{readableCapabilityReference(item.reference)}</strong>
                <small>{item.reason}</small>
                <details><summary>{zh ? "技术标识" : "Technical reference"}</summary><code>{item.reference}</code></details>
              </div>
            ))}
          </div>
        ) : null}
        <div className={`factory-proposal-readiness is-${session.run_availability}`} role="status">
          <strong>{zh ? "运行准备" : "Run setup"}</strong>
          <span>{runAvailabilityLabel(session.run_availability, locale)}</span>
        </div>
        {(goal || instructions) ? (
          <details className="factory-proposal-details">
            <summary>{zh ? "查看完整需求与 Agent 指令" : "View full request and Agent instructions"}</summary>
            {goal ? <div><strong>{zh ? "完整目标" : "Full goal"}</strong><pre>{goal}</pre></div> : null}
            {instructions ? <div><strong>{zh ? "完整 Agent 指令" : "Full Agent instructions"}</strong><pre>{instructions}</pre></div> : null}
          </details>
        ) : null}
      </section>
    </div>
  );
}

function ProductPlanSummary({
  session,
  locale,
}: {
  session: FactorySession;
  locale: Locale;
}) {
  const zh = locale === "zh";
  const preview = isRecord(session.proposal_preview) ? session.proposal_preview : null;
  const shape = session.product_shape || (isRecord(preview?.product_shape) ? String(preview.product_shape.shape || "") : "");
  const agents = Array.isArray(preview?.agents) ? preview.agents : [];
  const stages = Array.isArray(preview?.stages) ? preview.stages : [];
  const flow = Array.isArray(preview?.flow) ? preview.flow : [];
  const business = Array.isArray(preview?.business_approvals) ? preview.business_approvals : [];
  const tools = Array.isArray(preview?.tool_approvals) ? preview.tool_approvals : [];
  const missing = Array.isArray(preview?.missing_required) ? preview.missing_required : [];
  const state = isRecord(preview?.persistent_state) ? preview.persistent_state : null;
  if (!preview && !shape) return null;
  return (
    <section className="draft-note factory-proposal-summary" aria-label={zh ? "产品形态" : "Product shape"}>
      <span className="ui-eyebrow">{zh ? "产品形态" : "Product shape"}</span>
      <strong>{shape || (zh ? "方案" : "Plan")}</strong>
      <p>
        {zh ? "将创建：" : "Will create: "}
        {preview?.workflow ? (zh ? "1 个 Workflow" : "1 Workflow") : (zh ? "1 个 Agent" : "1 Agent")}
        {agents.length ? (zh ? ` · ${agents.length} 个 Agent` : ` · ${agents.length} Agents`) : ""}
        {state ? (zh ? " · 1 个持久状态" : " · 1 persistent state") : ""}
      </p>
      {stages.length ? (
        <div>
          <strong>{zh ? "任务阶段" : "Task stages"}</strong>
          <ol>
            {stages.map((item, index) => {
              const row = isRecord(item) ? item : {};
              return <li key={String(row.id || index)}>{String(row.summary || row.id || "")}</li>;
            })}
          </ol>
        </div>
      ) : null}
      {flow.length ? (
        <div>
          <strong>{zh ? "执行计划" : "Execution plan"}</strong>
          <ol>
            {flow.map((item, index) => {
              const row = isRecord(item) ? item : {};
              return (
                <li key={String(row.id || index)}>
                  {String(row.kind || "")}{row.why ? ` · ${String(row.why)}` : ""}
                  {row.source ? <small> {zh ? "来源：" : "Source: "}{String(row.source)}</small> : null}
                </li>
              );
            })}
          </ol>
        </div>
      ) : null}
      {business.length || tools.length ? (
        <div>
          <strong>{zh ? "审批" : "Approvals"}</strong>
          {business.length ? <p>{zh ? "业务审批：" : "Business: "}{business.map(String).join(", ")}</p> : null}
          {tools.length ? <p>{zh ? "安全审批：" : "Tool: "}{tools.map(String).join(", ")}</p> : null}
        </div>
      ) : null}
      {state ? <p>{zh ? "持久状态：" : "Persistent state: "}{String(state.entity || "")}</p> : null}
      {missing.length ? (
        <div role="status">
          <strong>{zh ? "缺失能力" : "Missing capabilities"}</strong>
          {missing.map((item, index) => {
            const row = isRecord(item) ? item : {};
            return <p key={String(row.capability || index)}>{String(row.capability || row.reference || "")}</p>;
          })}
        </div>
      ) : null}
      {session.blocked_reason ? <p>{zh ? "已阻止：" : "Blocked: "}{session.blocked_reason}</p> : null}
    </section>
  );
}

export function FactoryAssemblyCanvas({
  locale,
  session,
  busy,
  canGenerate,
  canApply,
  studioHref,
  createdAgentId,
  drafted,
  focusChild,
  phase,
  planSummary,
  live = false,
  stageStartedAt = null,
  onClose,
  onGenerate,
  onApply,
  onReject,
  onRevise,
  onQuarantine,
  onApproveFactory,
  testRun,
  embedded = false,
}: {
  locale: Locale;
  session: FactorySession | null;
  busy: Busy;
  canGenerate: boolean;
  canApply: boolean;
  studioHref: string | null;
  createdAgentId: string | null;
  drafted: boolean;
  focusChild: boolean;
  phase?: WorkbenchPhase;
  planSummary?: Record<string, string>;
  live?: boolean;
  stageStartedAt?: string | null;
  onClose: () => void;
  onGenerate?: () => void;
  onApply: () => void;
  onReject?: () => void;
  onRevise?: () => void;
  onQuarantine?: () => void;
  onApproveFactory?: (capability: string) => void;
  testRun?: ReactNode;
  embedded?: boolean;
}) {
  const text = copy[locale];
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!live || !stageStartedAt) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [live, stageStartedAt]);
  const clock = live && stageStartedAt ? runningClock(stageStartedAt, now, locale) : "";
  const resolvedPhase = phase ?? (
    createdAgentId || session?.state === "completed" ? "completed"
    : session?.state === "missing_capability" ? "missing"
    : session?.state === "review" ? "review"
    : session?.state === "generating" || busy === "generate" ? "compiling"
    : session?.state === "ready" ? "planning"
    : "understanding"
  );
  const compiled = Boolean(session?.blueprint) && (resolvedPhase === "review" || resolvedPhase === "completed" || resolvedPhase === "missing");
  const assembled = resolvedPhase === "compiling" || resolvedPhase === "validating";
  const activeIndex = resolvedPhase === "missing" ? 4 : Math.max(stageOrder.indexOf(resolvedPhase), 0);
  const showApply = resolvedPhase === "review" && !createdAgentId;
  const showReject = showApply && Boolean(onReject);
  const showRevise = showApply && Boolean(onRevise);
  const showStudio = Boolean(studioHref && (createdAgentId || resolvedPhase === "completed"));
  const showGenerate = Boolean(onGenerate);
  const showQuarantine = Boolean(onQuarantine) && Boolean(session?.missing_capabilities.length);
  const showActions = showApply || showReject || showRevise || showStudio || showGenerate || showQuarantine;
  const body = (
      <>
        <ol className="factory-stage-track">
          {stageOrder.map((item, index) => (
            <li key={item} data-active={index <= activeIndex ? "true" : "false"} data-current={live && index === activeIndex ? "true" : "false"}>{stageLabel(item, locale)}</li>
          ))}
        </ol>
        {clock ? <p className="factory-canvas-live" role="status">{stageLabel(resolvedPhase, locale)} · {clock}。{text.waiting}</p> : null}
        {resolvedPhase === "understanding" ? <p className="factory-canvas-empty">{text.understanding}…</p> : null}
        {resolvedPhase === "planning" ? (
          <div className="draft-note">
            <strong>{text.planning}</strong>
            {planSummary?.suggested_name ? <p>{planSummary.suggested_name}</p> : null}
            {planSummary?.input_count ? <p>{planSummary.input_count} inputs · {planSummary.output_count ?? "0"} outputs</p> : null}
          </div>
        ) : null}
        {assembled ? <p className="factory-canvas-assembling">{text.assembling}</p> : null}
        {compiled && session ? <ProductPlanSummary session={session} locale={locale} /> : null}
        {compiled && isLoopProposal(session) ? <CapabilityProposal session={session!} locale={locale} busy={busy} onApproveFactory={onApproveFactory} /> : null}
        {compiled && !isLoopProposal(session) ? <BlueprintFlow session={session} locale={locale} /> : null}
        {compiled && !isLoopProposal(session) ? <ResourcePlan items={session?.resource_plan ?? []} locale={locale} /> : null}
        {compiled && !isLoopProposal(session) && session?.resource_plan.length ? (
          <StatusBadge label={`${text.availability}: ${runAvailabilityLabel(session.run_availability, locale)}`} tone={availabilityTone(session.run_availability)} />
        ) : null}
        {resolvedPhase === "missing" && session?.missing_capabilities.length && !(compiled && isLoopProposal(session)) ? (
          <div className="draft-note">
            <strong>{text.missing}</strong>
            <p>{text.missingHint}</p>
            {session.missing_capabilities.map((item) => {
              const readable = readableCapabilityReference(item.reference);
              return (
                <p key={item.reference}>
                  {readable}: {item.reason}
                  {readable !== item.reference ? <> <code>{item.reference}</code></> : null}
                </p>
              );
            })}
            {drafted ? <p>{text.quarantined}</p> : null}
          </div>
        ) : null}
        {compiled && session?.diagnostics.length ? (
          <Alert type="warning" title={text.diagnostics}>
            {session.diagnostics.map((item) => <p key={item}>{item}</p>)}
          </Alert>
        ) : null}
        {showActions ? <div className={`factory-canvas-actions${showApply || showStudio ? " is-priority" : ""}`}>
          {showGenerate ? <Button variant="primary" disabled={!canGenerate || Boolean(busy)} onClick={onGenerate}>
            {busy === "generate" ? text.generatingBtn : text.generate}
          </Button> : null}
          {showApply ? <Button variant="primary" disabled={!canApply || Boolean(busy)} onClick={onApply}>
            {busy === "apply" ? text.applying : text.apply}
          </Button> : null}
          {showRevise ? <Button disabled={!canApply || Boolean(busy)} onClick={onRevise}>{text.revise}</Button> : null}
          {showReject ? <Button disabled={!canApply || Boolean(busy)} onClick={onReject}>{text.reject}</Button> : null}
          {showQuarantine ? <Button disabled={!session?.missing_capabilities.length || Boolean(busy)} onClick={onQuarantine}>
            {busy === "draft" ? text.quarantining : text.quarantine}
          </Button> : null}
          {showStudio ? <LinkButton variant="primary" href={studioHref!}>{text.studio}</LinkButton> : null}
        </div> : null}
        {createdAgentId ? (
          <div className="draft-note">
            <strong>{text.completed}</strong>
            <p>{text.created}</p>
            <p>{text.noExecute}</p>
          </div>
        ) : null}
        {focusChild && canApply ? <p className="factory-canvas-kicker">{text.child}</p> : null}
        {!embedded && createdAgentId ? testRun : null}
        {!createdAgentId ? <p className="factory-canvas-kicker">{text.noExecute}</p> : null}
      </>
  );
  if (embedded) {
    return (
      <div className="factory-assembly-embedded">
        <h3>{stageLabel(resolvedPhase, locale)}</h3>
        {body}
      </div>
    );
  }
  return (
    <aside className="agent-convo-canvas factory-assembly-canvas" aria-label={text.canvas}>
      <header className="agent-convo-canvas-head">
        <div>
          <span className="ui-eyebrow">Workbench</span>
          <h3>{stageLabel(resolvedPhase, locale)}</h3>
        </div>
        <div className="factory-canvas-head-actions">
          {session ? <StatusBadge label={session.state} tone={session.state === "completed" ? "good" : session.state === "missing_capability" ? "bad" : "warn"} /> : null}
          <IconButton icon={X} label={locale === "zh" ? "关闭工作台" : "Close workbench"} onClick={onClose} />
        </div>
      </header>
      <div className="agent-convo-canvas-body">{body}</div>
    </aside>
  );
}

export function FactoryCanvasCard({
  title,
  locale,
  onOpen,
}: {
  title: string;
  locale: Locale;
  onOpen: () => void;
}) {
  return (
    <button className="agent-convo-canvas-card" type="button" onClick={onOpen} aria-label={locale === "zh" ? "在画布中查看" : "Open in canvas"}>
      <span className="agent-convo-canvas-card-icon"><LayoutPanelTop size={16} aria-hidden="true" /></span>
      <span>
        <strong>{title}</strong>
        <small>{locale === "zh" ? "在画布中查看" : "Open in canvas"}</small>
      </span>
    </button>
  );
}
