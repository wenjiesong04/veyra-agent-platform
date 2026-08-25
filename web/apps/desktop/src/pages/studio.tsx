import { Check, CircleHelp, Code2, Eye, GitBranch, LayoutPanelTop, Play, Save, ShieldCheck, SlidersHorizontal, SquareStack } from "lucide-react";
import { projectRoutePaths } from "@veyra/api-contracts";
import { useState } from "react";
import { Button, LinkButton, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";
import { NotFoundPage } from "./not-found";
import { agents, projects } from "./projects";

type StudioView = "canvas" | "form" | "source";

const nodes = [
  { id: "start", label: "Start", detail: "Requirement received", tone: "good" as const },
  { id: "collect", label: "Collect evidence", detail: "Project scope", tone: "good" as const },
  { id: "review", label: "Prepare brief", detail: "Structured output", tone: "neutral" as const },
  { id: "approve", label: "Approval gate", detail: "Before external write", tone: "warn" as const },
  { id: "verify", label: "Verify result", detail: "Independent check", tone: "neutral" as const },
];

const studioCopy = {
  zh: {
    missingProject: "返回项目", eyebrow: "Agent 定义", description: "表单、Canvas 和源码是同一份规范化定义的三种视图。", saved: "版本已保存", draft: "草稿变更", save: "保存版本", run: "运行", studioView: "Studio 视图", canvas: "Canvas", form: "表单", source: "源码", behaviorHash: "行为哈希", library: "组件库", components: "组件", condition: "条件", verifier: "验证器", approval: "审批", dropNode: "拖入节点", inspectable: "每条连线都可以在源码中检查。", designCanvas: "设计 Canvas", stable: "往返稳定", inspector: "检查器", approvalGate: "审批门", needsDecision: "需要决策", node: "节点 04 / HumanApproval", prompt: "提示词", promptValue: "发布这份评审简报吗？", permissions: "权限", resume: "恢复", checkpoint: "检查点可用", runControls: "查看运行控制",
  },
  en: {
    missingProject: "Back to Project", eyebrow: "Agent definition", description: "Form, Canvas, and Source are three views of one normalized definition.", saved: "Saved version", draft: "Draft changes", save: "Save version", run: "Run", studioView: "Studio view", canvas: "Canvas", form: "Form", source: "Source", behaviorHash: "behavior hash", library: "Library", components: "Components", condition: "Condition", verifier: "Verifier", approval: "Approval", dropNode: "Drop a node", inspectable: "Every edge remains inspectable in Source.", designCanvas: "Design canvas", stable: "Round-trip stable", inspector: "Inspector", approvalGate: "Approval gate", needsDecision: "Needs decision", node: "Node 04 / HumanApproval", prompt: "Prompt", promptValue: "Publish this review brief?", permissions: "Permissions", resume: "Resume", checkpoint: "Checkpoint available", runControls: "View run controls",
  },
} as const;

const localizedNodes = {
  zh: [
    { id: "start", label: "开始", detail: "已收到需求", tone: "good" as const },
    { id: "collect", label: "收集证据", detail: "项目范围", tone: "good" as const },
    { id: "review", label: "准备简报", detail: "结构化输出", tone: "neutral" as const },
    { id: "approve", label: "审批门", detail: "外部写入前", tone: "warn" as const },
    { id: "verify", label: "验证结果", detail: "独立检查", tone: "neutral" as const },
  ],
  en: nodes,
} as const;

export function StudioPage({ projectId, agentId }: { projectId: string; agentId: string }) {
  const { locale } = useLocale();
  const [view, setView] = useState<StudioView>("canvas");
  const [saved, setSaved] = useState(false);
  const project = projects.find((item) => item.id === projectId);
  const agent = agents.find((item) => item.id === agentId && item.projectId === projectId);
  const copy = studioCopy[locale];
  const canvasNodes = localizedNodes[locale];
  if (!project || !agent) return <NotFoundPage backHref={project ? projectRoutePaths.project(project.id) : "#/projects"} backLabel={copy.missingProject} />;
  const title = agent.name;

  return (
    <div className="page-stack">
      <div className="page-intro studio-intro">
        <div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{title}</h2><p>{copy.description}</p></div>
        <div className="intro-actions"><StatusBadge label={saved ? copy.saved : copy.draft} tone={saved ? "good" : "warn"} /><Button icon={Save} variant="primary" onClick={() => setSaved(true)}>{copy.save}</Button><LinkButton href={projectRoutePaths.agentRun(projectId, agentId)} icon={Play}>{copy.run}</LinkButton></div>
      </div>

      <div className="studio-toolbar"><div className="view-switcher" role="tablist" aria-label={copy.studioView}>{(["canvas", "form", "source"] as StudioView[]).map((item) => <button className={view === item ? "active" : ""} key={item} role="tab" aria-selected={view === item} onClick={() => setView(item)}>{item === "canvas" ? <LayoutPanelTop size={15} /> : item === "form" ? <SlidersHorizontal size={15} /> : <Code2 size={15} />}{copy[item]}</button>)}</div><span className="toolbar-meta"><GitBranch size={14} /> {copy.behaviorHash} <strong>8f2a…c91d</strong></span></div>

      {view === "canvas" ? <div className="studio-layout"><Panel className="component-rail"><SectionHeading eyebrow={copy.library} title={copy.components} /><div className="component-list"><div><SquareStack size={15} /><span>Start</span></div><div><GitBranch size={15} /><span>{copy.condition}</span></div><div><ShieldCheck size={15} /><span>{copy.verifier}</span></div><div><CircleHelp size={15} /><span>{copy.approval}</span></div></div><div className="rail-note"><strong>{copy.dropNode}</strong><span>{copy.inspectable}</span></div></Panel><Panel className="canvas-panel"><div className="canvas-grid"><div className="canvas-caption"><span>{copy.designCanvas}</span><Tag tone="good">{copy.stable}</Tag></div><div className="node-stack">{canvasNodes.map((node, index) => <div className="node-wrap" key={node.id}><div className={`canvas-node ${node.tone}`}><span className="node-number">0{index + 1}</span><span><strong>{node.label}</strong><small>{node.detail}</small></span><Eye size={15} /></div>{index < canvasNodes.length - 1 ? <span className="node-line" aria-hidden="true" /> : null}</div>)}</div></div></Panel><Panel className="inspector-panel"><SectionHeading eyebrow={copy.inspector} title={copy.approvalGate} /><div className="inspector-status"><StatusBadge label={copy.needsDecision} tone="warn" /><span>{copy.node}</span></div><dl className="detail-list"><div><dt>{copy.prompt}</dt><dd>{copy.promptValue}</dd></div><div><dt>{copy.permissions}</dt><dd><Tag>write / guarded</Tag></dd></div><div><dt>{copy.resume}</dt><dd>{copy.checkpoint}</dd></div></dl><LinkButton href="#/monitor" icon={SlidersHorizontal} size="sm">{copy.runControls}</LinkButton></Panel></div> : null}
      {view === "form" ? <FormView /> : null}
      {view === "source" ? <SourceView /> : null}
    </div>
  );
}

function FormView() {
  const { locale } = useLocale();
  const copy = locale === "zh" ? {
    eyebrow: "表单视图", title: "定义详情", detail: "简单字段会编译成 Canvas 中展示的同一张图。", name: "名称", versionNote: "版本说明", goal: "目标", runtime: "运行配置", guarded: "受控本机", reviewOnly: "仅评审", verification: "验证", required: "必需", optional: "可选", nameValue: "评审 Agent", noteValue: "在审批前收集证据。", goalValue: "准备一份带来源证据、并经过独立检查的评审简报。",
  } : {
    eyebrow: "Form view", title: "Definition details", detail: "Simple fields compile to the same graph shown on Canvas.", name: "Name", versionNote: "Version note", goal: "Goal", runtime: "Runtime profile", guarded: "Guarded local", reviewOnly: "Review only", verification: "Verification", required: "Required", optional: "Optional", nameValue: "Review Agent", noteValue: "Collect evidence before approval.", goalValue: "Prepare a review brief with linked evidence and an independently checked result.",
  };
  return <Panel className="form-view"><SectionHeading eyebrow={copy.eyebrow} title={copy.title} detail={copy.detail} /><div className="form-grid"><label><span>{copy.name}</span><input defaultValue={copy.nameValue} /></label><label><span>{copy.versionNote}</span><input defaultValue={copy.noteValue} /></label><label className="wide"><span>{copy.goal}</span><textarea defaultValue={copy.goalValue} rows={5} /></label><label><span>{copy.runtime}</span><select defaultValue="guarded-local"><option value="guarded-local">{copy.guarded}</option><option value="review-only">{copy.reviewOnly}</option></select></label><label><span>{copy.verification}</span><select defaultValue="required"><option value="required">{copy.required}</option><option value="optional">{copy.optional}</option></select></label></div></Panel>;
}

function SourceView() {
  const { locale } = useLocale();
  const copy = locale === "zh" ? { eyebrow: "源码视图", canonical: "规范源", footer: "上次验证后没有语义变更。" } : { eyebrow: "Source view", canonical: "Canonical", footer: "No semantic changes since last validation." };
  return <Panel className="source-view"><SectionHeading eyebrow={copy.eyebrow} title="review-agent.vagent.yaml" action={<Tag tone="good">{copy.canonical}</Tag>} /><pre><code>{`agentspec_version: "26.1"
id: review-agent
name: Review Agent

nodes:
  - id: collect
    component_type: Tool
  - id: approve
    component_type: HumanApproval
  - id: verify
    component_type: Verifier

extensions:
  veyra:
    verification:
      required: true`}</code></pre><div className="source-footer"><Check size={15} /> {copy.footer}</div></Panel>;
}
