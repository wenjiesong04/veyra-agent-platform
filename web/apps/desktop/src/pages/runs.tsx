import { ArrowUpRight, Clock3, FileCheck2, Play, RotateCcw } from "lucide-react";
import type { RunSummary } from "@veyra/api-contracts";
import { Button, LinkButton, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";

const runs: RunSummary[] = [
  { id: "run-1042", agentName: "Release Check", projectName: "Release Room", state: "waiting", startedAt: "Aug 25, 14:08", duration: "08:42", eventCount: 28 },
  { id: "run-1041", agentName: "Review Companion", projectName: "Signal Review", state: "verified", startedAt: "Aug 25, 13:34", duration: "04:18", eventCount: 19 },
  { id: "run-1039", agentName: "Review Companion", projectName: "Signal Review", state: "failed", startedAt: "Yesterday, 18:12", duration: "01:03", eventCount: 7 },
];

const toneForState = (state: RunSummary["state"]) => state === "verified" ? "good" : state === "waiting" ? "warn" : state === "failed" ? "bad" : "neutral";

export function RunsPage({ runId }: { runId?: string }) {
  const { locale } = useLocale();
  const copy = locale === "zh" ? {
    eyebrow: "不可变历史", title: "运行记录告诉你发生了什么。", description: "检查事件顺序、审批、产物和验证器结果，不改变原始运行。", openMonitor: "打开监控", history: "运行历史", recent: "最近运行", detail: "每次运行都固定到一个 Agent 版本。", selected: "选中的运行", project: "项目", started: "开始时间", duration: "耗时", evidence: "证据", ordered: "个有序事件", openCanvas: "打开运行 Canvas", retry: "重试安全节点", events: "个事件", state: { waiting: "等待中", verified: "已验证", failed: "失败", running: "运行中", queued: "排队中" }, dates: { "Aug 25, 14:08": "8月25日 14:08", "Aug 25, 13:34": "8月25日 13:34", "Yesterday, 18:12": "昨天 18:12" },
  } : {
    eyebrow: "Immutable history", title: "Runs tell you what happened.", description: "Inspect event order, approvals, artifacts, and verifier outcomes without changing the original run.", openMonitor: "Open monitor", history: "Run history", recent: "Recent runs", detail: "Every run is pinned to an Agent version.", selected: "Selected run", project: "Project", started: "Started", duration: "Duration", evidence: "Evidence", ordered: "ordered events", openCanvas: "Open run canvas", retry: "Retry safe nodes", events: "events", state: { waiting: "waiting", verified: "verified", failed: "failed", running: "running", queued: "queued" }, dates: { "Aug 25, 14:08": "Aug 25, 14:08", "Aug 25, 13:34": "Aug 25, 13:34", "Yesterday, 18:12": "Yesterday, 18:12" },
  };
  const stateLabel = (state: RunSummary["state"]) => copy.state[state];
  const dateLabel = (date: string) => copy.dates[date as keyof typeof copy.dates] ?? date;
  const selected = runs.find((run) => run.id === runId) ?? runs[0];
  return (
    <div className="page-stack">
      <div className="page-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{copy.title}</h2><p>{copy.description}</p></div><LinkButton href="#/monitor" icon={Play} variant="primary">{copy.openMonitor}</LinkButton></div>
      <div className="content-grid two-thirds"><Panel><SectionHeading eyebrow={copy.history} title={copy.recent} detail={copy.detail} /><div className="run-list">{runs.map((run) => <a className={`run-row ${run.id === selected.id ? "selected" : ""}`} href="#/runs" key={run.id}><span className="run-state-icon"><FileCheck2 size={17} /></span><span className="row-copy"><strong>{run.agentName}</strong><small>{run.projectName} · {dateLabel(run.startedAt)}</small><em><Clock3 size={12} /> {run.duration} · {run.eventCount} {copy.events}</em></span><StatusBadge label={stateLabel(run.state)} tone={toneForState(run.state)} /><ArrowUpRight size={15} className="row-arrow" /></a>)}</div></Panel><Panel><SectionHeading eyebrow={copy.selected} title={selected.id} /><div className="run-detail-header"><StatusBadge label={stateLabel(selected.state)} tone={toneForState(selected.state)} /><Tag>{selected.agentName}</Tag></div><dl className="detail-list"><div><dt>{copy.project}</dt><dd>{selected.projectName}</dd></div><div><dt>{copy.started}</dt><dd>{dateLabel(selected.startedAt)}</dd></div><div><dt>{copy.duration}</dt><dd>{selected.duration}</dd></div><div><dt>{copy.evidence}</dt><dd>{selected.eventCount} {copy.ordered}</dd></div></dl><div className="button-row"><LinkButton href="#/monitor" icon={Play} size="sm" variant="primary">{copy.openCanvas}</LinkButton><Button icon={RotateCcw} size="sm">{copy.retry}</Button></div></Panel></div>
    </div>
  );
}
