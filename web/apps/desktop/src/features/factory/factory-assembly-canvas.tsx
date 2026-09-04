import type { ReactNode } from "react";
import { LayoutPanelTop, X } from "lucide-react";
import type { FactoryResourcePlanItem, FactorySession } from "@veyra/api-contracts";
import { Button, IconButton, LinkButton, StatusBadge } from "@veyra/ui";
import { blueprintGraph } from "./factory-blueprint";

type Locale = "zh" | "en";
type Busy = "message" | "generate" | "apply" | "draft" | null;

const NODE_W = 148;
const NODE_H = 58;

const copy = {
  zh: {
    canvas: "组装画布",
    collecting: "正在了解需求",
    ready: "可以组装蓝图",
    generating: "正在组装蓝图",
    review: "资源计划",
    missing: "缺少能力",
    completed: "Draft 已创建",
    abandoned: "会话已放弃",
    plan: "将引用这些已登记资源",
    emptyPlan: "发送需求后，这里会显示资源计划和蓝图。",
    assembling: "Veyra Agent 正在按资源库组装 Blueprint，不会执行草稿。",
    missingHint: "缺失能力会写入隔离 Catalog。它们不可执行，Factory 也不能再选用，直到人工审核并登记。",
    quarantine: "写入隔离草稿",
    quarantining: "正在写入…",
    quarantined: "已写入隔离 Catalog，不可执行、不可被 Factory 选用。",
    generate: "生成 Blueprint",
    generatingBtn: "正在生成…",
    apply: "确认创建 Draft",
    applying: "正在创建…",
    studio: "打开 Studio",
    created: "Draft 已创建。请在 Studio 检查，再用本机 Runtime 试跑直到验证通过。",
    noExecute: "Factory 不会执行草稿，也不会自动运行生成的工具代码。",
    child: "将创建为当前 Agent 的子版本",
    diagnostics: "修复诊断",
    availability: "运行可用性",
  },
  en: {
    canvas: "Assembly canvas",
    collecting: "Collecting requirements",
    ready: "Ready to assemble",
    generating: "Assembling blueprint",
    review: "Resource plan",
    missing: "Missing capabilities",
    completed: "Draft created",
    abandoned: "Session abandoned",
    plan: "These registered catalog resources will be used",
    emptyPlan: "After you describe the Agent, the resource plan and blueprint appear here.",
    assembling: "Veyra Agent is assembling a Blueprint from the catalog. It will not execute the Draft.",
    missingHint: "Missing capabilities become quarantined catalog drafts. They are not executable and Factory cannot select them until they are reviewed and registered.",
    quarantine: "Create quarantined drafts",
    quarantining: "Writing drafts…",
    quarantined: "Wrote quarantined catalog drafts. They are not executable and Factory cannot select them.",
    generate: "Generate Blueprint",
    generatingBtn: "Generating…",
    apply: "Create Draft",
    applying: "Creating…",
    studio: "Open Studio",
    created: "Draft created. Review it in Studio, then test-run it with the local Runtime until it verifies.",
    noExecute: "Factory never executes drafts and does not auto-run generated tool code.",
    child: "Will be created as a child of the current Agent",
    diagnostics: "Repair diagnostics",
    availability: "Run availability",
  },
} as const;

const stageOrder: FactorySession["state"][] = ["collecting", "ready", "generating", "review", "completed"];

function stageLabel(state: FactorySession["state"], locale: Locale): string {
  const text = copy[locale];
  if (state === "missing_capability") return text.missing;
  if (state === "abandoned") return text.abandoned;
  return text[state];
}

function availabilityTone(value: FactorySession["run_availability"]): "good" | "warn" | "bad" | "neutral" {
  return value === "ready" ? "good" : value === "unavailable" ? "bad" : "warn";
}

function BlueprintFlow({
  session,
  assembling,
}: {
  session: FactorySession | null;
  assembling: boolean;
}) {
  const graph = blueprintGraph(session?.blueprint);
  const nodes = graph.nodes.length
    ? graph.nodes
    : assembling
      ? [
          { id: "start", component_type: "Start" },
          { id: "work", component_type: "Agent" },
          { id: "output", component_type: "Output" },
        ]
      : [];
  if (!nodes.length) return null;
  const placed = nodes.map((node, index) => ({
    ...node,
    x: 24 + (index % 3) * 180,
    y: 24 + Math.floor(index / 3) * 88,
  }));
  const width = Math.max(...placed.map((node) => node.x)) + NODE_W + 24;
  const height = Math.max(...placed.map((node) => node.y)) + NODE_H + 24;
  const center = (id: string) => {
    const node = placed.find((item) => item.id === id);
    if (!node) return null;
    return { x: node.x + NODE_W / 2, y: node.y + NODE_H / 2 };
  };
  const edges = graph.transitions.length
    ? graph.transitions
    : assembling
      ? [
          { from: "start", port: "next", to: "work" },
          { from: "work", port: "next", to: "output" },
        ]
      : [];
  return (
    <div className="agent-convo-flow-block">
      <div className={`agent-convo-flow${assembling ? " is-assembling" : ""}`} style={{ width, height }}>
        <svg className="agent-convo-flow-edges" viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
          {edges.map((edge) => {
            const from = center(edge.from);
            const to = center(edge.to);
            if (!from || !to) return null;
            return <line key={`${edge.from}:${edge.port}:${edge.to}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y} />;
          })}
        </svg>
        {placed.map((node) => (
          <div
            key={node.id}
            className="agent-convo-flow-node"
            data-state={assembling ? "running" : "pending"}
            style={{ left: node.x, top: node.y, width: NODE_W }}
          >
            <strong>{node.component_type}</strong>
            <small>{node.id}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

function ResourcePlan({ items, locale }: { items: FactoryResourcePlanItem[]; locale: Locale }) {
  if (!items.length) return null;
  return (
    <div className="factory-canvas-plan">
      <p className="factory-canvas-kicker">{copy[locale].plan}</p>
      {items.map((item) => (
        <div className="draft-node" key={item.reference}>
          <span>{item.kind}</span>
          <div>
            <strong>{item.reference}</strong>
            <small>{item.availability} · {item.runtime_status}</small>
          </div>
        </div>
      ))}
    </div>
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
  onClose,
  onGenerate,
  onApply,
  onQuarantine,
  testRun,
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
  onClose: () => void;
  onGenerate: () => void;
  onApply: () => void;
  onQuarantine: () => void;
  testRun?: ReactNode;
}) {
  const text = copy[locale];
  const assembling = busy === "generate" || session?.state === "generating";
  const state = assembling ? "generating" : (session?.state ?? "collecting");
  const activeIndex = state === "missing_capability" ? 3 : Math.max(stageOrder.indexOf(state), 0);
  return (
    <aside className="agent-convo-canvas factory-assembly-canvas" aria-label={text.canvas}>
      <header className="agent-convo-canvas-head">
        <div>
          <span className="ui-eyebrow">Canvas</span>
          <h3>{stageLabel(state, locale)}</h3>
        </div>
        <div className="factory-canvas-head-actions">
          {session ? <StatusBadge label={session.state} tone={session.state === "completed" ? "good" : session.state === "missing_capability" ? "bad" : "warn"} /> : null}
          <IconButton icon={X} label={locale === "zh" ? "关闭画布" : "Close canvas"} onClick={onClose} />
        </div>
      </header>
      <div className="agent-convo-canvas-body">
        <ol className="factory-stage-track" aria-hidden="true">
          {stageOrder.map((item, index) => (
            <li key={item} data-active={index <= activeIndex ? "true" : "false"}>{stageLabel(item, locale)}</li>
          ))}
        </ol>
        {!session ? <p className="factory-canvas-empty">{text.emptyPlan}</p> : null}
        {assembling ? <p className="factory-canvas-assembling">{text.assembling}</p> : null}
        <BlueprintFlow session={session} assembling={assembling} />
        <ResourcePlan items={session?.resource_plan ?? []} locale={locale} />
        {session?.resource_plan.length ? (
          <StatusBadge label={`${text.availability}: ${session.run_availability}`} tone={availabilityTone(session.run_availability)} />
        ) : null}
        {session?.missing_capabilities.length ? (
          <div className="draft-note">
            <strong>{text.missing}</strong>
            <p>{text.missingHint}</p>
            {session.missing_capabilities.map((item) => (
              <p key={item.reference}>{item.reference}: {item.reason}</p>
            ))}
            {drafted ? <p>{text.quarantined}</p> : null}
          </div>
        ) : null}
        {session?.diagnostics.length ? (
          <div className="draft-note">
            <strong>{text.diagnostics}</strong>
            {session.diagnostics.map((item) => <p key={item}>{item}</p>)}
          </div>
        ) : null}
        {createdAgentId ? (
          <div className="draft-note">
            <strong>{text.completed}</strong>
            <p>{text.created}</p>
            <p>{text.noExecute}</p>
          </div>
        ) : null}
        <div className="factory-canvas-actions">
          <Button variant="primary" disabled={!canGenerate || Boolean(busy)} onClick={onGenerate}>
            {busy === "generate" ? text.generatingBtn : text.generate}
          </Button>
          <Button disabled={!canApply || Boolean(busy)} onClick={onApply}>
            {busy === "apply" ? text.applying : text.apply}
          </Button>
          <Button disabled={!session?.missing_capabilities.length || Boolean(busy)} onClick={onQuarantine}>
            {busy === "draft" ? text.quarantining : text.quarantine}
          </Button>
          {studioHref ? <LinkButton href={studioHref}>{text.studio}</LinkButton> : null}
        </div>
        {focusChild && canApply ? <p className="factory-canvas-kicker">{text.child}</p> : null}
        {createdAgentId ? testRun : null}
        <p className="factory-canvas-kicker">{text.noExecute}</p>
      </div>
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
