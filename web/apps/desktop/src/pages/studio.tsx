import { Check, CircleHelp, Code2, Eye, GitBranch, LayoutPanelTop, Play, Save, ShieldCheck, SlidersHorizontal, SquareStack } from "lucide-react";
import { useState } from "react";
import { Button, LinkButton, Panel, SectionHeading, StatusBadge, Tag } from "@veyra/ui";

type StudioView = "canvas" | "form" | "source";

const nodes = [
  { id: "start", label: "Start", detail: "Requirement received", tone: "good" as const },
  { id: "collect", label: "Collect evidence", detail: "Project scope", tone: "good" as const },
  { id: "review", label: "Prepare brief", detail: "Structured output", tone: "neutral" as const },
  { id: "approve", label: "Approval gate", detail: "Before external write", tone: "warn" as const },
  { id: "verify", label: "Verify result", detail: "Independent check", tone: "neutral" as const },
];

export function StudioPage({ agentId }: { agentId?: string }) {
  const [view, setView] = useState<StudioView>("canvas");
  const [saved, setSaved] = useState(false);
  const title = agentId ? "Review Agent" : "Untitled Agent";

  return (
    <div className="page-stack">
      <div className="page-intro studio-intro">
        <div><span className="ui-eyebrow">Agent definition</span><h2>{title}</h2><p>Form, Canvas, and Source are three views of one normalized definition.</p></div>
        <div className="intro-actions"><StatusBadge label={saved ? "Saved version" : "Draft changes"} tone={saved ? "good" : "warn"} /><Button icon={Save} variant="primary" onClick={() => setSaved(true)}>Save version</Button><Button icon={Play}>Run</Button></div>
      </div>

      <div className="studio-toolbar"><div className="view-switcher" role="tablist" aria-label="Studio view">{(["canvas", "form", "source"] as StudioView[]).map((item) => <button className={view === item ? "active" : ""} key={item} role="tab" aria-selected={view === item} onClick={() => setView(item)}>{item === "canvas" ? <LayoutPanelTop size={15} /> : item === "form" ? <SlidersHorizontal size={15} /> : <Code2 size={15} />}{item[0].toUpperCase() + item.slice(1)}</button>)}</div><span className="toolbar-meta"><GitBranch size={14} /> behavior hash <strong>8f2a…c91d</strong></span></div>

      {view === "canvas" ? <div className="studio-layout"><Panel className="component-rail"><SectionHeading eyebrow="Library" title="Components" /><div className="component-list"><div><SquareStack size={15} /><span>Start</span></div><div><GitBranch size={15} /><span>Condition</span></div><div><ShieldCheck size={15} /><span>Verifier</span></div><div><CircleHelp size={15} /><span>Approval</span></div></div><div className="rail-note"><strong>Drop a node</strong><span>Every edge remains inspectable in Source.</span></div></Panel><Panel className="canvas-panel"><div className="canvas-grid"><div className="canvas-caption"><span>Design canvas</span><Tag tone="good">Round-trip stable</Tag></div><div className="node-stack">{nodes.map((node, index) => <div className="node-wrap" key={node.id}><div className={`canvas-node ${node.tone}`}><span className="node-number">0{index + 1}</span><span><strong>{node.label}</strong><small>{node.detail}</small></span><Eye size={15} /></div>{index < nodes.length - 1 ? <span className="node-line" aria-hidden="true" /> : null}</div>)}</div></div></Panel><Panel className="inspector-panel"><SectionHeading eyebrow="Inspector" title="Approval gate" /><div className="inspector-status"><StatusBadge label="Needs decision" tone="warn" /><span>Node 04 / HumanApproval</span></div><dl className="detail-list"><div><dt>Prompt</dt><dd>Publish this review brief?</dd></div><div><dt>Permissions</dt><dd><Tag>write / guarded</Tag></dd></div><div><dt>Resume</dt><dd>Checkpoint available</dd></div></dl><LinkButton href="#/monitor" icon={SlidersHorizontal} size="sm">View run controls</LinkButton></Panel></div> : null}
      {view === "form" ? <FormView /> : null}
      {view === "source" ? <SourceView /> : null}
    </div>
  );
}

function FormView() {
  return <Panel className="form-view"><SectionHeading eyebrow="Form view" title="Definition details" detail="Simple fields compile to the same graph shown on Canvas." /><div className="form-grid"><label><span>Name</span><input defaultValue="Review Agent" /></label><label><span>Version note</span><input defaultValue="Collect evidence before approval." /></label><label className="wide"><span>Goal</span><textarea defaultValue="Prepare a review brief with linked evidence and an independently checked result." rows={5} /></label><label><span>Runtime profile</span><select defaultValue="guarded-local"><option value="guarded-local">Guarded local</option><option value="review-only">Review only</option></select></label><label><span>Verification</span><select defaultValue="required"><option value="required">Required</option><option value="optional">Optional</option></select></label></div></Panel>;
}

function SourceView() {
  return <Panel className="source-view"><SectionHeading eyebrow="Source view" title="review-agent.vagent.yaml" action={<Tag tone="good">Canonical</Tag>} /><pre><code>{`agentspec_version: "26.1"
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
      required: true`}</code></pre><div className="source-footer"><Check size={15} /> No semantic changes since last validation.</div></Panel>;
}
