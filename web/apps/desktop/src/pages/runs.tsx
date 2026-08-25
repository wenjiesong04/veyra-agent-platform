import { ArrowUpRight, Clock3, FileCheck2, Play, RotateCcw } from "lucide-react";
import type { RunSummary } from "@veyra/api-contracts";
import { Button, LinkButton, Panel, SectionHeading, StatusBadge, Tag } from "@veyra/ui";

const runs: RunSummary[] = [
  { id: "run-1042", agentName: "Release Check", projectName: "Release Room", state: "waiting", startedAt: "Aug 25, 14:08", duration: "08:42", eventCount: 28 },
  { id: "run-1041", agentName: "Review Companion", projectName: "Signal Review", state: "verified", startedAt: "Aug 25, 13:34", duration: "04:18", eventCount: 19 },
  { id: "run-1039", agentName: "Review Companion", projectName: "Signal Review", state: "failed", startedAt: "Yesterday, 18:12", duration: "01:03", eventCount: 7 },
];

const toneForState = (state: RunSummary["state"]) => state === "verified" ? "good" : state === "waiting" ? "warn" : state === "failed" ? "bad" : "neutral";

export function RunsPage({ runId }: { runId?: string }) {
  const selected = runs.find((run) => run.id === runId) ?? runs[0];
  return (
    <div className="page-stack">
      <div className="page-intro"><div><span className="ui-eyebrow">Immutable history</span><h2>Runs tell you what happened.</h2><p>Inspect event order, approvals, artifacts, and verifier outcomes without changing the original run.</p></div><LinkButton href="#/monitor" icon={Play} variant="primary">Open monitor</LinkButton></div>
      <div className="content-grid two-thirds"><Panel><SectionHeading eyebrow="Run history" title="Recent runs" detail="Every run is pinned to an Agent version." /><div className="run-list">{runs.map((run) => <a className={`run-row ${run.id === selected.id ? "selected" : ""}`} href="#/runs" key={run.id}><span className="run-state-icon"><FileCheck2 size={17} /></span><span className="row-copy"><strong>{run.agentName}</strong><small>{run.projectName} · {run.startedAt}</small><em><Clock3 size={12} /> {run.duration} · {run.eventCount} events</em></span><StatusBadge label={run.state} tone={toneForState(run.state)} /><ArrowUpRight size={15} className="row-arrow" /></a>)}</div></Panel><Panel><SectionHeading eyebrow="Selected run" title={selected.id} /><div className="run-detail-header"><StatusBadge label={selected.state} tone={toneForState(selected.state)} /><Tag>{selected.agentName}</Tag></div><dl className="detail-list"><div><dt>Project</dt><dd>{selected.projectName}</dd></div><div><dt>Started</dt><dd>{selected.startedAt}</dd></div><div><dt>Duration</dt><dd>{selected.duration}</dd></div><div><dt>Evidence</dt><dd>{selected.eventCount} ordered events</dd></div></dl><div className="button-row"><LinkButton href="#/monitor" icon={Play} size="sm" variant="primary">Open run canvas</LinkButton><Button icon={RotateCcw} size="sm">Retry safe nodes</Button></div></Panel></div>
    </div>
  );
}
