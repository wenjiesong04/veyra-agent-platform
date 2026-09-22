import type { ReactNode } from "react";
import { LayoutPanelTop, X } from "lucide-react";
import type { FactoryResourcePlanItem, FactorySession } from "@veyra/api-contracts";
import { Alert, Button, IconButton, LinkButton, StatusBadge } from "@veyra/ui";
import { blueprintGraph, blueprintPresentation } from "./factory-blueprint";
import type { WorkbenchPhase } from "../builder/workbench-phase";
import { centerNoteAboveGraph, estimatedNodeSize, layoutExecutionGraph } from "../studio/graph-layout";

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
    missing: "缺少能力",
    completed: "Draft 已创建",
    abandoned: "会话已放弃",
    plan: "将引用这些已登记资源",
    emptyPlan: "确认创建意图后，这里会显示正在构建的对象。",
    assembling: "正在根据语义计划编译 Agent 结构。",
    missingHint: "缺失能力会写入隔离 Catalog。它们不可执行，Factory 也不能再选用，直到人工审核并登记。",
    quarantine: "写入隔离草稿",
    quarantining: "正在写入…",
    quarantined: "已写入隔离 Catalog，不可执行、不可被 Factory 选用。",
    generate: "生成 Blueprint",
    generatingBtn: "正在生成…",
    apply: "确认创建 Draft",
    reject: "拒绝",
    applying: "正在创建…",
    studio: "打开 Studio",
    created: "Draft 已创建。请在 Studio 检查，再用本机 Runtime 试跑直到验证通过。",
    noExecute: "Factory 不会执行草稿，也不会自动运行生成的工具代码。",
    child: "将创建为当前 Agent 的子版本",
    diagnostics: "修复诊断",
    availability: "运行可用性",
    reviewReady: "方案待确认",
  },
  en: {
    canvas: "Workbench",
    understanding: "Understanding the request",
    planning: "Generating the plan",
    compiling: "Assembling the Agent",
    validating: "Validating structure",
    review: "Review proposal",
    missing: "Missing capabilities",
    completed: "Draft created",
    abandoned: "Session abandoned",
    plan: "These registered catalog resources will be used",
    emptyPlan: "Once create intent is known, the object being built appears here.",
    assembling: "Compiling the Agent structure from the semantic plan.",
    missingHint: "Missing capabilities become quarantined catalog drafts. They are not executable and Factory cannot select them until they are reviewed and registered.",
    quarantine: "Create quarantined drafts",
    quarantining: "Writing drafts…",
    quarantined: "Wrote quarantined catalog drafts. They are not executable and Factory cannot select them.",
    generate: "Generate Blueprint",
    generatingBtn: "Generating…",
    apply: "Create Draft",
    reject: "Reject",
    applying: "Creating…",
    studio: "Open Studio",
    created: "Draft created. Review it in Studio, then test-run it with the local Runtime until it verifies.",
    noExecute: "Factory never executes drafts and does not auto-run generated tool code.",
    child: "Will be created as a child of the current Agent",
    diagnostics: "Repair diagnostics",
    availability: "Run availability",
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

function BlueprintFlow({
  session,
}: {
  session: FactorySession | null;
}) {
  const graph = blueprintGraph(session?.blueprint);
  if (!graph.nodes.length) return null;
  const presentation = blueprintPresentation(session?.blueprint);
  const layoutNodes = graph.nodes.map((node) => ({ id: node.id, component_type: node.component_type }));
  const positions = layoutExecutionGraph(layoutNodes, graph.transitions);
  const placed = graph.nodes.map((node) => ({
    ...node,
    ...positions[node.id],
    ...estimatedNodeSize(node.component_type),
  }));
  const graphRight = Math.max(...placed.map((node) => node.x + node.width));
  const graphBottom = Math.max(...placed.map((node) => node.y + node.height));
  const note = presentation.note;
  const noteHeight = note ? 154 : 0;
  const margin = 24;
  const noteGap = 48;
  const width = Math.max(graphRight, note?.width ?? 0) + margin * 2;
  const graphTop = margin + (note ? noteHeight + noteGap : 0);
  const height = graphBottom + graphTop + margin;
  const notePosition = note ? centerNoteAboveGraph(layoutNodes, positions, note.width, noteHeight, noteGap) : null;
  const center = (id: string) => {
    const node = placed.find((item) => item.id === id);
    if (!node) return null;
    return { x: margin + node.x + node.width / 2, y: graphTop + node.y + node.height / 2 };
  };
  return (
    <div className="agent-convo-flow-block">
      <div className="agent-convo-flow" style={{ aspectRatio: `${width} / ${height}` }}>
        <svg className="agent-convo-flow-edges" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet" aria-hidden="true">
          {graph.transitions.map((edge) => {
            const from = center(edge.from);
            const to = center(edge.to);
            if (!from || !to) return null;
            const source = placed.find((node) => node.id === edge.from)!;
            const target = placed.find((node) => node.id === edge.to)!;
            const startX = margin + source.x + source.width;
            const endX = margin + target.x;
            const curveX = (startX + endX) / 2;
            return (
              <g key={`${edge.from}:${edge.port}:${edge.to}`}>
                <path d={`M ${startX} ${from.y} C ${curveX} ${from.y}, ${curveX} ${to.y}, ${endX} ${to.y}`} />
                {edge.port !== "next" ? <text x={curveX} y={(from.y + to.y) / 2 - 7}>{edge.port}</text> : null}
              </g>
            );
          })}
        </svg>
        {note && notePosition ? (
          <div
            className={`agent-convo-flow-note color-${note.color}`}
            style={{
              left: `${((notePosition.x + margin) / width) * 100}%`,
              top: `${margin / height * 100}%`,
              width: `${(note.width / width) * 100}%`,
              height: `${(noteHeight / height) * 100}%`,
            }}
            >
            <strong>{note.text}</strong>
          </div>
        ) : null}
        {placed.map((node) => (
          <div
            key={node.id}
            className="agent-convo-flow-node"
            data-state="completed"
            style={{
              left: `${((margin + node.x) / width) * 100}%`,
              top: `${((graphTop + node.y) / height) * 100}%`,
              width: `${(node.width / width) * 100}%`,
              height: `${(node.height / height) * 100}%`,
            }}
          >
            <strong>{presentation.labels[node.id] ?? node.component_type}</strong>
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
  phase,
  planSummary,
  onClose,
  onGenerate,
  onApply,
  onReject,
  onQuarantine,
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
  onClose: () => void;
  onGenerate?: () => void;
  onApply: () => void;
  onReject?: () => void;
  onQuarantine?: () => void;
  testRun?: ReactNode;
  embedded?: boolean;
}) {
  const text = copy[locale];
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
  const showStudio = Boolean(studioHref);
  const showGenerate = Boolean(onGenerate);
  const showQuarantine = Boolean(onQuarantine) && Boolean(session?.missing_capabilities.length);
  const showActions = showApply || showReject || showStudio || showGenerate || showQuarantine;
  const body = (
      <>
        <ol className="factory-stage-track" aria-hidden="true">
          {stageOrder.map((item, index) => (
            <li key={item} data-active={index <= activeIndex ? "true" : "false"}>{stageLabel(item, locale)}</li>
          ))}
        </ol>
        {resolvedPhase === "understanding" ? <p className="factory-canvas-empty">{text.understanding}…</p> : null}
        {resolvedPhase === "planning" ? (
          <div className="draft-note">
            <strong>{text.planning}</strong>
            {planSummary?.suggested_name ? <p>{planSummary.suggested_name}</p> : null}
            {planSummary?.input_count ? <p>{planSummary.input_count} inputs · {planSummary.output_count ?? "0"} outputs</p> : null}
          </div>
        ) : null}
        {assembled ? <p className="factory-canvas-assembling">{text.assembling}</p> : null}
        {compiled ? <BlueprintFlow session={session} /> : null}
        {compiled ? <ResourcePlan items={session?.resource_plan ?? []} locale={locale} /> : null}
        {compiled && session?.resource_plan.length ? (
          <StatusBadge label={`${text.availability}: ${session.run_availability}`} tone={availabilityTone(session.run_availability)} />
        ) : null}
        {resolvedPhase === "missing" && session?.missing_capabilities.length ? (
          <div className="draft-note">
            <strong>{text.missing}</strong>
            <p>{text.missingHint}</p>
            {session.missing_capabilities.map((item) => (
              <p key={item.reference}>{item.reference}: {item.reason}</p>
            ))}
            {drafted ? <p>{text.quarantined}</p> : null}
          </div>
        ) : null}
        {compiled && session?.diagnostics.length ? (
          <Alert type="warning" title={text.diagnostics}>
            {session.diagnostics.map((item) => <p key={item}>{item}</p>)}
          </Alert>
        ) : null}
        {createdAgentId ? (
          <div className="draft-note">
            <strong>{text.completed}</strong>
            <p>{text.created}</p>
            <p>{text.noExecute}</p>
          </div>
        ) : null}
        {showActions ? <div className="factory-canvas-actions">
          {showGenerate ? <Button variant="primary" disabled={!canGenerate || Boolean(busy)} onClick={onGenerate}>
            {busy === "generate" ? text.generatingBtn : text.generate}
          </Button> : null}
          {showApply ? <Button disabled={!canApply || Boolean(busy)} onClick={onApply}>
            {busy === "apply" ? text.applying : text.apply}
          </Button> : null}
          {showReject ? <Button disabled={!canApply || Boolean(busy)} onClick={onReject}>{text.reject}</Button> : null}
          {showQuarantine ? <Button disabled={!session?.missing_capabilities.length || Boolean(busy)} onClick={onQuarantine}>
            {busy === "draft" ? text.quarantining : text.quarantine}
          </Button> : null}
          {showStudio ? <LinkButton href={studioHref!}>{text.studio}</LinkButton> : null}
        </div> : null}
        {focusChild && canApply ? <p className="factory-canvas-kicker">{text.child}</p> : null}
        {!embedded && createdAgentId ? testRun : null}
        <p className="factory-canvas-kicker">{text.noExecute}</p>
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
